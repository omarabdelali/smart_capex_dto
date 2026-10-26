"""Build similarity inputs from persisted site features and pre-event MAOS history."""
from calendar import monthrange
from datetime import date
from statistics import median

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Count, F, Max, Min, Q, Sum

from core.models import MAOSMonthlyKPI
from services.models.preprocessing.maos_aggregation import normalize_monthly_totals
from services.models.features.population import population_features
from services.models.features.population import POPULATION_FIELDS
from .historical import month_offset, load_network, context_features
from services.models.features.road_features import road_similarity_values


PERFORMANCE_FIELDS = (
    'pre_dl_traffic_gb_day', 'pre_active_users', 'pre_traffic_users',
    'pre_prb_util_dl_pct', 'pre_cqi_avg', 'pre_dl_throughput_kbps',
    'pre_dl_packet_delay_ms', 'pre_cell_availability_pct',
)


def _related(site, relation):
    try:
        return getattr(site, relation)
    except ObjectDoesNotExist:
        return None


def _values(instance, names):
    if instance is None:
        return {}
    return {name: getattr(instance, name, None) for name in names}


def build_site_similarity_vector(site, as_of_date=None, snapshot_cache=None, allow_current_roads=False):
    """Return mixed static features plus a median 1-3 month pre-event profile."""
    config = _related(site, 'config_features')
    geometry = _related(site, 'geometric_features')
    clutter = _related(site, 'clutter_features')
    spatial = _related(site, 'spatial_features')
    anp = _related(site, 'anp_features')
    cluster = _related(site, 'cluster_features')
    prelaunch = _related(site, 'prelaunch_kpi')
    history = MAOSMonthlyKPI.objects.filter(cell__site=site)
    event_date = site.launch_date or site.cells.filter(
        is_launched=True, launch_date__isnull=False
    ).aggregate(event_date=Min('launch_date'))['event_date']
    if as_of_date is None:
        latest = history.aggregate(month=Max('month_date'))['month'] if not event_date else None
        as_of_date = event_date or (month_offset(latest, 1) if latest else date.today())
    cutoff = as_of_date.replace(day=1)
    historical = cutoff < date.today().replace(day=1) or (
        event_date is not None and cutoff <= event_date.replace(day=1)
    )

    vector = {
        'site_id': site.site_id,
        'event_type': getattr(config, 'event_type', None),
        'tech_added': getattr(config, 'tech_added', None) or None,
        'bands_added': getattr(config, 'bands_added', None) or None,
        'sector_count_after': getattr(config, 'sector_count_after', None),
        'cells_per_sector_after': getattr(config, 'cells_per_sector_after', None),
        'antenna_height_m': getattr(config, 'antenna_height_m', None),
        'total_bw_after_mhz': getattr(config, 'total_bw_after_mhz', None),
        # The current spec reserves zero as an uncomputed placeholder, not a
        # measured capacity value; omit it from selection and distance.
        'total_capacity_after_mbps': (
            getattr(config, 'total_capacity_after_mbps', None)
            if getattr(config, 'total_capacity_after_mbps', None) not in (None, 0)
            else None
        ),
        'tech_before_2g': getattr(config, 'has_2g_before', None),
        'tech_before_3g': getattr(config, 'has_3g_before', None),
        'tech_before_4g': getattr(config, 'has_4g_before', None),
        'tech_after_2g': getattr(config, 'has_2g_after', None),
        'tech_after_3g': getattr(config, 'has_3g_after', None),
        'tech_after_4g': getattr(config, 'has_4g_after', None),
    }
    configuration_fields = set(vector) - {'site_id'}
    vector.update(_values(geometry, (
        'z_antenna_m', 'terrain_slope_deg', 'terrain_roughness_m', 'terrain_aspect_deg',
    )))
    vector.update(_values(clutter, (
        'dominant_clutter', 'clutter_entropy_2km', 'pct_building_area_1km',
        'avg_building_height_m',
    )))
    vector.update(_values(spatial, (
        'dist_nearest_site_m', 'n_sites_1km', 'n_sites_2km', 'n_sites_3km',
        'n_2g_sites_2km', 'n_3g_sites_2km', 'n_4g_sites_2km',
        'neighbor_avg_antenna_height_m',
    )))
    vector.update(_values(anp, (
        'n_tier1', 'n_tier2', 't1_to_t2_ratio', 't1_nearest_m', 't2_nearest_m',
        'angular_uniformity', 'max_empty_arc_deg', 'n_empty_bins',
        'dominant_sector_deg', 'dominant_sector_count', 'edge_score',
        'bearing_stddev_deg', 'avg_neighbor_dist_t1_m', 'avg_neighbor_dist_t2_m',
        'coverage_asymmetry',
    )))
    vector.update(_values(cluster, (
        'cluster_id', 'cluster_size', 'cluster_density_sites_per_km2',
        'cluster_avg_traffic_gb', 'cluster_avg_users', 'dist_to_cluster_centroid_m',
    )))
    vector.update(_values(prelaunch, (
        'avg_traffic_dl_gb', 'avg_traffic_ul_gb', 'avg_users', 'avg_prb_util_pct',
        'peak_hour_traffic_gb', 'peak_hour_users', 'avg_cqi', 'avg_rsrp_dbm',
        'congestion_hours_per_day',
    )))

    vector.update(population_features(site.latitude, site.longitude) if cutoff >= date(2025, 1, 1)
                  else dict.fromkeys(POPULATION_FIELDS))
    vector['population_quality'] = vector.pop('quality', None)
    monthly_rows = list(history.filter(month_date__gte=month_offset(cutoff, -3), month_date__lt=cutoff).values('month_date').annotate(
        traffic_bits=Sum('thrp_bits_dl'),
        dl_bits=Sum('thrp_bits_dl', filter=Q(thrp_time_dl_ms__isnull=False, thrp_bits_dl_last_tti__isnull=False, thrp_bits_dl__gte=F('thrp_bits_dl_last_tti'))),
        dl_last_tti_bits=Sum('thrp_bits_dl_last_tti', filter=Q(thrp_time_dl_ms__isnull=False, thrp_bits_dl__gte=F('thrp_bits_dl_last_tti'))),
        dl_time_ms=Sum('thrp_time_dl_ms', filter=Q(thrp_time_dl_ms__isnull=False, thrp_bits_dl_last_tti__isnull=False, thrp_bits_dl__gte=F('thrp_bits_dl_last_tti'))),
        prb_used=Sum('prb_dl_used_avg', filter=Q(prb_dl_used_avg__isnull=False, prb_dl_available__gt=0)),
        prb_available=Sum('prb_dl_available', filter=Q(prb_dl_used_avg__isnull=False, prb_dl_available__gt=0)),
        delay_time_ms=Sum('dl_packet_delay_time_ms', filter=Q(dl_packet_delay_time_ms__isnull=False, dl_packet_delay_packets__gt=0)),
        delay_packets=Sum('dl_packet_delay_packets', filter=Q(dl_packet_delay_time_ms__isnull=False, dl_packet_delay_packets__gt=0)),
        unavailable_s=Sum('cell_unavail_duration_s', filter=Q(cell_unavail_duration_s__isnull=False, observation_duration_s__gt=0)),
        observation_s=Sum('observation_duration_s', filter=Q(cell_unavail_duration_s__isnull=False, observation_duration_s__gt=0)),
        cqi_weighted_total=Sum('cqi_weighted_sum', filter=Q(cqi_weighted_sum__isnull=False, cqi_sample_count__gt=0)),
        cqi_sample_count=Sum('cqi_sample_count', filter=Q(cqi_weighted_sum__isnull=False, cqi_sample_count__gt=0)),
        active_users=Sum('active_users_avg'),
        traffic_users=Sum('traffic_user_avg'), reporting_cells=Count('cell_id', distinct=True),
    ).order_by('-month_date')[:3])
    monthly_rows.reverse()
    profiles = []
    for row in monthly_rows:
        metrics = normalize_monthly_totals(row)
        days = monthrange(row['month_date'].year, row['month_date'].month)[1]
        traffic_gb = metrics['thrp_dl_gb']
        profiles.append({
            'pre_dl_traffic_gb_day': traffic_gb / days if traffic_gb is not None else None,
            'pre_active_users': metrics['active_users_avg'],
            'pre_traffic_users': metrics['traffic_user_avg'],
            'pre_prb_util_dl_pct': metrics['prb_util_dl_pct'],
            'pre_cqi_avg': metrics['cqi_avg'],
            'pre_dl_throughput_kbps': metrics['dl_throughput_kbps'],
            'pre_dl_packet_delay_ms': metrics['dl_packet_delay_ms'],
            'pre_cell_availability_pct': metrics['cell_availability_pct'],
        })

    for field in PERFORMANCE_FIELDS:
        values = [row[field] for row in profiles if row[field] is not None]
        vector[field] = median(values) if values else None

    def relative_trend(key):
        valid = [row[key] for row in profiles if row[key] is not None]
        if len(valid) < 2 or valid[0] == 0:
            return None
        return (valid[-1] - valid[0]) / abs(valid[0]) * 100

    vector['pre_traffic_trend_3m_pct'] = relative_trend('pre_dl_traffic_gb_day')
    vector['pre_prb_trend_3m_pct'] = relative_trend('pre_prb_util_dl_pct')
    valid_values = sum(value is not None for row in profiles for value in row.values())
    vector['pre_profile_months_available'] = len(profiles)
    vector['pre_profile_completeness'] = valid_values / (3 * len(PERFORMANCE_FIELDS))
    # Replace current network context for every as-of vector. No future
    # inventory, heights, membership or latest-global-month KPI enters it.
    context_names = (
        'dist_nearest_site_m n_sites_1km n_sites_2km n_sites_3km n_2g_sites_2km n_3g_sites_2km n_4g_sites_2km '
        'neighbor_avg_antenna_height_m n_tier1 n_tier2 t1_to_t2_ratio t1_nearest_m t2_nearest_m '
        'angular_uniformity max_empty_arc_deg n_empty_bins dominant_sector_deg dominant_sector_count edge_score '
        'bearing_stddev_deg avg_neighbor_dist_t1_m avg_neighbor_dist_t2_m coverage_asymmetry '
        'cluster_id cluster_size cluster_density_sites_per_km2 cluster_avg_traffic_gb cluster_avg_users dist_to_cluster_centroid_m'
    ).split()
    cache = snapshot_cache if snapshot_cache is not None else {}
    if cutoff not in cache:
        cache[cutoff] = load_network(cutoff)
    vector.update(dict.fromkeys(context_names))
    vector.update(context_features(site, cache[cutoff], cutoff))
    # Legacy records have no verified measurement window; never use their
    # default zeros or undated values as historical model inputs.
    vector.update(dict.fromkeys((
        'avg_traffic_dl_gb avg_traffic_ul_gb avg_users avg_prb_util_pct peak_hour_traffic_gb '
        'peak_hour_users avg_cqi avg_rsrp_dbm congestion_hours_per_day'
    ).split()))
    if historical:
        vector.update(dict.fromkeys(configuration_fields))
        vector['event_type'] = 'NEW_SITE' if site.is_launched and site.launch_date and site.launch_date.replace(day=1) == cutoff else None
        vector.update(dict.fromkeys(('z_antenna_m', 'dominant_clutter', 'clutter_entropy_2km',
                                     'pct_building_area_1km', 'avg_building_height_m')))
        # The only population epoch available locally is 2025. Retain all
        # dimensions in the schema, but do not use it for earlier events.
    if cutoff < date(2025, 1, 1):
        vector.update(dict.fromkeys(POPULATION_FIELDS))
    vector['feature_as_of_date'] = cutoff.isoformat()
    vector.update(road_similarity_values(_related(site, 'road_features'), cutoff, allow_current=allow_current_roads))
    vector['feature_timing_note'] = (
        'Only three complete pre-cutoff calendar months are used. Network context is reconstructed from evidenced LTE activity; '
        'coordinates are assumed stable. Historical configuration, building/clutter snapshots and undated legacy KPIs are unavailable. '
        'Terrain shape is treated as static; population is 2025 context and is excluded before 2025.'
    )
    return vector
