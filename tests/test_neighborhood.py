from datetime import date
import math
from unittest.mock import patch
from django.test import TestCase,SimpleTestCase
from core.models import Site,Cell,MAOSMonthlyKPI,RadioNetworkEvent
from services.models.features.neighborhood import (
    tier,bin_and_bearing,select_virtual,neighborhood,public_context,
    reconcile_locations,refresh_current,scheme,
    sample_series,
)
from services.models.similarity.engine import rank_similar_cases
from services.models.similarity.pca import prepare_pca

JUN=date(2025,6,1)
MAY=date(2025,5,1)
APR=date(2025,4,1)


class NeighborhoodGeometryTests(SimpleTestCase):
    def test_exact_distance_and_bearing_boundaries(self):
        self.assertIsNone(tier(49.999,'extended'))
        self.assertEqual(tier(50,'extended'),'tier1')
        self.assertEqual(tier(4999.999,'extended'),'tier1')
        self.assertEqual(tier(5000,'extended'),'tier2')
        self.assertIsNone(tier(10000,'extended'))
        self.assertEqual(tier(2000,'standard'),'tier1')
        self.assertEqual(tier(2000.001,'standard'),'tier2')
        self.assertEqual(tier(5000,'standard'),'tier2')
        self.assertEqual(bin_and_bearing(30),(1,30))
        self.assertEqual(bin_and_bearing(359.9999999),(0,0))
        self.assertEqual(bin_and_bearing(-30),(11,330))

    def test_same_metre_numeric_tie_and_maximum_twelve(self):
        candidates=[{'site_id':str(i),'distance_m':100+i,'bearing_deg':i*30} for i in range(12)]
        candidates += [{'site_id':'100','distance_m':500,'bearing_deg':30},
                       {'site_id':'2','distance_m':100.4,'bearing_deg':30},
                       {'site_id':'10','distance_m':100.1,'bearing_deg':30},
                       {'site_id':'-100','distance_m':49,'bearing_deg':30}]
        selected=select_virtual(candidates)
        self.assertEqual(len(selected),12)
        self.assertEqual(next(m['site_id'] for m in selected if m['bin']==1),'2')
        self.assertEqual(select_virtual([{'site_id':'1','distance_m':10000,'bearing_deg':0}]),[])

    def test_original_and_pca_partitions_never_relax_across_schemes(self):
        query={'site_id':'q','tier_scheme':'extended','event_type':'CELL_ADDED','n_sites_2km':2,'population_tier1':8}
        candidates=[{**query,'site_id':str(i),'tier_scheme':'standard','n_sites_2km':i,'population_tier1':i*i} for i in range(6)]
        candidates.append({**query,'site_id':'allowed','event_type':'OTHER','n_sites_2km':3})
        rank=rank_similar_cases(query,candidates,selected_features=['n_sites_2km'])
        self.assertEqual([r['features']['site_id'] for r in rank['cases']],['allowed'])
        prepared=prepare_pca(query,candidates)
        self.assertEqual(prepared['report']['candidate_pool_size'],1)
        self.assertFalse(prepared['report']['available'])


