import copy
from datetime import date
from types import SimpleNamespace
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import numpy as np
from django.test import SimpleTestCase,TestCase
from core.models import Site,Cell,MAOSMonthlyKPI,RadioNetworkEvent
from services.models.features.neighborhood import offset
from services.models.prediction.counterfactual_gains import add_gain_series,gain_forecast
from services.models.prediction.pair_validation import PairRanker,DEFAULT
from services.models.prediction.recipient_data import RecipientData
from services.models.prediction.pair_cases import export_pair_cases
from services.models.prediction.analysis_episodes import refresh_episodes
from services.analysis_profiles import defaults
from tests.test_recipient_cbr import FakeData,pair


class GainArithmeticTests(SimpleTestCase):
    def test_signed_monthly_gain_and_joint_cumulative_draws(self):
        points=[{'predicted':v,'observed':None} for v in (8.,13.,9.)]
        draws=[np.array([v-1,v+1,v-1,v+1,v]) for v in (8.,13.,9.)]
        report=add_gain_series(points,draws,[10.,10.,10.],3)
        self.assertEqual([p['monthly_gain'] for p in points],[-2.,3.,-1.])
        self.assertEqual(report['gain'],0.)
        self.assertEqual(points[0]['cumulative_gain'],-2.)
        self.assertEqual(report['mean_interval_95'],[-3.,3.])

    def test_gap_never_becomes_zero_or_partial_cumulative_total(self):
        points=[{'predicted':v} for v in (11.,None,13.)]
        report=add_gain_series(points,[np.ones(5)*11,np.full(5,np.nan),np.ones(5)*13],[10.,10.,10.],3)
        self.assertEqual(points[0]['cumulative_gain'],1.)
        self.assertIsNone(points[1]['monthly_gain'])
        self.assertIsNone(points[2]['cumulative_gain'])
        self.assertIsNone(report['gain'])
        self.assertEqual(report['supported_months'],2)

    def test_zero_is_measured_and_forecast_origin_roles_never_mix(self):
        points=[{'predicted':0.}]
        report=add_gain_series(points,[np.zeros(5)],[0.],1)
        self.assertEqual(report['gain'],0.)
        rows=[{**pair('neighbor'),'recipient_role':'neighbor'},{**pair('origin'),'recipient_role':'origin'}]
        query={**pair('q'),'recipient_role':'origin'}
        self.assertEqual(PairRanker(rows,'downlink_traffic_gb',1).neighbors(query,DEFAULT)[0],[1])


def controlled_fixture():
    data=FakeData();cutoff=date(2024,1,1)
    for key in data.locations:
        for k in range(-6,7):
            data.history[key][offset(cutoff,k)]={'traffic_bits':(14 if key=='a' and k>0 else 10)*8e9}
    data.events.append(SimpleNamespace(event_key='historical',effective_date=cutoff,site=SimpleNamespace(latitude=35.,longitude=9.)))
    rows=[]
    for i in range(6):
        row=pair(f'e{i}',load=10,delta=4)
        row.update(event_date=cutoff.isoformat(),outcome_months={str(h):offset(cutoff,h).isoformat() for h in range(1,7)})
        rows.append(row)
    return data,rows


