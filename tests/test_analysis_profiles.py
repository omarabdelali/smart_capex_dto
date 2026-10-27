from uuid import uuid4
from django.test import TestCase,SimpleTestCase,Client
from services.analysis_profiles import defaults,save_profile,assign_default,resolve_profile,profile_list,validate_settings
from core.models import AnalysisProfileRevision
from services.models.similarity.engine import rank_similar_cases
from services.models.similarity.pca import prepare_pca
from services.models.prediction.pair_validation import PairRanker,DEFAULT
from tests.test_recipient_cbr import pair


class ProfilePersistenceTests(TestCase):
    def setUp(self):
        self.a=uuid4();self.b=uuid4()
        self.context={'event_type':'CELL_ADDED','tier_scheme':'standard','technology':'4G'}

    def create(self,actor=None,**kwargs):
        result,code=save_profile(actor or self.a,{'name':'My template','settings':defaults(),**kwargs})
        self.assertEqual(code,201,result)
        return result

    def test_private_profiles_cannot_be_read_edited_or_assigned_by_other_browser(self):
        p=self.create()
        self.assertEqual(profile_list(self.b)['profiles'],[])
        self.assertEqual(save_profile(self.b,{'name':'stolen','revision':1},p['id'])[1],404)
        self.assertEqual(resolve_profile(self.b,'similarity',{'profile_id':p['id']},self.context)[2][1],404)
        self.assertEqual(assign_default(self.b,{'profile_id':p['id'],'scope':'personal','purpose':'prediction'})[1],404)

    def test_shared_configuration_is_editable_and_revisions_detect_stale_writes(self):
        p=self.create(is_shared=True)
        edited,code=save_profile(self.b,{'revision':1,'name':'Updated'},p['id'])
        self.assertEqual(code,200)
        self.assertEqual(edited['revision'],2)
        self.assertEqual(save_profile(self.a,{'revision':1,'name':'Stale'},p['id'])[1],409)
        self.assertEqual(AnalysisProfileRevision.objects.filter(profile_id=p['id']).count(),2)
        self.assertEqual(AnalysisProfileRevision.objects.get(profile_id=p['id'],revision=1).snapshot['name'],'My template')

    def test_defaults_are_purpose_specific_and_personal_then_specific(self):
        general=self.create(is_shared=True)
        specific=self.create(is_shared=True,event_type='CELL_ADDED')
        personal=self.create()
        for p in (general,specific):
            self.assertEqual(assign_default(self.a,{'profile_id':p['id'],'scope':'system','purpose':'similarity'})[1],200)
        self.assertEqual(resolve_profile(self.a,'similarity',{},self.context)[1]['id'],specific['id'])
        self.assertIsNone(resolve_profile(self.a,'prediction',{},self.context)[0])
        assign_default(self.a,{'profile_id':personal['id'],'scope':'personal','purpose':'similarity'})
        self.assertEqual(resolve_profile(self.a,'similarity',{},self.context)[1]['id'],personal['id'])
        self.assertEqual(resolve_profile(self.b,'similarity',{},self.context)[1]['id'],specific['id'])
        self.assertIsNone(resolve_profile(self.a,'similarity',{'profile_id':'manual'},self.context)[0])

    def test_archive_preserves_history_and_is_not_resolved(self):
        p=self.create(is_shared=True)
        assign_default(self.a,{'profile_id':p['id'],'scope':'system','purpose':'similarity'})
        save_profile(self.a,{'revision':1,'is_active':False},p['id'])
        self.assertIsNone(resolve_profile(self.a,'similarity',{},self.context)[0])
        self.assertEqual(AnalysisProfileRevision.objects.filter(profile_id=p['id']).count(),2)

    def test_explicit_wrong_scenario_and_private_system_default_rejected(self):
        p=self.create(event_type='SITE_ADDED')
        self.assertEqual(resolve_profile(self.a,'prediction',{'profile_id':p['id']},self.context)[2][1],422)
        self.assertEqual(assign_default(self.a,{'profile_id':p['id'],'scope':'system','purpose':'prediction'})[1],400)

    def test_default_scenario_edits_and_visibility_changes_require_copy(self):
        p=self.create(is_shared=True)
        assign_default(self.a,{'profile_id':p['id'],'scope':'system','purpose':'similarity'})
        self.assertEqual(save_profile(self.a,{'revision':1,'event_type':'CELL_ADDED'},p['id'])[1],400)
        self.assertEqual(save_profile(self.a,{'revision':1,'is_shared':False},p['id'])[1],400)

    def test_technology_scenario_matches_bandwidth_events_without_tech_added_feature(self):
        from services.models.similarity.api import profile_parameters
        p=self.create(is_shared=True,event_type='BANDWIDTH_UPGRADE',technology='4G')
        assign_default(self.a,{'profile_id':p['id'],'scope':'system','purpose':'similarity'})
        _,settings,metadata,error=profile_parameters({},self.a,{'event_type':'BANDWIDTH_UPGRADE',
            'tier_scheme':'standard','tech_added':None,'_event_technologies':'4G'})
        self.assertIsNone(error)
        self.assertEqual(metadata['id'],p['id'])

    def test_anonymous_browser_writes_require_csrf_and_persist_session(self):
        client=Client(enforce_csrf_checks=True)
        result=client.get('/api/analysis/profiles/')
        self.assertEqual(result.status_code,200,result.content)
        actor=client.session['analysis_browser']
        payload={'name':'Browser private','settings':defaults()}
        self.assertEqual(client.post('/api/analysis/profiles/',payload,content_type='application/json').status_code,403)
        created=client.post('/api/analysis/profiles/',payload,content_type='application/json',HTTP_X_CSRFTOKEN=result.json()['csrf_token'])
        self.assertEqual(created.status_code,201,created.content)
        self.assertEqual(client.session['analysis_browser'],actor)
        other=Client().get('/api/analysis/profiles/').json()
        self.assertNotIn(created.json()['id'],[p['id'] for p in other['profiles']])


