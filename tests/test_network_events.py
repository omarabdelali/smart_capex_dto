from datetime import date
from django.test import SimpleTestCase, TestCase

from core.models import Cell, MAOSMonthlyKPI, RadioNetworkEvent, Site
from services.models.preprocessing.network_events import (
    analyze_cell, bandwidth_from_prb, detect_and_save_events, effective_event_date,
    site_event_data, cluster_events,
)

OCT = date(2023,10,1)
NOV = date(2023,11,1)
DEC = date(2023,12,1)
JAN = date(2024,1,1)


class CellEvidenceTests(SimpleTestCase):
    def test_activation_is_positive_traffic_not_zero_or_other_kpi(self):
        state = analyze_cell([(OCT,0,100),(NOV,None,100),(DEC,2,100)],'4G',OCT)
        self.assertEqual(state['activation'],DEC)
        self.assertEqual(state['evidence'],'zero_to_positive')
        self.assertIsNone(analyze_cell([(OCT,None,100),(NOV,0,100)],'4G',OCT)['activation'])

    def test_left_censoring_and_unobserved_prehistory_are_explicit(self):
        self.assertEqual(analyze_cell([(OCT,1,25)],'4G',OCT)['evidence'],'baseline_left_censored')
        self.assertEqual(analyze_cell([(NOV,1,25)],'4G',OCT)['evidence'],'first_positive_observed')

    def test_prb_tolerance_inclusive_and_no_arbitrary_rounding(self):
        for prbs,bw in [(20,5),(30,5),(45,10),(55,10),(70,15),(80,15),(95,20),(105,20)]:
            self.assertEqual(bandwidth_from_prb(prbs),bw)
        for prbs in (None,0,31,44,56,69,81,94,106,float('nan')):
            self.assertIsNone(bandwidth_from_prb(prbs))

    def test_upgrade_waits_for_positive_traffic_and_downgrade_keeps_identity(self):
        state=analyze_cell([(OCT,1,25),(NOV,0,52),(DEC,2,49),(JAN,2,25)],'4G',OCT)
        up,down=state['bandwidth_changes']
        self.assertEqual((up['event_type'],up['effective_date'],up['previous_bandwidth_mhz'],up['new_bandwidth_mhz']),
                         ('BANDWIDTH_UPGRADE',DEC,5,10))
        self.assertEqual(up['details']['first_changed_prb_month'],NOV.isoformat())
        self.assertEqual((down['event_type'],down['effective_date']),('BANDWIDTH_DOWNGRADE',JAN))

    def test_gaps_unknown_prbs_and_jitter_do_not_invent_change_months(self):
        for rows in [[(OCT,1,25),(DEC,1,100)],[(OCT,1,25),(NOV,1,None),(DEC,1,100)],
                     [(OCT,1,24),(NOV,1,29),(DEC,1,20)]]:
            self.assertEqual(analyze_cell(rows,'4G',OCT)['bandwidth_changes'],[])
        self.assertEqual(analyze_cell([(OCT,1,25),(NOV,1,100)],'3G',OCT)['bandwidth_changes'],[])