class GainForecastTests(SimpleTestCase):
    def test_scenario_identity_complete_scope_sum_and_future_query_invariance(self):
        data,rows=controlled_fixture()
        event=SimpleNamespace(event_key='query',event_type='CELL_ADDED',effective_date=date(2025,7,1),details={})
        choices={**defaults(),'prediction_features':['recipient_pre_dl_gb']}
        kwargs=dict(data=data,training=rows,profile_settings=choices,bootstrap_draws=100,
            reference=({'recipient_pre_dl_gb':[0,100]}, {'reference_id':'fixture-frozen'}),horizon=3)
        result=gain_forecast(SimpleNamespace(),event,**kwargs)
        for recipient in result['recipients']:
            point=recipient['points'][0]
            self.assertAlmostEqual(point['no_event_forecast'],18.)
            self.assertAlmostEqual(point['monthly_gain'],4.)
            self.assertAlmostEqual(point['with_event_forecast'],point['no_event_forecast']+point['monthly_gain'])
            self.assertIsNone(point['prediction_interval_95'])
        self.assertAlmostEqual(result['scope_series'][0]['monthly_gain'],8.)
        self.assertAlmostEqual(result['cumulative']['gain'],24.)
        for history in data.history.values():
            for month in history:
                if month>=event.effective_date:
                    history[month]['traffic_bits']=1e30
        changed=gain_forecast(SimpleNamespace(),event,**kwargs)
        for before,after in zip(result['scope_series'],changed['scope_series']):
            self.assertEqual(before['monthly_gain'],after['monthly_gain'])
            self.assertEqual(before['with_event_forecast'],after['with_event_forecast'])
            self.assertEqual(before['no_event_forecast'],after['no_event_forecast'])

    def test_missing_recipient_history_keeps_complete_scope_gain_unavailable(self):
        data,rows=controlled_fixture();del data.history['b'][date(2025,5,1)]
        event=SimpleNamespace(event_key='query',event_type='CELL_ADDED',effective_date=date(2025,7,1),details={})
        result=gain_forecast(SimpleNamespace(),event,data=data,training=rows,bootstrap_draws=100,
            reference=({'recipient_pre_dl_gb':[0,100]},{'reference_id':'fixture'}),profile_settings={**defaults(),'prediction_features':['recipient_pre_dl_gb']})
        self.assertIsNone(result['cumulative']['gain'])
        self.assertIsNotNone(result['recipients'][0]['cumulative']['gain'])
        self.assertIsNone(result['scope_series'][0]['monthly_gain'])


class GainDataTests(TestCase):
    def test_origin_features_and_export_preserve_unknown_pre_launch_history(self):
        origin=Site.objects.create(site_id='o',site_name='Origin',latitude=35.,longitude=9.,location='',cluster_id=1)
        neighbor=Site.objects.create(site_id='n',site_name='Neighbor',latitude=35.01,longitude=9.,location='',cluster_id=1)
        own=Cell.objects.create(site=origin,cell_id='o',cell_name='o',technology='4G',band='B3',frequency=1800,azimuth=0,antenna_height_m=25)
        peer=Cell.objects.create(site=neighbor,cell_id='n',cell_name='n',technology='4G',band='B3',frequency=1800,azimuth=0,antenna_height_m=25)
        for month in (1,2,3,4,5):
            MAOSMonthlyKPI.objects.create(cell=peer,month_date=date(2025,month,1),thrp_bits_dl=8e9)
        MAOSMonthlyKPI.objects.create(cell=own,month_date=date(2025,4,1),thrp_bits_dl=16e9)
        event=RadioNetworkEvent.objects.create(site=origin,event_key='e',event_type='SITE_ADDED',effective_date=date(2025,4,1),detector_version='fixture',details={'cell_ids':['o'],'bands':['B3'],'technologies':['4G']})
        context,rows=RecipientData().query_pairs(origin,event,'origin')
        self.assertEqual(rows[0]['distance_m'],0.)
        self.assertIsNone(rows[0]['relative_bearing_deg'])
        self.assertIsNone(rows[0]['recipient_pre_dl_gb'])
        self.assertEqual(rows[0]['recipient_role'],'origin')
        refresh_episodes()
        with TemporaryDirectory() as folder:
            path=Path(folder)/'gain.jsonl'
            report=export_pair_cases(path,lambda _:None,'episode',include_origin=True)
            exported=[json.loads(line) for line in path.read_text().splitlines()]
        self.assertEqual(report['pairs'],2)
        self.assertEqual(sum(r['recipient_role']=='origin' for r in exported),1)
        row=next(r for r in exported if r['recipient_role']=='origin')
        self.assertIsNone(row['outcomes']['downlink_traffic_gb']['1'])

    def test_gain_api_validates_horizon_metric_and_noise_cluster(self):
        site=Site.objects.create(site_id='o',site_name='Origin',latitude=35.,longitude=9.,location='',cluster_id=-1)
        RadioNetworkEvent.objects.create(site=site,event_key='e',event_type='CELL_ADDED',effective_date=date(2025,4,1),detector_version='fixture',details={'cell_ids':[]})
        refresh_episodes()
        self.assertEqual(self.client.get('/api/cbr/gains/',{'site_id':'o','metadata':'true'}).status_code,200)
        for params in ({'horizon':0},{'metric':'cqi_avg'},{'scope':'cluster_total'},{'horizon':'bad'}):
            self.assertEqual(self.client.get('/api/cbr/gains/',{'site_id':'o',**params}).status_code,400)