class NeighborhoodDataTests(TestCase):
    def site(self,key,lat=35,lon=9,cluster=-1,launch=None):
        return Site.objects.create(site_id=key,site_name='Site '+key,latitude=lat,longitude=lon,
            location='',cluster_id=cluster,launch_date=launch,is_launched=launch is not None)

    def traffic(self,site,month=MAY,bits=8e9,technology='4G'):
        cell=Cell.objects.create(site=site,cell_id=f'{site.site_id}-{month}',cell_name=f'{site.site_id}-{month}',
            technology=technology,band='B3',frequency=1800,azimuth=0,antenna_height_m=25)
        return MAOSMonthlyKPI.objects.create(cell=cell,month_date=month,thrp_bits_dl=bits)

    def test_real_label_propagation_preserves_original_rows_and_noise(self):
        real=self.site('10',cluster=7)
        alias=self.site('11',lat=35.00001)
        noise=self.site('20',lat=35.1)
        report=reconcile_locations()
        alias.refresh_from_db();noise.refresh_from_db()
        self.assertEqual(report['changed_labels'],1)
        self.assertEqual(alias.cluster_id,7)
        self.assertEqual(alias.original_cluster_id,-1)
        self.assertEqual(alias.canonical_site_id,'10')
        self.assertEqual(alias.tier_scheme,'standard')
        self.assertEqual(noise.cluster_id,-1)
        self.assertEqual(noise.tier_scheme,'extended')
        self.assertEqual(Site.objects.count(),3)
        reconcile_locations()
        alias.refresh_from_db()
        self.assertEqual(alias.original_cluster_id,-1)

    def test_ambiguous_real_labels_are_rejected_without_mutation(self):
        self.site('a',cluster=7);self.site('b',cluster=8)
        with self.assertRaises(ValueError):
            reconcile_locations()
        self.assertEqual(Site.objects.get(site_id='b').cluster_id,8)

    def test_one_per_bin_recency_and_same_month_launch_filter(self):
        origin=self.site('origin')
        near=self.site('2',lat=35.01,launch=APR)
        far=self.site('3',lat=35.03)
        recent=self.site('4',lon=9.07,launch=MAY)
        same_month=self.site('5',lat=34.99,launch=JUN)
        zero=self.site('6',lon=8.99)
        colocated=self.site('7',lat=35.00001)
        for site in (near,far,recent,same_month,colocated):
            self.traffic(site)
        self.traffic(zero,bits=0)
        before=public_context(origin,JUN,{})
        self.assertEqual({m['site_id'] for m in before['vis_members']},{'2','4'})
        self.assertEqual(before['support_level'],'low')
        self.assertTrue(all(m['member_recent_launch'] for m in before['vis_members']))
        self.assertEqual(before['virtual_id'],'V_origin')
        self.assertEqual(before['cluster_id'],-1)
        self.traffic(zero,month=JUN,bits=1e20)
        self.assertEqual(before,public_context(origin,JUN,{}))

    def test_traffic_sample_mean_and_complete_total_are_distinct(self):
        origin=self.site('origin')
        near=self.site('a',lat=35.01)
        far=self.site('b',lat=35.02)
        east=self.site('c',lon=9.03)
        for site,bits in ((near,8e9),(far,16e9),(east,24e9)):
            self.traffic(site,bits=bits)
        value=public_context(origin,JUN,{})
        self.assertEqual(value['vis_n_members'],2)
        self.assertEqual(value['vis_sampled_traffic_gb'],4)
        self.assertEqual(value['vis_mean_traffic_per_member_gb'],2)
        self.assertEqual(value['traffic_all_sites_within_R'],6)
        self.assertEqual(neighborhood(origin,JUN,{})['scopes']['cluster'],[])

    def test_missing_previous_month_stays_null_and_only_lte_traffic_qualifies(self):
        origin=self.site('origin')
        past=self.site('past',lat=35.01)
        other_tech=self.site('3g',lon=9.02)
        self.traffic(past,month=APR)
        self.traffic(other_tech,technology='3G')
        value=public_context(origin,JUN,{})
        self.assertEqual(value['vis_n_members'],1)
        self.assertIsNone(value['vis_sampled_traffic_gb'])
        self.assertIsNone(value['traffic_all_sites_within_R'])

    def test_isolated_zero_bins_has_no_synthetic_cluster_or_zero_traffic(self):
        origin=self.site('origin')
        value=public_context(origin,JUN,{})
        self.assertEqual(value['vis_n_bins_filled'],0)
        self.assertEqual(value['support_level'],'isolated')
        self.assertIsNone(value['virtual_id'])
        self.assertIsNone(value['vis_sampled_traffic_gb'])

    def test_global_nearest_feature_survives_beyond_virtual_radius(self):
        origin=self.site('origin');far=self.site('far',lat=35.2)
        self.traffic(far)
        value=public_context(origin,JUN,{})
        self.assertEqual(value['vis_n_members'],0)
        self.assertGreater(value['nearest_eligible_site_m'],10000)

    def test_current_snapshot_is_stored_but_event_context_is_rebuilt(self):
        origin=self.site('origin')
        peer=self.site('peer',lat=35.01)
        self.traffic(peer,month=JUN)
        refresh_current()
        origin.refresh_from_db()
        self.assertEqual(origin.vis_n_members,1)
        self.assertEqual(origin.vis_snapshot_kind,'current')
        self.assertEqual(origin.vis_snapshot_cutoff,date(2025,7,1))
        self.assertEqual(public_context(origin,JUN,{})['vis_n_members'],0)
        self.assertEqual(origin.cluster_id,-1)

    def test_sample_series_preserves_missing_members_and_true_zero(self):
        a=self.site('a',lat=35.01);b=self.site('b',lon=9.01)
        self.traffic(a,month=APR,bits=0)
        self.traffic(a,month=MAY,bits=0);self.traffic(b,month=MAY,bits=0)
        members=[{'site_id':'a','site_ids':['a']},{'site_id':'b','site_ids':['b']}]
        rows=sample_series(members)
        self.assertIsNone(rows[0]['thrp_dl_gb'])
        self.assertEqual(rows[0]['reporting_members'],1)
        self.assertEqual(rows[1]['thrp_dl_gb'],0)
        self.assertEqual(rows[1]['vis_mean_traffic_per_member_gb'],0)

    def test_cbr_tiers_and_distance_bands_use_same_event_membership(self):
        from services.models.prediction.cbr_impact import _scope_members
        origin=self.site('origin')
        peers=[self.site('near',lat=35.009),self.site('middle',lat=35.027),self.site('far',lat=35.063)]
        for peer in peers:
            self.traffic(peer)
        scopes,_=_scope_members(origin,[origin]+peers,{},JUN,{})
        self.assertEqual(set(scopes['tier1']),{'near','middle'})
        self.assertEqual(scopes['tier2'],['far'])
        self.assertEqual(scopes['distance_0_2'],['near'])
        self.assertEqual(scopes['distance_2_5'],['middle'])
        self.assertEqual(scopes['distance_5_10'],['far'])
        self.assertEqual(scopes['virtual_cluster'],['near'])
        self.assertEqual(scopes['cluster'],[])
        origin.cluster_id=7
        scopes,_=_scope_members(origin,[origin]+peers,{},JUN,{})
        self.assertEqual(scopes['tier1'],['near'])
        self.assertEqual(scopes['tier2'],['middle'])
        self.assertEqual(scopes['virtual_cluster'],[])

    def test_active_users_without_positive_lte_traffic_do_not_qualify(self):
        origin=self.site('origin');peer=self.site('peer',lat=35.01)
        row=self.traffic(peer,bits=0)
        row.active_users_avg=100;row.cqi_avg=10;row.save()
        self.assertEqual(neighborhood(origin,JUN,{})['vis_n_members'],0)

    def test_map_links_use_virtual_sample_for_noise_and_full_tiers_for_standard(self):
        origin=self.site('origin')
        for key,latitude in [('near',35.01),('middle',35.03),('far',35.06)]:
            self.traffic(self.site(key,lat=latitude))
        response=self.client.get('/api/sites/origin/map-links/')
        self.assertEqual(response.status_code,200)
        data=response.json()
        self.assertEqual(data['cluster_id'],-1)
        self.assertEqual(data['link_scope'],'virtual_cluster')
        self.assertEqual([m['site_id'] for m in data['members']],['near'])
        self.assertEqual(data['members'][0]['tier'],'tier1')
        origin.cluster_id=7;origin.save()
        data=self.client.get('/api/sites/origin/map-links/').json()
        self.assertEqual(data['link_scope'],'tiers')
        self.assertEqual({m['site_id'] for m in data['members']},{'near','middle'})
        self.assertEqual({m['tier'] for m in data['members']},{'tier1','tier2'})
        self.assertEqual(data['membership_kind'],'current')

    def test_future_launch_metadata_cannot_change_earlier_membership_flags(self):
        origin=self.site('origin');peer=self.site('peer',lat=35.01)
        self.traffic(peer)
        before=public_context(origin,JUN,{})
        peer.launch_date=date(2025,9,1);peer.is_launched=True;peer.save()
        self.assertEqual(before,public_context(origin,JUN,{}))

    def test_feature_api_exposes_mandatory_scheme_and_current_event_versions(self):
        origin=self.site('origin');peer=self.site('peer',lat=35.01)
        self.traffic(peer)
        with patch('services.models.similarity.feature_vector.population_features',return_value={}):
            response=self.client.get('/api/similarity/features/',{'site_id':'origin'})
        self.assertEqual(response.status_code,200)
        data=response.json()
        self.assertEqual(data['tier_scheme'],'extended')
        policy=next(f for f in data['features'] if f['key']=='tier_scheme')
        self.assertFalse(policy['selectable'])
        self.assertEqual(data['neighborhood']['cluster_id'],-1)
        self.assertEqual(data['neighborhood']['vis_n_members'],1)

    def test_selected_event_endpoint_rebuilds_membership_and_rejects_foreign_events(self):
        origin=self.site('origin');peer=self.site('peer',lat=35.01)
        self.traffic(peer)
        for key,month in [('early',JUN),('late',date(2025,9,1))]:
            RadioNetworkEvent.objects.create(site=origin,event_key=key,event_type='CELL_ADDED',effective_date=month,
                detector_version='fixture',details={'cell_ids':[],'technologies':['4G'],'bands':[]})
        early=self.client.get('/api/sites/origin/neighborhood/',{'event_key':'early'})
        late=self.client.get('/api/sites/origin/neighborhood/',{'event_key':'late'})
        self.assertEqual(early.status_code,200)
        self.assertEqual(late.status_code,200)
        self.assertEqual(early.json()['event']['vis_n_members'],1)
        self.assertEqual(late.json()['event']['vis_n_members'],0)
        self.assertEqual(self.client.get('/api/sites/peer/neighborhood/',{'event_key':'early'}).status_code,404)
        self.assertEqual(self.client.get('/api/sites/origin/neighborhood/',{'as_of':'2025-06-02'}).status_code,400)
        from services.models.prediction.cbr_impact import build_cbr_impact_prediction
        with patch('services.models.prediction.cbr_impact.build_site_similarity_vector',return_value={'tier_scheme':'extended','feature_timing_note':'fixture'}):
            predicted=build_cbr_impact_prediction('origin',event_key='late')
        self.assertEqual(predicted['query']['event_date'],'2025-09-01')
        self.assertEqual(predicted['neighborhood']['vis_n_members'],0)
