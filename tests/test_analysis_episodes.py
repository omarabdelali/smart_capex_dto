from datetime import date
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from django.test import TestCase,SimpleTestCase
from core.models import Site,RadioNetworkEvent,AnalysisEpisode,AnalysisEpisodeMember,Cell,MAOSMonthlyKPI
from services.models.prediction.analysis_episodes import refresh_episodes,as_event,episode_magnitude
from services.models.prediction.pair_cases import export_pair_cases
from services.models.prediction.pair_validation import PairRanker,DEFAULT
from services.models.prediction.recipient_cbr import recipient_request
from tests.test_recipient_cbr import pair


class EpisodePersistenceTests(TestCase):
    def setUp(self):
        self.site=Site.objects.create(site_id='1',site_name='Origin',latitude=35,longitude=9,location='',cluster_id=-1,canonical_site_id='1')
        self.alias=Site.objects.create(site_id='101',site_name='Origin alias',latitude=35,longitude=9,location='',cluster_id=-1,canonical_site_id='1')

    def event(self,key,month=11,site=None,kind='BANDWIDTH_UPGRADE',cell=None):
        return RadioNetworkEvent.objects.create(site=site or self.site,event_key=key,event_type=kind,
            effective_date=date(2025,month,1),detector_version='fixture',previous_bandwidth_mhz=5,new_bandwidth_mhz=10,
            details={'cell_ids':[cell or key],'technologies':['4G'],'bands':['B3'],
                'cell_activation_months':{cell or key:f'2025-{month:02}-01'}})

    def test_alias_actions_group_months_remain_separate_and_refresh_is_idempotent(self):
        self.event('a');self.event('b',site=self.alias);self.event('c',month=12)
        report=refresh_episodes()
        self.assertEqual(report['raw_events'],3)
        self.assertEqual(report['episodes'],2)
        november=AnalysisEpisode.objects.get(effective_date=date(2025,11,1))
        self.assertEqual(november.site_id,self.site.pk)
        self.assertEqual(november.raw_events.count(),2)
        self.assertEqual(episode_magnitude(as_event(november),{}),{'event_prb_delta':50,'event_added_cells':0})
        self.assertEqual(refresh_episodes()['new_versions'],0)
        self.site.refresh_from_db();self.assertEqual(self.site.cluster_id,-1)
        self.assertEqual(RadioNetworkEvent.objects.filter(is_current=True).count(),3)

    def test_membership_revision_preserves_previous_episode_and_action_snapshot(self):
        event=self.event('a');refresh_episodes()
        old=AnalysisEpisode.objects.get()
        event.new_bandwidth_mhz=15;event.save()
        report=refresh_episodes()
        self.assertEqual(report['new_versions'],1)
        old.refresh_from_db();self.assertFalse(old.is_current)
        self.assertEqual(old.details['actions'][0]['new_bandwidth_mhz'],10)
        self.assertEqual(AnalysisEpisode.objects.filter(is_current=True).count(),1)
        self.assertEqual(AnalysisEpisodeMember.objects.count(),2)

    def test_compound_episode_deduplicates_added_cells_and_keeps_strict_activation_dates(self):
        self.event('a',kind='CELL_ADDED',cell='x')
        self.event('b',site=self.alias,kind='CELL_ADDED',cell='x')
        self.event('c',cell='y')
        refresh_episodes();episode=AnalysisEpisode.objects.get()
        self.assertEqual(episode.event_type,'COMPOUND_EVENT')
        self.assertEqual(episode.details['added_cell_ids'],['x'])
        self.assertEqual(episode.details['cell_activation_months']['x'],'2025-11-01')
        event=as_event(episode)
        self.assertIsNone(episode_magnitude(event,{})['event_prb_delta'])
        self.assertEqual(episode_magnitude(event,{('x',event.effective_date):25}),{'event_prb_delta':50,'event_added_cells':1})

    def test_metadata_exposes_one_icon_choice_per_episode_with_raw_provenance(self):
        self.event('a');self.event('b');self.event('c',month=12);refresh_episodes()
        metadata,code=recipient_request({'site_id':'1','metadata':'true','analysis_unit':'episode'})
        self.assertEqual(code,200)
        self.assertEqual(len(metadata['events']),2)
        self.assertEqual(len(metadata['events'][0]['actions']),2)
        raw,code=recipient_request({'site_id':'1','metadata':'true','analysis_unit':'event'})
        self.assertEqual(len(raw['events']),3)

    def test_export_has_one_label_per_episode_recipient_not_per_raw_action(self):
        peer=Site.objects.create(site_id='2',site_name='Peer',latitude=35.01,longitude=9,location='',cluster_id=-1,canonical_site_id='2')
        cell=Cell.objects.create(site=peer,cell_id='peer',cell_name='peer',technology='4G',band='B3',frequency=1800,azimuth=0,antenna_height_m=25)
        for month,value in [(8,10),(9,20),(10,30),(11,999),(12,40)]:
            MAOSMonthlyKPI.objects.create(cell=cell,month_date=date(2025,month,1),thrp_bits_dl=value*8e9)
        self.event('a');self.event('b');refresh_episodes()
        with TemporaryDirectory() as folder:
            path=Path(folder)/'episodes.jsonl'
            report=export_pair_cases(path,lambda _:None,analysis_unit='episode')
            rows=[json.loads(line) for line in path.read_text().splitlines()]
        self.assertEqual(report['events'],1)
        self.assertEqual(report['pairs'],1)
        self.assertEqual(rows[0]['raw_event_keys'],['a','b'])
        self.assertEqual(rows[0]['recipient_pre_dl_gb'],20)
        self.assertEqual(rows[0]['outcomes']['downlink_traffic_gb']['1'],20)
        self.assertNotIn('0',rows[0]['outcomes']['downlink_traffic_gb'])


class EpisodeCompatibilityTests(SimpleTestCase):
    def test_pair_ranker_cannot_mix_raw_cases_or_different_compound_actions(self):
        q={**pair('q'),'analysis_unit':'episode','action_signature':'CELL_ADDED+BANDWIDTH_UPGRADE'}
        rows=[{**pair('raw')},{**pair('wrong'),'analysis_unit':'episode','action_signature':'CELL_ADDED+BANDWIDTH_DOWNGRADE'},
            {**pair('correct'),'analysis_unit':'episode','action_signature':q['action_signature']}]
        ranker=PairRanker(rows,'downlink_traffic_gb',1)
        self.assertEqual(ranker.neighbors(q,DEFAULT)[0],[2])
