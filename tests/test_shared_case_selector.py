from datetime import date
from types import SimpleNamespace
from unittest.mock import patch
from django.test import SimpleTestCase
from services.models.similarity.case_selector import eligible_events,rank_cases,resolve_template,CaseSelectionError
from services.models.similarity.engine import rank_similar_cases


class SharedCaseSelectorTests(SimpleTestCase):
    def test_original_ranking_matches_existing_similarity_engine(self):
        query={'site_id':'q','tier_scheme':'standard','event_type':'TECHNOLOGY_ADDED','tech_added':'4G',
            'bands_added':'L1800','n_sites_1km':4,'terrain_slope_deg':3}
        cases=[{**query,'site_id':'a','n_sites_1km':3,'terrain_slope_deg':4},
               {**query,'site_id':'b','n_sites_1km':9,'terrain_slope_deg':7}]
        selected=['n_sites_1km','terrain_slope_deg']
        expected=rank_similar_cases(query,cases,k=2,selected_features=selected,weighting_mode='equal_per_group',
            minimum_available_weight_share=.6,strict_selection=True)
        actual=rank_cases(query,cases,selected_features=selected,weighting_mode='equal_per_group',
            minimum_available_weight_share=.6,limit=2,strict_selection=True)['ranking']
        self.assertEqual(actual['cases'],expected['cases'])
        self.assertEqual(actual['active_features'],expected['active_features'])

    def test_profile_resolves_as_similarity_and_errors_propagate(self):
        query={'event_type':'TECHNOLOGY_ADDED','tier_scheme':'standard','_event_technologies':'4G'}
        with patch('services.analysis_profiles.resolve_profile',return_value=({'similarity_features':['n_sites_1km']},{'revision':4},None)) as resolve:
            settings,metadata=resolve_template(None,{'profile_id':'chosen'},query)
        self.assertEqual(settings['similarity_features'],['n_sites_1km'])
        self.assertEqual(metadata['revision'],4)
        self.assertEqual(resolve.call_args.args[1],'similarity')
        with patch('services.analysis_profiles.resolve_profile',return_value=(None,None,({'error':'not found'},404))):
            with self.assertRaises(CaseSelectionError) as error: resolve_template(None,{},query)
        self.assertEqual(error.exception.status,404)

    def test_event_cutoff_and_physical_deduplication(self):
        def event(site,when,key,current=True,physical=None):
            return SimpleNamespace(site=SimpleNamespace(site_id=site,canonical_site_id=physical or site),
                effective_date=when,event_type='TECHNOLOGY_ADDED',is_current=current,event_key=key)
        events=[event('a',date(2024,1,1),'first'),event('alias',date(2024,1,1),'alias',physical='a'),
                event('b',date(2025,1,1),'same'),event('c',date(2026,1,1),'future'),
                event('d',date(2024,1,1),'inactive',current=False)]
        self.assertEqual([e.event_key for e in eligible_events(events,date(2025,1,1))],['first'])
        self.assertEqual(eligible_events(events,date(2025,1,1),'a'),[])

    @patch('services.models.similarity.case_selector.rank_pca')
    @patch('services.models.similarity.case_selector.prepare_pca')
    def test_pca_uses_template_source_features_and_same_rank_settings(self,prepare,rank):
        prepare.return_value={'report':{'available':True,'fit_id':'fit','components':[{'key':'PC1'}]},'query_scores':{}}
        rank.return_value={'cases':[]}
        settings={'similarity_features':['n_sites_1km','terrain_slope_deg'],'pca_variance_target':.9}
        result=rank_cases({'n_sites_1km':2,'terrain_slope_deg':3},[],profile_settings=settings,
            representation='pca',weighting_mode='equal_per_group',limit=5)
        self.assertEqual(result['selected_features'],['PC1'])
        self.assertEqual(prepare.call_args.kwargs['source_features'],settings['similarity_features'])
        self.assertEqual(rank.call_args.kwargs['weighting_mode'],'equal_per_group')
        with self.assertRaises(CaseSelectionError) as error:
            rank_cases({},[],profile_settings=settings,representation='pca',expected_fit_id='different')
        self.assertEqual(error.exception.status,409)