class NetworkEventTests(TestCase):
    def setUp(self):
        self.site=Site.objects.create(site_id='event',site_name='Event site',location='',latitude=35,longitude=9,cluster_id=7)
        self.baseline_site=Site.objects.create(site_id='base',site_name='Baseline',location='',latitude=35,longitude=9)
        self.cell('baseline',self.baseline_site,active=OCT)

    def cell(self,key,site=None,tech='4G',band='B3',frequency=1800,active=None):
        cell=Cell.objects.create(site=site or self.site,cell_id=key,cell_name=key,technology=tech,
            band=band,frequency=frequency,azimuth=0,antenna_height_m=25)
        MAOSMonthlyKPI.objects.create(cell=cell,month_date=OCT,thrp_bits_dl=1 if active==OCT else 0,
                                     active_users_avg=100,prb_dl_available=25)
        if active and active!=OCT:
            MAOSMonthlyKPI.objects.create(cell=cell,month_date=active,thrp_bits_dl=10,prb_dl_available=25)
        return cell

    def events(self):
        detect_and_save_events()
        return list(RadioNetworkEvent.objects.filter(site=self.site,is_current=True))

    def test_site_action_does_not_swallow_a_later_technology_action(self):
        a=self.cell('a',active=NOV)
        b=self.cell('b',tech='3G',active=DEC)
        events=self.events()
        event=next(e for e in events if e.event_type=='SITE_ADDED')
        self.assertEqual((event.event_type,event.effective_date),('SITE_ADDED',NOV))
        self.assertEqual(event.details['cell_activation_months'],{'a':NOV.isoformat()})
        self.assertEqual([(e.event_type,e.effective_date) for e in events],
                         [('SITE_ADDED',NOV),('TECHNOLOGY_ADDED',DEC)])
        self.site.refresh_from_db()
        a.refresh_from_db()
        self.assertEqual(self.site.launch_date,NOV)
        self.assertEqual(a.launch_date,NOV)
        self.assertEqual(effective_event_date(self.site),NOV)
        self.assertIsNone(event.configuration_date)
        self.assertEqual(len(cluster_events(7)),2)
        from core.serializers.site_serializers import SiteGeoJSONSerializer
        from core.serializers.feature_serializers import SiteWithFeaturesSerializer
        self.assertIn('network_events',SiteWithFeaturesSerializer().fields)
        payload=SiteGeoJSONSerializer(self.site).data['properties']
        self.assertEqual(payload['launch_date'],NOV.isoformat())
        self.assertEqual(len(payload['network_events']),2)

    def test_technology_action_does_not_swallow_a_later_cell_action(self):
        self.cell('existing',tech='3G',active=OCT)
        self.cell('new_a',active=NOV)
        self.cell('new_b',active=DEC)
        events=self.events()
        event=events[0]
        self.assertEqual([(e.event_type,e.effective_date) for e in events],
                         [('TECHNOLOGY_ADDED',NOV),('CELL_ADDED',DEC)])
        self.assertEqual(event.details['label'],'4G_ADDED')
        self.assertFalse(Site.objects.get(pk=self.site.pk).is_launched)

    def test_complete_multiple_technologies_same_month_have_combined_label(self):
        self.cell('existing',active=OCT)
        self.cell('2g',tech='2G',active=NOV)
        self.cell('3g',tech='3G',active=NOV)
        event,=self.events()
        self.assertEqual(event.details['label'],'2G/3G_ADDED')

    def test_band_then_partial_band_falls_back_to_cell_without_duplicates(self):
        self.cell('existing',active=OCT)
        self.cell('partial',active=NOV)
        self.cell('band_a',band='B20',frequency=800,active=NOV)
        self.cell('band_b',band='B20',frequency=800,active=DEC)
        events=self.events()
        self.assertEqual({e.event_type for e in events},{'FREQUENCY_BAND_ADDED','CELL_ADDED'})
        ids=[key for e in events for key in e.details['cell_ids']]
        self.assertEqual(sorted(ids),['band_a','band_b','partial'])
        band=next(e for e in events if e.event_type=='FREQUENCY_BAND_ADDED')
        self.assertEqual(band.effective_date,NOV)

    def test_many_cells_at_existing_technology_are_one_monthly_action(self):
        self.cell('existing',active=OCT)
        self.cell('one',active=NOV)
        self.cell('two',active=NOV)
        self.cell('three',active=DEC)
        events=self.events()
        self.assertEqual([(e.event_type,e.effective_date) for e in events],
                         [('CELL_ADDED',NOV),('CELL_ADDED',DEC)])
        self.assertEqual(events[0].details['cell_ids'],['one','two'])

    def test_same_month_site_suppresses_all_technology_band_and_cell_children(self):
        self.cell('4g',active=NOV)
        self.cell('3g',tech='3G',active=NOV)
        event,=self.events()
        self.assertEqual(event.event_type,'SITE_ADDED')
        self.assertEqual(event.details['cell_ids'],['3g','4g'])

    def test_same_month_technology_suppresses_band_and_cell_children(self):
        self.cell('old',tech='3G',active=OCT)
        self.cell('new_a',active=NOV)
        self.cell('new_b',band='B20',frequency=800,active=NOV)
        event,=self.events()
        self.assertEqual(event.event_type,'TECHNOLOGY_ADDED')
        self.assertEqual(event.details['cell_ids'],['new_a','new_b'])

    def test_missing_group_member_prevents_complete_event_and_missing_is_not_zero(self):
        unknown=self.cell('unknown')
        MAOSMonthlyKPI.objects.filter(cell=unknown).update(thrp_bits_dl=None)
        self.cell('known',active=NOV)
        event,=self.events()
        self.assertEqual(event.event_type,'CELL_ADDED')
        unknown.refresh_from_db()
        self.assertIsNone(unknown.effective_activation_month)
        self.assertEqual(unknown.activation_evidence,'no_positive_traffic')

    def test_bandwidth_persists_and_recompute_is_idempotent_with_old_history_retained(self):
        cell=self.cell('upgrade',active=OCT)
        MAOSMonthlyKPI.objects.create(cell=cell,month_date=NOV,thrp_bits_dl=1,prb_dl_available=100)
        event,=self.events()
        self.assertEqual((event.event_type,event.previous_bandwidth_mhz,event.new_bandwidth_mhz),('BANDWIDTH_UPGRADE',5,20))
        self.events()
        self.assertEqual(RadioNetworkEvent.objects.filter(site=self.site).count(),1)
        MAOSMonthlyKPI.objects.filter(cell=cell,month_date=NOV).update(thrp_bits_dl=0)
        self.assertEqual(self.events(),[])
        event.refresh_from_db()
        self.assertFalse(event.is_current)
        self.assertEqual(site_event_data(self.site)['network_events'],[])