class ProfileCalculationTests(SimpleTestCase):
    def test_schema_rejects_identifiers_unknown_fields_and_empty_selection(self):
        for change in ({'similarity_features':['site_id']},{'prediction_features':[]},{'wrong':1},{'minimum_available_weight_share':.5}):
            with self.assertRaises(ValueError):
                validate_settings(change)

    def test_strict_selection_removes_legacy_fallback_from_distance(self):
        q={'n_sites_1km':1,'pre_cqi_avg':10}
        candidates=[{'site_id':'a','n_sites_1km':1,'pre_cqi_avg':1},{'site_id':'b','n_sites_1km':3,'pre_cqi_avg':10}]
        result=rank_similar_cases(q,candidates,selected_features=['n_sites_1km'],strict_selection=True)
        self.assertEqual(result['cases'][0]['features']['site_id'],'a')
        for row in result['cases']:
            self.assertEqual(row['feature_weights'],{'n_sites_1km':1.})

    def test_pca_profile_controls_sources_and_variance_fingerprint(self):
        rows=[{'site_id':str(i),'n_sites_1km':i,'n_sites_2km':(i*i)%7,'pre_cqi_avg':i%3} for i in range(10)]
        q=rows[1]
        result=prepare_pca(q,rows,source_features=['n_sites_1km','n_sites_2km'],variance_target=.8)
        self.assertTrue(result['report']['available'])
        self.assertEqual(set(result['report']['source_features']),{'n_sites_1km','n_sites_2km'})
        self.assertEqual(result['report']['excluded_features']['pre_cqi_avg'],'not_selected_in_profile')
        other=prepare_pca(q,rows,source_features=['n_sites_1km','n_sites_2km'],variance_target=.99)
        self.assertNotEqual(result['report']['fit_id'],other['report']['fit_id'])

    def test_pair_selection_changes_neighbors_and_missing_selection_has_no_support(self):
        rows=[pair(str(i),load=10+i) for i in range(4)]
        for i,row in enumerate(rows):
            row['distance_m']=4000-i*1000
        q=pair('query',load=10);q['distance_m']=1000
        model=PairRanker(rows,'downlink_traffic_gb',1)
        load=model.neighbors(q,{**DEFAULT,'selected_features':['recipient_pre_dl_gb']})[0]
        distance=model.neighbors(q,{**DEFAULT,'selected_features':['distance_m']})[0]
        self.assertEqual(load[0],0)
        self.assertEqual(distance[0],3)
        self.assertEqual(model.neighbors({**q,'distance_m':None},{**DEFAULT,'selected_features':['distance_m']})[0],[])

    def test_pair_strict_filter_does_not_relax_technology(self):
        rows=[{**pair(str(i)),'technology':'3G'} for i in range(4)]
        model=PairRanker(rows,'downlink_traffic_gb',1)
        self.assertTrue(model.neighbors(pair('q'),DEFAULT)[0])
        self.assertEqual(model.neighbors(pair('q'),{**DEFAULT,'allow_filter_relaxation':False})[0],[])

    def test_explicit_pair_group_weight_is_divided_among_common_features(self):
        query={**pair('q',load=0),'distance_m':0}
        candidate={**pair('other',load=0),'distance_m':1000,'relative_bearing_deg':None}
        model=PairRanker([candidate],'downlink_traffic_gb',1,feature_ranges={
            'distance_m':[0,1000],'relative_bearing_deg':[0,180],'recipient_pre_dl_gb':[0,100]})
        ids,distances,coverage=model.neighbors(query,{**DEFAULT,'weighting_mode':'equal_per_group',
            'selected_features':['distance_m','relative_bearing_deg','recipient_pre_dl_gb']})
        self.assertEqual(ids,[0])
        self.assertAlmostEqual(float(coverage[0]),.75)
        self.assertAlmostEqual(float(distances[0]),.5)
