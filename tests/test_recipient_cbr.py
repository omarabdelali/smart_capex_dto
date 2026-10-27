from datetime import date
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from django.test import SimpleTestCase,TestCase
from core.models import Site,RadioNetworkEvent
from services.models.features.neighborhood import offset
from services.models.prediction.recipient_cbr import forecast
from services.models.prediction.recipient_uncertainty import event_multipliers,weighted_estimate,smooth_curve
from services.models.prediction.recipient_uncertainty import prediction_radius,_artifact
from services.models.prediction.matched_controls import MatchedControls
from services.models.prediction.recipient_data import load_training
from services.models.prediction.pair_cases import event_bands,event_magnitude
from services.models.prediction.accuracy_audit import baseline_forecasts,comparison_metrics
from services.models.prediction.action_context import other_site_actions


def pair(key,recipient='a',load=10,delta=1):
    return {'event_key':key,'event_site_id':key,'recipient_site_id':recipient,'event_date':'2024-07-01',
        'event_type':'CELL_ADDED','tier_scheme':'standard','technology':'4G','bands':['B3'],
        'distance_m':1000.,'relative_bearing_deg':30.,'same_band':True,
        'recipient_pre_dl_gb':load,'recipient_pre_active_users':load,'recipient_pre_prb_util_pct':20.,
        'recipient_pre_cqi':10.,'event_prb_delta':25.,'event_added_cells':1,
        'outcome_months':{str(h):offset(date(2024,7,1),h).isoformat() for h in range(1,7)},
        'outcomes':{'downlink_traffic_gb':{str(h):delta for h in range(1,7)}}}


class FakeData:
    def __init__(self):
        self.exposure_cache={};self.control_cache={};self.cache={}
        self.locations={key:{'site_id':key,'site_name':key,'latitude':lat,'longitude':9.,'cluster_id':1}
            for key,lat in [('a',35.01),('b',35.02),('c1',35.5),('c2',35.6),('c3',35.7)]}
        self.events=[SimpleNamespace(effective_date=date(2025,7,1),site=SimpleNamespace(latitude=35.,longitude=9.))]
        self.history={}
        for key in self.locations:
            self.history[key]={date(2025,m,1):{'traffic_bits':(2*m+2)*8e9} for m in range(1,7)}
            self.history[key][date(2025,8,1)]={'traffic_bits':(20 if key in ('a','b') else 16)*8e9}

    def bands(self,key,cutoff):
        return {'B3'}

    def values(self,key,cutoff,metric,n=3):
        from services.models.prediction.cbr_impact import _row_value
        return [_row_value(self.history.get(key,{}).get(offset(cutoff,k)),metric) for k in range(-n,0)]

    def query_pairs(self,site,event,scope):
        rows=[]
        for key,load in [('a',10),('b',100)]:
            row=pair('query',key,load);row.update(event_date=event.effective_date.isoformat(),site_name=key,tier='tier1')
            rows.append(row)
        return {'canonical_site_id':'query','tier_scheme':'standard'},rows


