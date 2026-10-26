from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from django.test import TestCase
from core.models import Site, Cell, MAOSMonthlyKPI, UserContextFeatures
from services.models.features.maos_context import (
    monthly_series, scope_members, calculate_user_context, save_user_context, USER_CONTEXT_FIELDS,
)
from services.models.preprocessing.maos_report_loader import MAOSReportLoader
from services.models.similarity.gower_distance import GowerDistance


class UserContextTests(TestCase):
    def site(self,key,latitude,cluster=7,traffic=100,border=20,peak=50,low=10):
        site=Site.objects.create(site_id=key,site_name=key,location='',latitude=latitude,longitude=9,cluster_id=cluster)
        cell=Cell.objects.create(site=site,cell_id=key,cell_name=key,technology='4G',frequency=1800,band='B3',azimuth=0,antenna_height_m=25)
        MAOSMonthlyKPI.objects.create(cell=cell,month_date=date(2025,5,1),traffic_user_avg=traffic,
            border_user_avg=border,border_user_max=peak,lowlatency_user_avg=low,thrp_bits_dl=10)
        return site,cell

    def setUp(self):
        self.origin,self.origin_cell=self.site('origin',35)
        self.a,self.a_cell=self.site('a',35.005,traffic=10,border=8,peak=16,low=1)
        self.b,self.b_cell=self.site('b',35.01,traffic=90,border=9,peak=27,low=9)
        self.c,self.c_cell=self.site('c',35.025,traffic=200,border=10,peak=30,low=20)

    def test_sum_over_sum_not_mean_of_ratios(self):
        row=monthly_series(['a','b'])[0]
        self.assertAlmostEqual(row['edge_user_share'],17/100)
        self.assertAlmostEqual(row['edge_user_peak_ratio'],43/17)
        self.assertAlmostEqual(row['lowlatency_user_share'],10/100)

    def test_active_users_sum_cells_for_every_scope_and_cbr(self):
        from services.models.prediction.cbr_impact import _month_rows, _row_value
        for cell, users in [(self.origin_cell, 11), (self.a_cell, 3), (self.b_cell, 7), (self.c_cell, 19)]:
            MAOSMonthlyKPI.objects.filter(cell=cell).update(active_users_avg=users)
        extra = Cell.objects.create(site=self.a, cell_id='extra', cell_name='extra', technology='4G',
            frequency=1800, band='B3', azimuth=120, antenna_height_m=25)
        MAOSMonthlyKPI.objects.create(cell=extra, month_date=date(2025,5,1), active_users_avg=13)
        scopes = {'site':['origin'], **scope_members(self.origin)}
        for scope, expected in [('site',11), ('tier1',23), ('tier2',19), ('cluster',53)]:
            self.assertEqual(monthly_series(scopes[scope])[0]['active_users_avg'], expected)
        self.assertEqual(_row_value(_month_rows()['a'][date(2025,5,1)], 'active_users'),16)
        MAOSMonthlyKPI.objects.filter(cell__site=self.a).update(active_users_avg=None)
        self.assertIsNone(monthly_series(['a'])[0]['active_users_avg'])
        MAOSMonthlyKPI.objects.filter(cell=extra).update(active_users_avg=0)
        self.assertEqual(monthly_series(['a'])[0]['active_users_avg'],0)

    def test_nonadditive_counters_use_pooled_components(self):
        MAOSMonthlyKPI.objects.filter(cell=self.a_cell).update(prb_dl_used_avg=1, prb_dl_available=10,
            cqi_weighted_sum=10,cqi_sample_count=10,dl_packet_delay_time_ms=20,dl_packet_delay_packets=10,
            thrp_bits_dl=110,thrp_bits_dl_last_tti=10,thrp_time_dl_ms=10,
            cell_unavail_duration_s=10,observation_duration_s=100)
        MAOSMonthlyKPI.objects.filter(cell=self.b_cell).update(prb_dl_used_avg=81, prb_dl_available=90,
            cqi_weighted_sum=15,cqi_sample_count=1,dl_packet_delay_time_ms=900,dl_packet_delay_packets=90,
            thrp_bits_dl=1820,thrp_bits_dl_last_tti=20,thrp_time_dl_ms=90,
            cell_unavail_duration_s=0,observation_duration_s=900)
        row=monthly_series(['a','b'])[0]
        for field, expected in [('prb_util_dl_pct',82),('cqi_avg',25/11),
            ('dl_packet_delay_ms',9.2),('dl_throughput_kbps',19),('cell_availability_pct',99)]:
            self.assertAlmostEqual(row[field],expected)

    def test_pairwise_missing_counter_omits_its_denominator(self):
        MAOSMonthlyKPI.objects.filter(cell=self.b_cell).update(border_user_avg=None)
        row=monthly_series(['a','b'])[0]
        self.assertAlmostEqual(row['edge_user_share'],8/10)
        self.assertEqual(row['edge_user_peak_ratio'],2)
        self.assertEqual(row['lowlatency_user_share'],.1)

    def test_zero_numerator_is_zero_but_zero_denominator_is_unavailable(self):
        MAOSMonthlyKPI.objects.filter(cell=self.a_cell).update(border_user_avg=0,border_user_max=0,lowlatency_user_avg=None)
        row=monthly_series(['a'])[0]
        self.assertEqual(row['edge_user_share'],0)
        self.assertIsNone(row['edge_user_peak_ratio'])
        self.assertIsNone(row['lowlatency_user_share'])
        self.assertEqual(row['user_ratio_support']['edge_user_peak_ratio']['unavailable_reason'],'zero_denominator')
        self.assertEqual(row['user_ratio_support']['lowlatency_user_share']['unavailable_reason'],'no_paired_counters')

    def test_tiers_are_disjoint_and_total_cluster_includes_origin(self):
        scopes=scope_members(self.origin)
        self.assertEqual(set(scopes['tier1']),{'a','b'})
        self.assertEqual(scopes['tier2'],['c'])
        row=monthly_series(scopes['cluster'])[0]
        self.assertAlmostEqual(row['edge_user_share'],47/400)
        self.assertAlmostEqual(row['edge_user_peak_ratio'],123/47)

    def test_noise_sites_do_not_share_one_cluster(self):
        noise,_=self.site('noise',35.05,cluster=-1)
        self.site('other_noise',35.06,cluster=-1)
        self.assertEqual(scope_members(noise)['cluster'],['noise'])

    def test_profiles_exclude_event_month_and_later_counters(self):
        cutoff=date(2025,6,1)
        before=calculate_user_context(self.origin,cutoff)
        MAOSMonthlyKPI.objects.create(cell=self.a_cell,month_date=cutoff,traffic_user_avg=1,border_user_avg=999,border_user_max=9999,lowlatency_user_avg=999,thrp_bits_dl=1e12)
        after=calculate_user_context(self.origin,cutoff)
        self.assertEqual(before,after)
        self.assertAlmostEqual(before['tier1_edge_user_share'],.17)
        self.assertAlmostEqual(before['tier2_edge_user_peak_ratio'],3)

    def test_three_month_profile_pools_raw_components_not_monthly_ratios(self):
        MAOSMonthlyKPI.objects.create(cell=self.a_cell,month_date=date(2025,3,1),traffic_user_avg=900,border_user_avg=90,border_user_max=270,lowlatency_user_avg=90)
        values=calculate_user_context(self.origin,date(2025,6,1))
        self.assertAlmostEqual(values['tier1_edge_user_share'],107/1000)
        self.assertAlmostEqual(values['tier1_edge_user_peak_ratio'],313/107)

    def test_profile_persistence_and_similarity_registry(self):
        self.origin.is_launched=True
        self.origin.launch_date=date(2025,6,15)
        self.origin.save()
        values=save_user_context(self.origin)
        stored=UserContextFeatures.objects.get(site=self.origin)
        self.assertEqual(stored.profile_as_of_date,date(2025,6,1))
        self.assertAlmostEqual(stored.tier1_edge_user_share,.17)
        self.assertTrue(set(USER_CONTEXT_FIELDS).issubset(GowerDistance.NUMERIC_FEATURES))
        self.assertEqual(GowerDistance()._get_feature_group('cluster_edge_user_share'),'user_context')

    def test_targeted_import_preserves_other_counters(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'monthly.csv'
            path.write_text('metadata\n'*6+'Date,Cell Name,L.Traffic.User.Avg,L.Traffic.User.BorderUE.Avg,L.Traffic.User.BorderUE.Max,L.Traffic.User.LowLatency.Avg\n05-2025,origin,20,4,12,2\n',encoding='utf-8')
            stats=MAOSReportLoader(path).import_user_counters()
        row=MAOSMonthlyKPI.objects.get(cell=self.origin_cell)
        self.assertEqual(stats['rows_updated'],1)
        self.assertEqual(row.border_user_avg,4)
        self.assertEqual(row.border_user_max,12)
        self.assertEqual(row.lowlatency_user_avg,2)
        self.assertEqual(row.thrp_bits_dl,10)

    def test_deselected_new_user_dimensions_do_not_change_distance(self):
        from services.models.similarity.engine import rank_similar_cases
        query={'n_sites_2km':2,'tier1_edge_user_share':.1}
        case={'n_sites_2km':2,'tier1_edge_user_share':.9}
        result=rank_similar_cases(query,[case],selected_features=['n_sites_2km'])
        self.assertEqual(result['cases'][0]['distance'],0)
        self.assertNotIn('tier1_edge_user_share',result['cases'][0]['used_features'])
