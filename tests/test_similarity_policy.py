from datetime import date
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import numpy as np
from django.test import SimpleTestCase,TestCase
from core.models import Site,Cell,MAOSMonthlyKPI,RadioNetworkEvent
from services.models.similarity.calibration import freeze_reference,reference_ranges,available_weight_share
from services.models.similarity.gower_distance import GowerDistance
from services.models.similarity.engine import rank_similar_cases
from services.models.similarity.hierarchical_filter import HierarchicalFilter
from services.models.similarity.kernel_weights import KernelWeights
from services.models.prediction.pair_cases import export_pair_cases,relative_bearing,prior_value
from services.models.prediction.pair_validation import split_at,PairRanker,errors,DEFAULT


class SimilarityPolicyTests(SimpleTestCase):
    def test_gaussian_default_and_extreme_distances_stay_normalized(self):
        weights=KernelWeights(bandwidth=1e-6).compute_weights([.2,.8])
        self.assertAlmostEqual(float(weights.sum()),1.)
        self.assertGreater(weights[0],weights[1])
        self.assertTrue(np.isfinite(KernelWeights().compute_weights([.1,.2])).all())
    def test_hard_event_and_scheme_survive_low_support(self):
        q={'event_type':'CELL_ADDED','tier_scheme':'extended','tech_added':'4G'}
        candidates=[{**q,'event_type':'SITE_ADDED'},{**q,'tier_scheme':'standard'},{**q,'tech_added':'3G'}]
        self.assertEqual(HierarchicalFilter().filter_cases(q,candidates),[2])
        self.assertEqual(HierarchicalFilter().filter_cases({**q,'_allow_filter_relaxation':False},candidates),[])

    def test_coverage_is_checked_before_pair_renormalisation(self):
        q={'pre_cqi_avg':10,'pre_active_users':20}
        candidates=[{'site_id':'sparse','pre_cqi_avg':10},{'site_id':'full',**q}]
        result=rank_similar_cases(q,candidates,selected_features=list(q))
        self.assertEqual([r['features']['site_id'] for r in result['cases']],['full'])
        self.assertEqual(result['rejected_cases'][0]['available_weight_share'],.5)
        self.assertEqual(result['cases'][0]['available_weight_share'],1)

    def test_exact_point_six_and_group_budget(self):
        g=GowerDistance()
        q={f:1 for f in ['n_sites_1km','n_sites_2km','n_sites_3km','population_tier1','population_tier2']}
        c={f:1 for f in list(q)[:3]}
        self.assertAlmostEqual(available_weight_share(g,q,c,list(q),'equal_per_feature'),.6)
        self.assertAlmostEqual(available_weight_share(g,q,c,list(q),'equal_per_group'),.5)
        self.assertEqual(len(rank_similar_cases(q,[c],selected_features=list(q))['cases']),1)

    def test_frozen_ranges_ignore_candidate_pool_and_future_profiles(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'reference.json'
            artifact=freeze_reference([
                {'feature_as_of_date':'2024-01-01','avg_users':0},
                {'feature_as_of_date':'2024-02-01','avg_users':100},
                {'feature_as_of_date':'2025-01-01','avg_users':1e8}],path)
            with patch('services.models.similarity.calibration.policy',return_value={'reference_path':str(path)}):
                first,meta=reference_ranges({'feature_as_of_date':'2024-03-01'},[{'avg_users':10000}])
                second,_=reference_ranges({'feature_as_of_date':'2024-03-01'},[{'avg_users':-999}])
            self.assertEqual(first,second)
            self.assertEqual(first['avg_users'],[5.,95.])
            self.assertEqual(meta['reference_id'],artifact['reference_id'])

    def test_frozen_missing_numeric_range_does_not_become_raw_difference(self):
        result=rank_similar_cases({'feature_as_of_date':'2025-01-01','avg_users':20},
            [{'avg_users':20}],selected_features=['avg_users'],feature_ranges={})
        self.assertEqual(result['cases'],[])

    def test_relative_bearing_wraps_and_missing_stays_unknown(self):
        self.assertEqual(relative_bearing(359,[1,180]),2)
        self.assertEqual(relative_bearing(30,[30,210]),0)
        self.assertIsNone(relative_bearing(30,[]))

    def test_grouped_temporal_split_purges_origins_and_unfinished_outcomes(self):
        def row(key,origin,month,outcome):
            return {'event_key':key,'event_site_id':origin,'event_date':month,
                'outcomes':{'m':{'1':2}},'outcome_months':{'1':outcome}}
        rows=[row('old','other','2024-01-01','2024-02-01'),
              row('same-origin','held','2024-01-01','2024-02-01'),
              row('unfinished','third','2024-03-01','2024-06-01'),
              row('validation','held','2024-06-01','2024-07-01')]
        train,valid=split_at(rows,['2024-06-01'],'m',1)
        self.assertEqual([r['event_key'] for r in train],['old'])
        self.assertEqual([r['event_key'] for r in valid],['validation'])

    def test_pair_ranker_requires_two_independent_events_and_same_scheme(self):
        def row(key,scheme='standard'):
            return {'event_key':key,'event_site_id':key,'event_type':'CELL_ADDED','tier_scheme':scheme,
                'recipient_site_id':'r','bands':['B3'],'technology':'4G','distance_m':1000,
                'relative_bearing_deg':30,'recipient_pre_dl_gb':100,'recipient_pre_active_users':5,
                'recipient_pre_prb_util_pct':20,'recipient_pre_cqi':10,'same_band':True,
                'outcomes':{'m':{'1':2}}}
        query=row('query')
        self.assertIsNone(PairRanker([row('one'),row('other','extended')],'m',1).predict(query,DEFAULT))
        self.assertAlmostEqual(PairRanker([row('one'),row('two')],'m',1).predict(query,DEFAULT),2)


class PairExportTests(TestCase):
    def test_event_recipient_export_has_strict_baselines_and_post_event_targets(self):
        origin=Site.objects.create(site_id='origin',site_name='Origin',latitude=35,longitude=9,location='',cluster_id=1)
        peer=Site.objects.create(site_id='peer',site_name='Peer',latitude=35.01,longitude=9,location='',cluster_id=1)
        cell=Cell.objects.create(site=peer,cell_id='peer-cell',cell_name='peer-cell',technology='4G',band='B3',frequency=1800,azimuth=0,antenna_height_m=25)
        for month,value in [(1,1),(2,2),(3,3),(4,999),(5,5)]:
            MAOSMonthlyKPI.objects.create(cell=cell,month_date=date(2025,month,1),thrp_bits_dl=value*8e9)
        RadioNetworkEvent.objects.create(site=origin,event_key='event',event_type='CELL_ADDED',effective_date=date(2025,4,1),detector_version='fixture',details={'bands':['B3'],'technologies':['4G'],'cell_ids':[]})
        with TemporaryDirectory() as folder:
            path=Path(folder)/'pairs.jsonl';report=export_pair_cases(path,lambda _:None)
            rows=[json.loads(line) for line in path.read_text().splitlines()]
        self.assertEqual(report['pairs'],1)
        self.assertEqual(rows[0]['recipient_pre_dl_gb'],2)
        self.assertEqual(rows[0]['outcomes']['downlink_traffic_gb']['1'],3)
        self.assertNotIn('0',rows[0]['outcomes']['downlink_traffic_gb'])
        self.assertTrue(rows[0]['same_band'])
        self.assertIsNone(rows[0]['recipient_pre_cqi'])
        self.assertIsNone(rows[0]['relative_bearing_deg'])
