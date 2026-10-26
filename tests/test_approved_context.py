from datetime import date
from unittest.mock import patch
from django.test import TestCase

from core.models import Site, Cell, MAOSMonthlyKPI, RadioNetworkEvent, ClutterFeatures, GeometricFeatures
from services.models.features.approved_context import (
    post_event_configuration, static_context, cluster_prelaunch_values, terrain_relief,
)
from services.models.similarity.gower_distance import GowerDistance
from services.models.similarity.weighting import pair_weights

NOV=date(2023,11,1)
DEC=date(2023,12,1)
JAN=date(2024,1,1)


class ApprovedContextTests(TestCase):
    def site(self,key,lat=35,cluster=7):
        return Site.objects.create(site_id=key,site_name=key,latitude=lat,longitude=9,location='',cluster_id=cluster)

    def cell(self,site,key,azimuth=0,height=25):
        return Cell.objects.create(site=site,cell_id=key,cell_name=key,technology='4G',
            band='B3',frequency=1800,azimuth=azimuth,antenna_height_m=height)

    def test_after_cells_join_plan_wrap_sectors_and_ignore_later_prb(self):
        site=self.site('query')
        old=self.cell(site,'old',0,0)
        wrapped=self.cell(site,'wrapped',360,0)
        added=self.cell(site,'added',120,0)
        future=self.cell(site,'future',240,50)
        for cell in (old,wrapped):
            MAOSMonthlyKPI.objects.create(cell=cell,month_date=NOV,thrp_bits_dl=1,prb_dl_available=25)
        MAOSMonthlyKPI.objects.create(cell=added,month_date=DEC,thrp_bits_dl=1,prb_dl_available=55)
        MAOSMonthlyKPI.objects.create(cell=future,month_date=JAN,thrp_bits_dl=1,prb_dl_available=100)
        MAOSMonthlyKPI.objects.create(cell=old,month_date=JAN,thrp_bits_dl=999,prb_dl_available=100)
        RadioNetworkEvent.objects.create(site=site,event_key='add',event_type='CELL_ADDED',effective_date=DEC,
            detector_version='test',details={'cell_ids':['added'],'cell_activation_months':{'added':DEC.isoformat()}})
        result=post_event_configuration(site,DEC)
        self.assertEqual(result['sector_count_after'],2)
        self.assertEqual(result['cells_per_sector_after'],1.5)
        self.assertEqual(result['total_bw_after_mhz'],20)
        self.assertEqual(result['total_prb_available'],105)
        self.assertEqual(result['antenna_height_m'],25)
        self.assertNotIn('future',result['post_event_configuration_support']['cell_ids'])

    def test_missing_prb_is_not_imputed_to_zero_or_plan_bandwidth(self):
        site=self.site('missing')
        cell=self.cell(site,'missing')
        MAOSMonthlyKPI.objects.create(cell=cell,month_date=NOV,thrp_bits_dl=1,prb_dl_available=None)
        result=post_event_configuration(site,DEC)
        self.assertIsNone(result['total_bw_after_mhz'])
        self.assertIsNone(result['total_prb_available'])

    def test_measured_zero_prb_capacity_does_not_fall_back_to_older_positive_value(self):
        site=self.site('zero')
        cell=self.cell(site,'zero')
        MAOSMonthlyKPI.objects.create(cell=cell,month_date=NOV,thrp_bits_dl=1,prb_dl_available=25)
        MAOSMonthlyKPI.objects.create(cell=cell,month_date=DEC,thrp_bits_dl=0,prb_dl_available=0)
        values=post_event_configuration(site,DEC)
        self.assertEqual(values['total_prb_available'],0)
        self.assertIsNone(values['total_bw_after_mhz'])

    def test_cluster_previous_month_sums_users_and_pools_ratios(self):
        a=self.site('a')
        b=self.site('b',35.005)
        first=self.cell(a,'a')
        second=self.cell(b,'b')
        for cell,users,used,available,cqi_sum,samples in [(first,3,1,10,10,10),(second,7,81,90,15,1)]:
            MAOSMonthlyKPI.objects.create(cell=cell,month_date=NOV,thrp_bits_dl=8e9,active_users_avg=users,
                prb_dl_used_avg=used,prb_dl_available=available,cqi_weighted_sum=cqi_sum,cqi_sample_count=samples)
        MAOSMonthlyKPI.objects.create(cell=second,month_date=DEC,thrp_bits_dl=1e15,active_users_avg=999)
        values=cluster_prelaunch_values(a,DEC,{})
        self.assertEqual(values['avg_users'],10)
        self.assertEqual(values['cluster_avg_users'],10)
        self.assertEqual(values['avg_traffic_dl_gb'],2)
        self.assertEqual(values['avg_prb_util_pct'],82)
        self.assertAlmostEqual(values['avg_cqi'],25/11)
        self.assertEqual(values['cluster_prelaunch_support']['month'],NOV.isoformat())

    def test_noise_cluster_is_independent_and_missing_month_stays_null(self):
        a=self.site('a',cluster=-1)
        b=self.site('b',cluster=-1)
        for site,users in [(a,3),(b,99)]:
            cell=self.cell(site,site.site_id)
            MAOSMonthlyKPI.objects.create(cell=cell,month_date=NOV,active_users_avg=users)
        self.assertEqual(cluster_prelaunch_values(a,DEC,{})['avg_users'],3)
        self.assertIsNone(cluster_prelaunch_values(a,date(2023,11,1),{})['avg_users'])

    def test_static_absolute_elevation_adds_ground_building_and_mast_once(self):
        a=self.site('a')
        b=self.site('b',35.005)
        self.cell(a,'a',height=0)
        self.cell(b,'b',height=30)
        for site,height in [(a,18),(b,8)]:
            ClutterFeatures.objects.create(site=site,dominant_clutter='urban',clutter_entropy_2km=1,
                pct_building_area_1km=5,avg_building_height_m=height)
        with patch('services.models.features.approved_context.ground_elevation',side_effect=lambda lat,lon:100 if lat==35 else 200):
            context=static_context(a,{})
        self.assertEqual(context['z_antenna_m'],143)
        self.assertEqual(context['neighbor_avg_antenna_height_m'],238)
        self.assertEqual(context['cluster_id'],7)

    def test_relief_classes_and_display_ids_never_change_distance(self):
        self.assertEqual([terrain_relief(slope) for slope in (1,2,5,15)],['flat','rolling','hilly','steep'])
        self.assertIsNone(terrain_relief(None))
        distance=GowerDistance(feature_ranges={'n_sites_2km':(0,10)})
        query={'cluster_id':1,'n_sites_2km':3,'avg_users':10,'cluster_avg_users':10}
        candidate={'cluster_id':99,'n_sites_2km':3,'avg_users':10,'cluster_avg_users':999}
        self.assertEqual(distance.compute_distance(query,candidate),0)
        weights=pair_weights(distance,query,candidate,['n_sites_2km'],'equal_per_feature')
        self.assertNotIn('cluster_id',weights)
        self.assertNotIn('cluster_avg_users',weights)

    def test_cluster_members_follow_site_labels_even_when_sites_are_colocated(self):
        from services.models.similarity.historical import cluster_members
        origin=self.site('origin',cluster=7)
        same=self.site('same',cluster=7)
        other=self.site('other',cluster=8)
        network={site.site_id:{'site_id':site.site_id,'latitude':site.latitude,'longitude':site.longitude}
                 for site in (same,other)}
        self.assertEqual({row['site_id'] for row in cluster_members(origin,network)},{'origin','same'})
        origin.cluster_id=-1
        self.assertEqual([row['site_id'] for row in cluster_members(origin,network)],['origin'])
