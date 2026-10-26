from datetime import date
from unittest.mock import patch
from django.test import SimpleTestCase, TestCase
import numpy as np

from core.models import Site, Cell, MAOSMonthlyKPI
from services.models.similarity.pca import prepare_pca, rank_pca
from services.data_explorer import explore, metadata


class PCATests(SimpleTestCase):
    def fixtures(self):
        rows = [{'site_id': str(i), 'event_type': 'CELL_ADDED', 'sector_count_after': i,
                 'total_prb_available': 20 * i, 'population_tier1': i ** 2,
                 'antenna_height_m': 25, 'cluster_id': i, 'cluster_avg_users': i * 12,
                 'road_km_total': i, 'road_context_signature': 'same'} for i in range(1, 41)]
        return {**rows[10], 'site_id': 'query'}, rows

    def test_scaled_candidate_only_fit_reduces_correlated_inputs(self):
        query, rows = self.fixtures()
        fit = prepare_pca(query, rows)
        report = fit['report']
        self.assertTrue(report['available'])
        self.assertLess(report['retained_dimension'], report['input_dimension'])
        self.assertGreaterEqual(report['retained_variance'], .9)
        self.assertAlmostEqual(report['scaler_mean']['sector_count_after'], 20.5)
        self.assertNotIn('query', report['fit_site_ids'])
        self.assertNotIn('cluster_id', report['source_features'])
        self.assertNotIn('cluster_avg_users', report['source_features'])
        self.assertNotIn('road_km_total', report['source_features'])
        self.assertEqual(report['excluded_features']['antenna_height_m'], 'constant_in_candidate_pool')
        changed = prepare_pca({**query, 'sector_count_after': 1e12}, rows)
        self.assertEqual(report['fit_id'], changed['report']['fit_id'])
        self.assertEqual(report['components'], changed['report']['components'])
        self.assertNotEqual(fit['query_scores'], changed['query_scores'])

    def test_no_imputation_and_sparse_inputs_excluded(self):
        query, rows = self.fixtures()
        rows[0]['population_tier1'] = None
        rows[1]['total_prb_available'] = None
        for row in rows[:10]:
            row['terrain_slope_deg'] = None
        for row in rows[10:]:
            row['terrain_slope_deg'] = float(row['site_id'])
        query['terrain_slope_deg'] = 2
        fit = prepare_pca(query, rows)
        self.assertEqual(fit['report']['fit_rows'], 38)
        self.assertEqual(fit['report']['excluded_candidate_count'], 2)
        self.assertNotIn('terrain_slope_deg', fit['report']['source_features'])
        self.assertIsNone(rows[0]['population_tier1'])
        self.assertNotIn(0, fit['candidate_scores'])

    def test_circular_angles_do_not_split_zero_and_360(self):
        query, rows = self.fixtures()
        for i, row in enumerate(rows):
            row['terrain_aspect_deg'] = (i * 10) % 360
        query['terrain_aspect_deg'] = 0
        first = prepare_pca(query, rows)
        second = prepare_pca({**query, 'terrain_aspect_deg': 360}, rows)
        self.assertIn('terrain_aspect_deg__sin', first['report']['encoded_features'])
        np.testing.assert_allclose(list(first['query_scores'].values()), list(second['query_scores'].values()), atol=1e-10)

    def test_actual_weights_selected_dimensions_and_road_cap(self):
        query, rows = self.fixtures()
        fit = prepare_pca(query, rows)
        selected = ['PC1', 'event_type', 'road_km_total']
        for mode in ('equal_per_feature', 'equal_per_group'):
            ranked = rank_pca(query, rows, fit, selected, weighting_mode=mode)
            self.assertEqual(len(ranked['cases']), 10)
            for item in ranked['cases']:
                self.assertAlmostEqual(sum(item['feature_weights'].values()), 1.)
                self.assertLessEqual(item['feature_weights']['road_km_total'], .05 + 1e-12)
                self.assertEqual(set(item['feature_weights']), set(selected))
            self.assertEqual(rank_pca(query, rows, fit, ['road_km_total'], weighting_mode=mode)['cases'], [])
        rows[0]['road_context_signature'] = 'different'
        ranked = rank_pca(query, rows, fit, selected, k=40)
        mismatch = next(item for item in ranked['cases'] if item['candidate_index'] == 0)
        self.assertNotIn('road_km_total', mismatch['feature_weights'])

    def test_insufficient_fit_is_explicit(self):
        query, rows = self.fixtures()
        fit = prepare_pca(query, rows[:2])
        self.assertFalse(fit['report']['available'])
        self.assertIn('Use Original', fit['report']['reason'])


class ExplorerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = Site.objects.create(site_id='a', site_name='Alpha', latitude=35, longitude=9, cluster_id=1, location='')
        cls.b = Site.objects.create(site_id='b', site_name='Beta', latitude=35.01, longitude=9, cluster_id=1, location='')
        cls.c = Site.objects.create(site_id='c', site_name='Noise C', latitude=35.1, longitude=9, cluster_id=-1, location='')
        cls.d = Site.objects.create(site_id='d', site_name='Noise D', latitude=35.2, longitude=9, cluster_id=-1, location='')
        for i, site in enumerate((cls.a, cls.b, cls.c, cls.d), 1):
            cell = Cell.objects.create(site=site, cell_id=site.site_id, cell_name=f'cell-{site.site_id}', technology='4G',
                band='B3', frequency=1800, azimuth=0, antenna_height_m=25)
            MAOSMonthlyKPI.objects.create(cell=cell, month_date=date(2024, 1, 1), active_users_avg=i,
                traffic_user_avg=10 * i, border_user_avg=i, border_user_max=2 * i, lowlatency_user_avg=0,
                thrp_bits_dl=8e9 * i, prb_dl_available=25 * i, prb_dl_used_avg=10,
                cqi_weighted_sum=30 * i, cqi_sample_count=3 * i,
                thrp_bits_dl_last_tti=0, thrp_time_dl_ms=100 * i,
                dl_packet_delay_time_ms=100 * i, dl_packet_delay_packets=10 * i,
                observation_duration_s=100, cell_unavail_duration_s=1)
            MAOSMonthlyKPI.objects.create(cell=cell, month_date=date(2024, 2, 1), active_users_avg=0, thrp_bits_dl=0)

    def test_raw_filters_dates_and_stable_pagination(self):
        data, status = explore({'dataset': 'raw', 'cluster_id': '1', 'month_from': '2024-01', 'month_to': '2024-01',
                                'columns': 'active_users_avg,thrp_bits_dl', 'page_size': '1', 'page': '2'})
        self.assertEqual(status, 200)
        self.assertEqual(data['count'], 2)
        self.assertEqual(data['rows'][0]['site_id'], 'b')
        self.assertEqual(data['rows'][0]['active_users_avg'], 2)

    def test_cluster_sums_pooled_ratios_and_noise_singletons(self):
        data, status = explore({'dataset': 'calculated', 'scope': 'cluster', 'month_to': '2024-01',
                                'columns': ','.join(metadata()['datasets']['calculated'][i]['key'] for i in range(11))})
        self.assertEqual(status, 200)
        self.assertEqual(data['count'], 3)
        row = next(r for r in data['rows'] if r['cluster_id'] == 1)
        self.assertEqual(row['active_users_avg'], 3)
        self.assertEqual(row['thrp_dl_gb'], 3)
        self.assertAlmostEqual(row['prb_util_dl_pct'], 100 * 20 / 75)
        self.assertEqual(row['cqi_avg'], 10)
        self.assertEqual(row['edge_user_share'], .1)
        self.assertEqual(row['edge_user_peak_ratio'], 2)
        self.assertEqual(row['lowlatency_user_share'], 0)
        self.assertEqual(row['dl_packet_delay_ms'], 10)
        self.assertEqual(row['cell_availability_pct'], 99)
        self.assertEqual(row['reporting_cells'], 2)
        self.assertEqual({r['site_id'] for r in data['rows'] if r['cluster_id'] == -1}, {'c', 'd'})

    def test_missing_zero_and_calculated_value_filter(self):
        data, status = explore({'dataset': 'calculated', 'month_from': '2024-02', 'columns': 'active_users_avg,prb_util_dl_pct',
                                'value_field': 'prb_util_dl_pct', 'value_op': 'missing'})
        self.assertEqual(status, 200)
        self.assertEqual(data['count'], 4)
        self.assertTrue(all(r['active_users_avg'] == 0 and r['prb_util_dl_pct'] is None for r in data['rows']))
        data, status = explore({'dataset': 'calculated', 'columns': 'prb_util_dl_pct', 'value_field': 'prb_util_dl_pct', 'value_op': 'gte', 'value': '30'})
        self.assertEqual(status, 200)
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['rows'][0]['site_id'], 'a')

    def test_tier_origin_is_required_and_excluded_from_neighbors(self):
        self.assertEqual(explore({'dataset': 'calculated', 'scope': 'tier1'})[1], 400)
        data, status = explore({'dataset': 'calculated', 'scope': 'tier1', 'origin_site_id': 'a', 'month_to': '2024-01'})
        self.assertEqual(status, 200)
        self.assertEqual(data['rows'][0]['active_users_avg'], 2)
        self.assertEqual(data['rows'][0]['reporting_sites'], 1)

    def test_invalid_parameters_and_unknown_columns(self):
        for params in ({'dataset': 'bad'}, {'page': '0'}, {'page_size': '201'}, {'columns': 'password'},
                       {'technology': '5G'}, {'month_from': '2024-02-02'}, {'month_from': '2024-04', 'month_to': '2024-03'},
                       {'value_field': 'active_users_avg', 'value': 'NaN'}):
            self.assertEqual(explore(params)[1], 400, params)
        self.assertEqual(self.client.get('/api/similarity/features/', {'representation': 'bad'}).status_code, 400)
        self.assertEqual(self.client.get('/api/explore/', {'dataset': 'bad'}).status_code, 400)
        self.assertEqual(self.client.get('/api/explore/metadata/').status_code, 200)

    @patch('services.models.similarity.api.candidate_context')
    @patch('services.models.similarity.api.build_site_similarity_vector')
    def test_pca_picker_search_and_fit_identity_use_same_dimensions(self, build, context):
        query = {'site_id': 'a', 'event_type': 'CELL_ADDED', 'sector_count_after': 2,
                 'total_prb_available': 80, 'population_tier1': 600}
        build.return_value = query
        sites = [self.b, self.c, self.d]
        vectors = [{**query, 'site_id': site.site_id, 'sector_count_after': i,
                    'total_prb_available': 40 * i, 'population_tier1': 300 * i} for i, site in enumerate(sites, 1)]
        context.return_value = sites, vectors, 3
        response = self.client.get('/api/similarity/features/', {'site_id': 'a', 'representation': 'pca'})
        self.assertEqual(response.status_code, 200)
        options = response.json()
        self.assertTrue(options['pca']['available'])
        selected = ','.join(f['key'] for f in options['features'] if f['available'] and f['default_selected'])
        params = {'site_id': 'a', 'representation': 'pca', 'features': selected, 'pca_fit_id': options['pca']['fit_id']}
        response = self.client.get('/api/similarity/search/', params)
        self.assertEqual(response.status_code, 200)
        ranked = response.json()
        self.assertEqual(ranked['representation'], 'pca')
        self.assertEqual(ranked['returned_count'], 3)
        self.assertIn('PC1', ranked['query']['dimension_values'])
        self.assertIn('PC1', ranked['cases'][0]['dimension_values'])
        self.assertAlmostEqual(sum(ranked['cases'][0]['feature_weights'].values()), 1)
        self.assertEqual(self.client.get('/api/similarity/search/', {**params, 'pca_fit_id': 'outdated'}).status_code, 409)
        self.assertEqual(self.client.get('/api/similarity/search/', {**params, 'features': 'PC999'}).status_code, 400)

    @patch('services.data_explorer.build_site_similarity_vector')
    def test_feature_filters_preserve_cutoffs_and_nulls(self, build):
        def profile(site, as_of_date=None, **kwargs):
            return {'feature_as_of_date': str(as_of_date), 'population_tier1': None if site.site_id == 'a' else 0}
        build.side_effect = profile
        data, status = explore({'dataset': 'features', 'columns': 'population_tier1', 'as_of': '2024-03',
            'value_field': 'population_tier1', 'value_op': 'missing'})
        self.assertEqual(status, 200)
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['rows'][0]['site_id'], 'a')
        self.assertIsNone(data['rows'][0]['population_tier1'])
        self.assertEqual(data['rows'][0]['as_of'], '2024-03-01')
