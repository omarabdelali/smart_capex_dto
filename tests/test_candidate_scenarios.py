from datetime import date
from unittest.mock import patch
from django.test import TestCase
from core.models import CandidateScenario, Site, Cell, RadioNetworkEvent
from services.candidate_scenarios import validate, classify_location, run_similarity


class CandidateScenarioTests(TestCase):
    def test_historical_month_and_tdd_are_rejected(self):
        values={'name':'test','latitude':35,'longitude':9,'technology':'4G','sector_count':3,'band':'TDD'}
        with self.assertRaises(ValueError): validate(values)

    def test_dbscan_classification_preserves_live_sites_and_rejects_colocation(self):
        for i,(lat,lon) in enumerate([(35,9),(35.005,9),(35.01,9)]):
            Site.objects.create(site_id=str(i),site_name=str(i),location='',latitude=lat,longitude=lon,cluster_id=7,canonical_site_id=str(i))
        cluster,_=classify_location(35.006,9.002,{})
        self.assertEqual(cluster,7)
        self.assertEqual(Site.objects.count(),3)
        with self.assertRaises(ValueError): classify_location(35,9,{})

    def test_new_real_cluster_is_hypothetical_and_keeps_noise_labels(self):
        for i,lat in enumerate((34.984,35.016)):
            Site.objects.create(site_id=str(i),site_name=str(i),location='',latitude=lat,longitude=9,cluster_id=-1,canonical_site_id=str(i))
        cache={}
        cluster,detail=classify_location(35,9,cache)
        self.assertEqual(cluster,-2)
        self.assertEqual(detail['kind'],'new')
        self.assertEqual(set(detail['member_site_ids']),{'0','1'})
        self.assertEqual(Site.objects.filter(cluster_id=-1).count(),2)

    def test_multiple_bands_and_new_site_single_technology_event(self):
        payload={'name':'test','latitude':35,'longitude':9,'sector_count':3,
            'technologies':[{'technology':'LTE','bands':'L1800; L800'}]}
        values=validate(payload)
        self.assertEqual(values['event_type'],'TECHNOLOGY_ADDED')
        self.assertEqual(values['technologies'][0],{'technology':'4G','bands':['L1800','L800']})
        payload['technologies'].append({'technology':'3G','bands':'U900'})
        self.assertEqual(validate(payload)['event_type'],'SITE_ADDED')

    def test_existing_site_addition_uses_physical_aliases(self):
        site=Site.objects.create(site_id='1',site_name='A',location='',latitude=35,longitude=9,canonical_site_id='1')
        alias=Site.objects.create(site_id='2',site_name='A2',location='',latitude=35,longitude=9,canonical_site_id='1')
        Cell.objects.create(site=alias,cell_id='a',cell_name='a',technology='4G',band='L1800',frequency=100,azimuth=0,antenna_height_m=25)
        payload={'name':'change','latitude':35,'longitude':9,'sector_count':3,'mode':'existing','site_id':'1',
            'technologies':[{'technology':'4G','bands':'L800'}]}
        with self.assertRaises(ValueError): validate(payload)
        payload['action']='band'
        self.assertEqual(validate(payload)['event_type'],'FREQUENCY_BAND_ADDED')
        payload['technologies'][0]['bands']='L1800'
        with self.assertRaises(ValueError): validate(payload)
        payload.update(action='bandwidth',cell_id='a',previous_bandwidth_mhz=10,new_bandwidth_mhz=20)
        self.assertEqual(validate(payload)['event_type'],'BANDWIDTH_UPGRADE')
        payload.update(previous_bandwidth_mhz=20,new_bandwidth_mhz=5)
        self.assertEqual(validate(payload)['event_type'],'BANDWIDTH_DOWNGRADE')

    @patch('services.models.similarity.profile_cache.profile_revision',return_value=None)
    @patch('services.models.similarity.profile_cache.cached_profile')
    @patch('services.analysis_profiles.resolve_profile')
    @patch('services.models.similarity.case_selector.rank_similar_cases')
    def test_profile_and_event_month_filter_apply_to_each_historical_event(self,rank,resolve,cached,revision):
        site=Site.objects.create(site_id='10',site_name='Historical',location='',latitude=35,longitude=9,cluster_id=7,canonical_site_id='10')
        for year in (2024,2025,2027):
            RadioNetworkEvent.objects.create(site=site,event_key=str(year),event_type='TECHNOLOGY_ADDED',effective_date=date(year,1,1),
                detector_version='test',details={'technologies':['4G'],'bands':['L1800']})
        other=Site.objects.create(site_id='20',site_name='Other',location='',latitude=36,longitude=9,cluster_id=7,canonical_site_id='20')
        RadioNetworkEvent.objects.create(site=other,event_key='other',event_type='TECHNOLOGY_ADDED',effective_date=date(2025,2,1),
            detector_version='test',details={'technologies':['4G'],'bands':['L1800']})
        settings={'similarity_features':['n_sites_1km'],'representation':'original','weighting_mode':'equal_per_group',
            'allow_filter_relaxation':True,'minimum_available_weight_share':.6,'pca_variance_target':.9}
        resolve.return_value=(settings,{'name':'Selected','revision':2},None)
        cached.side_effect=lambda s,cutoff,cache,rev:{'site_id':s.site_id,'n_sites_1km':1}
        rank.return_value={'cases':[{'candidate_index':i,'similarity':1-d,'distance':d,'used_features':['n_sites_1km'],'feature_weights':{'n_sites_1km':1}} for i,d in enumerate((.1,.2,.3))],
            'active_features':['n_sites_1km'],'excluded_features':{},'filter_explanation':'ok'}
        inputs={'event_month':'2026-01-01','profile_id':'selected','site_id':None}
        vector={'event_type':'TECHNOLOGY_ADDED','tier_scheme':'standard','tech_added':'4G','bands_added':'L1800','_event_technologies':'4G'}
        result=run_similarity(inputs,vector)
        self.assertEqual(result['pool_size'],3)
        self.assertEqual([item['site_id'] for item in result['cases']],['10','20'])
        self.assertAlmostEqual(sum(item['weight'] for item in result['cases']),1)
        self.assertEqual(result['profile']['revision'],2)
        self.assertEqual(rank.call_args.kwargs['selected_features'],['n_sites_1km'])
        self.assertEqual(rank.call_args.kwargs['k'],3)
        self.assertEqual(rank.call_args.kwargs['weighting_mode'],'equal_per_group')

    @patch('services.candidate_scenarios.run_similarity')
    @patch('services.candidate_scenarios.calculate_features')
    @patch('services.candidate_scenarios.validate')
    def test_saved_candidate_is_separate_and_loadable(self,validation,calculate,similarity):
        inputs={'name':'Future','latitude':35.,'longitude':9.,'technology':'4G','band':'L1800','sector_count':3,'event_month':'2026-10-01'}
        validation.return_value=inputs
        calculate.return_value=({'cluster_id':-1,'avg_users':None},{'method':'test'})
        similarity.return_value={'cases':[],'active_features':[]}
        response=self.client.post('/api/candidates/',data=inputs,content_type='application/json')
        self.assertEqual(response.status_code,201)
        saved=CandidateScenario.objects.get()
        self.assertEqual(saved.status,'complete')
        self.assertIsNone(saved.features['avg_users'])
        self.assertEqual(Site.objects.count(),0)
        loaded=self.client.get('/api/candidates/'+str(saved.id)+'/')
        self.assertEqual(loaded.json()['result']['similarity']['cases'],[])
