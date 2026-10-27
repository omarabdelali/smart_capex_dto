"""Explain excluded similarity dimensions without treating snapshots as history."""
from services.models.features.population import POPULATION_FIELDS
from services.models.similarity.gower_distance import GowerDistance

CONFIG_SNAPSHOT = ('sector_count_after','cells_per_sector_after','antenna_height_m','total_bw_after_mhz')
CLUTTER_SNAPSHOT = ('dominant_clutter','clutter_entropy_2km','pct_building_area_1km','avg_building_height_m')
LEGACY = ('avg_traffic_dl_gb','avg_traffic_ul_gb','avg_users','avg_prb_util_pct',
          'peak_hour_traffic_gb','peak_hour_users','avg_cqi','avg_rsrp_dbm','congestion_hours_per_day')


def feature_statuses(site, vector, include_current=False):
    """Report real missing-source reasons under the approved static-context policy."""
    statuses = {}
    for key in GowerDistance.NUMERIC_FEATURES + GowerDistance.CATEGORICAL_FEATURES:
        if key == 'tier_scheme':
            statuses[key]={'code':'mandatory_tier_partition','reason':'Standard and extended tiers are hard-filtered before ranking and PCA; this rule cannot be deselected.','selectable':False}
            continue
        if key == 'cluster_id':
            statuses[key]={'code':'identifier_display_only','reason':'Inherited site cluster ID; noise is -1. Displayed but never used as a distance dimension.','selectable':False}
            continue
        if key == 'cluster_avg_users':
            statuses[key]={'code':'duplicate_alias_display_only','reason':'Display alias of avg_users, the cluster active-user sum. Not weighted twice.','selectable':False}
            continue
        if not GowerDistance._is_missing(vector.get(key)):
            if key == 'avg_building_height_m':
                statuses[key] = {'code':'land_cover_height_prior','reason':
                    'Class-based estimate, not measured average height: urban 18 m, suburban 8 m, rural 4 m; forest/water use a 0 m convention. Retained under the approved static-context policy.',
                    'selectable':True}
                continue
            statuses[key] = {'code':'available','reason':None,'selectable':True}
            continue
        code, reason = 'missing_measurement','No supported measurement is available for this feature and cutoff.'
        if key in CONFIG_SNAPSHOT:
            code,reason='no_kpi_confirmed_configuration','No KPI-confirmed cells or complete PRB configuration can establish this feature at the event cutoff.'
            unmapped=vector.get('post_event_configuration_support',{}).get('unmapped_bandwidth_prbs',{})
            if key=='total_bw_after_mhz' and unmapped:
                code,reason='prb_bandwidth_unmapped',f'{len(unmapped)} cell PRB averages fall outside the strict +/-5 mapping windows for 25/50/75/100 PRBs; no future month or invented MHz value is used.'
        elif key in CLUTTER_SNAPSHOT:
            code,reason='static_source_missing','The approved static land-cover/building source has no value for this feature.'
        elif key in ('z_antenna_m','neighbor_avg_antenna_height_m'):
            code,reason='elevation_components_missing','DEM ground elevation, stored building height, or eligible neighbors are unavailable; antenna height alone defaults to 25 m.'
        elif key=='total_capacity_after_mbps':
            code,reason='legacy_mbps_not_defined','Use Site PRB capacity (total_prb_available). PRBs are not Mbps; no throughput-capacity conversion is assumed.'
        elif key=='total_prb_available':
            code,reason='prb_configuration_missing','At least one KPI-evidenced LTE cell lacks available-PRB configuration at or before the event month.'
        elif key in POPULATION_FIELDS:
            code,reason='static_population_source_missing','The static population raster/catchment has insufficient source data; this is not a time exclusion.'
        elif key in LEGACY:
            code,reason='cluster_previous_month_missing','No supported cluster measurement is available in the calendar month immediately before the event.'
            if key in ('avg_traffic_ul_gb','avg_rsrp_dbm','peak_hour_traffic_gb','peak_hour_users','congestion_hours_per_day'):
                code,reason='source_counter_unavailable','The imported monthly report lacks the required UL/RSRP or hourly measurements for this feature.'
        elif key=='cluster_id':
            code,reason='identifier_excluded','Cluster IDs are identifiers, not comparable measurements; reconstructed historical cluster labels are excluded.'
        elif key.startswith(('n_2g_','n_3g_')) or key.startswith(('tech_before_','tech_after_')):
            code,reason='technology_history_unknown','No supported traffic evidence establishes this technology state. The imported history is LTE-only; missing 2G/3G is not absence.'
        elif key in ('tech_added','bands_added'):
            code,reason='not_applicable_to_event','No corresponding technology/band addition is established for the selected event.'
        elif key.startswith(('tier1_','tier2_','cluster_')) and 'user_' in key:
            scope,metric=key.split('_',1)
            support=vector.get('user_context_support',{}).get(scope,{}).get('ratios',{}).get(metric,{})
            if support.get('unavailable_reason')=='zero_denominator':
                code,reason='zero_denominator','The summed denominator is zero; the ratio is undefined, even when other user shares are measured zero.'
            else:
                code,reason='no_paired_counters','No paired numerator and denominator counters are available in the pre-event window.'
        elif key.startswith('pre_'):
            code,reason='no_supported_pre_event_kpi','The three complete pre-event months lack a valid counter pair or positive denominator; missing values stay NULL.'
            if key.endswith('trend_3m_pct'):
                code,reason='trend_baseline_unavailable','A trend needs at least two valid monthly values and a nonzero first value.'
        status={'code':code,'reason':reason}
        statuses[key]=status
    return statuses