class RecipientMathTests(SimpleTestCase):
    def test_accuracy_baselines_use_only_pre_event_months(self):
        cutoff=date(2025,7,1)
        history={offset(cutoff,k):{'traffic_bits':(k+10)*8e9} for k in range(-12,7)}
        before=baseline_forecasts(history,cutoff,'downlink_traffic_gb',3)
        self.assertEqual(before['median_3m'],8)
        self.assertEqual(before['last_month'],9)
        self.assertAlmostEqual(before['linear_trend_6m'],13)
        for k in range(0,7):
            history[offset(cutoff,k)]['traffic_bits']=1e30
        self.assertEqual(before,baseline_forecasts(history,cutoff,'downlink_traffic_gb',3))

    def test_zero_observation_has_absolute_error_but_no_percentage(self):
        result=comparison_metrics(0.,5.,0.)
        self.assertEqual(result['absolute_error'],5)
        self.assertIsNone(result['absolute_percentage_error'])
        self.assertFalse(result['beats_last_month'])
        self.assertIsNone(comparison_metrics(None,5,4)['absolute_error'])

    def test_other_actions_are_grouped_by_month_and_marked_retrospective(self):
        site=SimpleNamespace(site_id='origin',canonical_site_id='origin')
        def event(key,month):
            return SimpleNamespace(event_key=key,site=site,effective_date=month,event_type='BANDWIDTH_UPGRADE',details={'cell_ids':[key]})
        cutoff=date(2025,7,1)
        events=[event('selected',cutoff),event('same-month',cutoff),event('later1',offset(cutoff,1)),event('later2',offset(cutoff,1))]
        context=other_site_actions(events,'origin','selected',cutoff)
        self.assertEqual(context[0]['phase'],'concurrent')
        self.assertEqual(context[1]['phase'],'later')
        self.assertEqual(context[1]['event_count'],2)

    def test_bandwidth_events_derive_band_and_signed_magnitude(self):
        event=SimpleNamespace(event_type='BANDWIDTH_DOWNGRADE',previous_bandwidth_mhz=20,new_bandwidth_mhz=10,
            details={'cell_ids':['c']},effective_date=date(2025,7,1))
        self.assertEqual(event_bands(event,{'c':{'band':'L1800'}}),{'L1800'})
        self.assertEqual(event_magnitude(event,{}),{'event_prb_delta':-50,'event_added_cells':0})
    def test_event_draw_counts_are_shared_across_recipients_and_horizons(self):
        draws=event_multipliers(['e1','e1','e2'],'seed',500)
        self.assertTrue(np.array_equal(draws[:,0],draws[:,1]))
        self.assertFalse(np.array_equal(draws[:,0],draws[:,2]))
        self.assertTrue(np.array_equal(draws[:,0],event_multipliers(['e1'],'seed',500)[:,0]))

    def test_many_pairs_from_one_event_do_not_create_independent_support(self):
        rows=[pair('single',str(i)) for i in range(20)]
        point,draws,report=weighted_estimate(rows,[1]*20,[.1]*20,rows[0],'seed')
        self.assertIsNone(point);self.assertEqual(report['n_events'],1)
        rows=[{**pair('action'+str(i)),'event_site_id':'same-site'} for i in range(20)]
        point,_,report=weighted_estimate(rows,[1]*20,[.1]*20,rows[0],'seed')
        self.assertIsNone(point);self.assertEqual(report['n_event_sites'],1)

    def test_prediction_interval_needs_dated_coverage_and_matching_dataset(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);base=root/'data/calibration';base.mkdir(parents=True)
            (base/'event_recipient_cases.manifest.json').write_text(json.dumps({'sha256':'current'}))
            records=[{'metric':'downlink_traffic_gb','horizon':1,'method':'pair_cbr','ramp':False,
                'event_type':'CELL_ADDED','tier_scheme':'standard','event_key':'e'+str(i),'event_site_id':'s'+str(i),
                'available_month':offset(date(2020,1,1),i).isoformat(),'error':1.} for i in range(45)]
            path=base/'intervals.json';payload={'model_version':'v1','dataset_sha256':'current','records':records}
            path.write_text(json.dumps(payload))
            policy={'calibration_path':'data/calibration/intervals.json','version':'v1','minimum_calibration_events':20,'minimum_calibration_coverage':.9}
            query={'event_date':'2025-01-01','event_site_id':'query','event_type':'CELL_ADDED','tier_scheme':'standard'}
            with self.settings(BASE_DIR=root),patch('services.models.prediction.recipient_uncertainty.policy',return_value=policy):
                radius,report=prediction_radius(query,'downlink_traffic_gb',1,'pair_cbr',False)
                self.assertEqual(radius,1.)
                self.assertEqual(report['status'],'available')
                future={**records[0],'available_month':'2028-01-01','event_key':'future','error':1e8}
                payload['records'].append(future);path.write_text(json.dumps(payload));_artifact.cache_clear()
                self.assertEqual(prediction_radius(query,'downlink_traffic_gb',1,'pair_cbr',False)[0],1.)
                payload['dataset_sha256']='stale';path.write_text(json.dumps(payload));_artifact.cache_clear()
                self.assertIsNone(prediction_radius(query,'downlink_traffic_gb',1,'pair_cbr',False)[0])

    def test_bootstrap_recomputes_local_estimator_and_is_finite(self):
        rows=[pair('e'+str(i//3),str(i),load=i+10,delta=i) for i in range(15)]
        point,draws,report=weighted_estimate(rows,list(range(15)),[.1]*15,rows[5],'seed',local=True)
        self.assertIsNotNone(point)
        self.assertGreater(np.isfinite(draws).sum(),400)
        self.assertIn('local_features',report)

    def test_ramp_preserves_missing_horizons_and_allows_negative_effects(self):
        values=[-10.,-5.,None,2.,5.,7.];samples=[np.full(500,v) if v is not None else None for v in values]
        curve,draws,applied=smooth_curve(values,samples,[3]*6)
        self.assertTrue(applied);self.assertIsNone(curve[2]);self.assertLess(curve[0],0)
        self.assertIsNone(draws[2])

    def test_matched_mean_baseline_did_and_later_exposure_censoring(self):
        data=FakeData();controls=MatchedControls(data);cutoff=date(2025,7,1)
        match=controls.select('a',cutoff,'downlink_traffic_gb')
        self.assertEqual(match['status'],'available')
        effect,report=controls.effect('a',cutoff,'downlink_traffic_gb',1)
        self.assertAlmostEqual(effect,4.)
        self.assertAlmostEqual(report['observed_control_change'],4.)
        self.assertAlmostEqual(controls.forecast_growth(match,1),6.)
        # Future control observations can alter historical labels but not the
        # pre-event control selection or pre-event-only growth forecast.
        data.history['c1'][date(2025,8,1)]['traffic_bits']=999*8e9
        self.assertAlmostEqual(controls.forecast_growth(match,1),6.)
        data.events.append(SimpleNamespace(effective_date=date(2025,8,1),site=SimpleNamespace(latitude=35.5,longitude=9.)))
        data.exposure_cache.clear()
        effect,report=controls.effect('a',cutoff,'downlink_traffic_gb',1)
        self.assertIsNone(effect);self.assertEqual(report['reason'],'incomplete_or_censored_control_outcomes')

    def test_controls_never_silently_relax_exposure_or_history(self):
        data=FakeData();data.events.append(SimpleNamespace(effective_date=date(2025,6,1),site=SimpleNamespace(latitude=35.6,longitude=9.)))
        result=MatchedControls(data).select('a',date(2025,7,1),'downlink_traffic_gb')
        self.assertEqual(result['status'],'unavailable')
        self.assertEqual(result['controls'],[])

    def test_training_loader_skips_future_and_same_origin(self):
        query={**pair('query'),'event_date':'2025-01-01'}
        old=pair('old');same={**old,'event_site_id':'query'};future={**old,'event_key':'future','event_date':'2026-01-01'}
        with TemporaryDirectory() as folder:
            path=Path(folder)/'cases.jsonl';path.write_text('\n'.join(json.dumps(r) for r in [old,same,future]))
            self.assertEqual([r['event_key'] for r in load_training(query,'downlink_traffic_gb',1,path)],['old'])

    def test_live_recipient_forecasts_differ_by_load_and_ignore_future_targets(self):
        data=FakeData();site=SimpleNamespace();event=SimpleNamespace(event_key='query',event_type='CELL_ADDED',effective_date=date(2025,7,1))
        rows=[pair('e'+str(i),key,load,delta) for i in range(6) for key,load,delta in [('a',10,1),('b',100,10)]]
        with patch('services.models.prediction.recipient_cbr.prediction_radius',return_value=(None,{'status':'unavailable'})):
            result=forecast(site,event,data=data,training=rows,bootstrap_draws=100)
            a,b=result['recipients']
            self.assertLess(a['points'][0]['predicted'],b['points'][0]['predicted'])
            changed=copy.deepcopy(rows)
            for r in changed:
                r['outcomes']['downlink_traffic_gb']['6']=1e8;r['outcome_months']['6']='2026-01-01'
            later=forecast(site,event,data=data,training=changed,bootstrap_draws=100)
        self.assertEqual(a['points'][0]['predicted'],later['recipients'][0]['points'][0]['predicted'])
        self.assertIsNone(later['recipients'][0]['points'][5]['predicted'])


class RecipientApiTests(TestCase):
    def test_metadata_validation_and_foreign_event_rejection(self):
        site=Site.objects.create(site_id='site',site_name='Site',latitude=35,longitude=9,location='',cluster_id=-1)
        RadioNetworkEvent.objects.create(site=site,event_key='event',event_type='CELL_ADDED',effective_date=date(2025,7,1),detector_version='fixture',details={})
        self.assertEqual(self.client.get('/api/cbr/recipients/',{'site_id':'site','metadata':'true'}).status_code,200)
        self.assertEqual(self.client.get('/api/cbr/recipients/',{'site_id':'site','metric':'rsrp_dbm'}).status_code,400)
        self.assertEqual(self.client.get('/api/cbr/recipients/',{'site_id':'site','event_key':'foreign'}).status_code,422)
        self.assertEqual(self.client.get('/api/cbr/recipients/',{'site_id':'site','scope':'cluster'}).status_code,400)
