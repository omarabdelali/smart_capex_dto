"""Temporal leakage regressions using an isolated Django test database."""
from datetime import date
from unittest.mock import patch

from django.test import TestCase

from core.models import Cell, Site, MAOSMonthlyKPI, RadioNetworkEvent
from core.models.features import ConfigurationFeatures, ClusterFeatures
from services.models.similarity.feature_vector import build_site_similarity_vector
from services.models.prediction.cbr_impact import _event_group_responses, build_cbr_impact_prediction


class HistoricalFeatureTests(TestCase):
    def make_site(self, key, lat, event=None):
        site = Site.objects.create(site_id=key, site_name=key, latitude=lat, longitude=9,
                                   location='', is_launched=event is not None, launch_date=event)
        cell = Cell.objects.create(site=site, cell_id=key, cell_name=key, technology='4G',
                                   frequency=1800, band='B3', azimuth=0, antenna_height_m=30)
        return site, cell

    def setUp(self):
        self.origin, self.cell = self.make_site('query', 35, date(2025,6,15))
        self.peer, self.peer_cell = self.make_site('peer', 35.005)
        self.future, self.future_cell = self.make_site('future', 35.002, date(2025,8,1))
        MAOSMonthlyKPI.objects.create(cell=self.cell, month_date=date(2025,5,1), thrp_bits_dl=8e9)
        MAOSMonthlyKPI.objects.create(cell=self.cell, month_date=date(2025,6,1), thrp_bits_dl=800e9)
        MAOSMonthlyKPI.objects.create(cell=self.peer_cell, month_date=date(2025,5,1), thrp_bits_dl=16e9)
        MAOSMonthlyKPI.objects.create(cell=self.future_cell, month_date=date(2025,8,1), thrp_bits_dl=160e9)
        self.population = patch('services.models.similarity.feature_vector.population_features', return_value={
            'population_density_1km_per_km2': 1000, 'population_tier1': 12000, 'population_tier2': 65000})
        self.population.start()
        self.addCleanup(self.population.stop)

    def test_midmonth_excludes_event_month_and_completeness_counts_calendar_gaps(self):
        vector = build_site_similarity_vector(self.origin)
        self.assertAlmostEqual(vector['pre_dl_traffic_gb_day'], 1/31)
        self.assertEqual(vector['feature_as_of_date'], '2025-06-01')
        self.assertEqual(vector['pre_profile_months_available'], 1)
        self.assertAlmostEqual(vector['pre_profile_completeness'], 1/24)
        self.assertEqual(vector['n_sites_1km'], 1)  # Future neighbor excluded.
        self.assertEqual(vector['antenna_height_m'],30)
        self.assertEqual(vector['cluster_id'],-1)

    def test_future_values_and_current_configuration_do_not_change_historical_vector(self):
        before = build_site_similarity_vector(self.origin)
        MAOSMonthlyKPI.objects.filter(month_date__gte=date(2025,6,1)).update(thrp_bits_dl=999999e9)
        ConfigurationFeatures.objects.create(site=self.origin, event_type='CAPACITY_ADD', antenna_height_m=999)
        ClusterFeatures.objects.create(site=self.origin, cluster_id=500, cluster_avg_traffic_gb=99999)
        after = build_site_similarity_vector(Site.objects.get(pk=self.origin.pk))
        self.assertEqual(before, after)

    def test_population_is_static_context_for_2024_event_by_approved_assumption(self):
        self.origin.launch_date = date(2024,6,1)
        vector = build_site_similarity_vector(self.origin)
        self.assertEqual(vector['population_tier1'],12000)
        self.assertEqual(vector['population_tier2'],65000)

    def test_event_labels_and_evidenced_lte_states_survive_config_exclusion(self):
        MAOSMonthlyKPI.objects.filter(cell=self.cell,month_date=date(2025,5,1)).update(thrp_bits_dl=0)
        RadioNetworkEvent.objects.create(site=self.origin,event_key='tech',event_type='TECHNOLOGY_ADDED',
            effective_date=date(2025,6,1),detector_version='test',
            details={'technologies':['4G'],'bands':['B3'],'cell_ids':[self.cell.cell_id]})
        vector=build_site_similarity_vector(self.origin)
        self.assertEqual(vector['tech_added'],'4G')
        self.assertEqual(vector['bands_added'],'B3')
        self.assertIs(vector['tech_before_4g'],False)
        self.assertIs(vector['tech_after_4g'],True)
        self.assertIsNone(vector['tech_before_3g'])
        self.assertIsNone(vector['tech_after_3g'])
        self.assertEqual(vector['antenna_height_m'],30)
        MAOSMonthlyKPI.objects.filter(month_date__gte=date(2025,6,1)).update(thrp_bits_dl=999e9)
        self.assertEqual(build_site_similarity_vector(self.origin),vector)

    def test_configuration_needs_kpi_cells_but_population_is_static(self):
        from services.models.similarity.availability import feature_statuses
        ConfigurationFeatures.objects.create(site=self.origin,event_type='TECHNOLOGY_ADDED',
            sector_count_after=4,antenna_height_m=25,total_bw_after_mhz=180.8)
        vector=build_site_similarity_vector(self.origin,as_of_date=date(2024,6,1))
        before=vector.copy()
        statuses=feature_statuses(self.origin,vector,include_current=True)
        self.assertEqual(statuses['sector_count_after']['code'],'no_kpi_confirmed_configuration')
        self.assertEqual(statuses['population_tier1']['code'],'available')
        self.assertEqual(statuses['total_capacity_after_mbps']['code'],'legacy_mbps_not_defined')
        self.assertEqual(vector,before)
        self.assertEqual(vector['population_tier1'],12000)
        self.assertIsNone(vector['sector_count_after'])

    def test_zero_user_share_available_while_peak_ratio_has_zero_denominator_reason(self):
        from services.models.similarity.availability import feature_statuses
        vector={'feature_as_of_date':'2023-12-01','tier1_edge_user_share':0,
            'tier1_edge_user_peak_ratio':None,'user_context_support':{'tier1':{'ratios':{
                'edge_user_peak_ratio':{'unavailable_reason':'zero_denominator'}}}}}
        statuses=feature_statuses(self.origin,vector)
        self.assertEqual(statuses['tier1_edge_user_share']['code'],'available')
        self.assertEqual(statuses['tier1_edge_user_peak_ratio']['code'],'zero_denominator')

    def test_future_outcome_months_are_not_training_targets(self):
        months = {date(2025,month,1): {'traffic_bits': 8e9*month} for month in (1,2,3,4,5,6,7)}
        responses, _ = _event_group_responses(['peer'], date(2025,4,1), {'peer': months}, available_before=date(2025,6,15))
        self.assertIn(1, responses['downlink_traffic_gb'])
        self.assertNotIn(2, responses['downlink_traffic_gb'])
        self.assertNotIn(3, responses['downlink_traffic_gb'])

    def test_cbr_candidates_exclude_later_launches(self):
        earlier, _ = self.make_site('earlier', 35.01, date(2025,4,1))
        self.make_site('same-month', 35.02, date(2025,6,1))
        result = build_cbr_impact_prediction(self.origin.site_id)
        self.assertEqual(result['prediction_cutoff'], '2025-06-01')
        self.assertEqual([case['site_id'] for case in result['cases']], [earlier.site_id])

    def test_cbr_predictions_are_invariant_to_future_kpi_changes(self):
        self.make_site('earlier1', 35.008, date(2025,2,1))
        self.make_site('earlier2', 35.009, date(2025,3,1))
        for month in (1,2,3,4):
            MAOSMonthlyKPI.objects.create(cell=self.peer_cell, month_date=date(2025,month,1), thrp_bits_dl=8e9*month)
        before = build_cbr_impact_prediction(self.origin.site_id)
        MAOSMonthlyKPI.objects.filter(month_date__gte=date(2025,6,1)).update(thrp_bits_dl=1e18)
        after = build_cbr_impact_prediction(self.origin.site_id)
        def forecasts(payload):
            return [(scope, metric, p['offset'], p['predicted'], p['lower_95'], p['upper_95'], p['analog_cases'])
                    for scope, data in payload['scopes'].items()
                    for metric, points in data['series'].items() for p in points]
        self.assertTrue(any(item[3] is not None for item in forecasts(before)))
        self.assertEqual(forecasts(before), forecasts(after))
