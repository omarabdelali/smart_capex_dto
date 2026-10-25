"""Cluster, cell-plan configuration, and MAOS context feature builders."""

from collections import defaultdict
from calendar import monthrange

from django.db.models import Avg, Max, Sum
from django.db.models import Q
from pyproj import Transformer
from shapely.geometry import MultiPoint, Point
from shapely.ops import transform as transform_geometry

from core.models import MAOSMonthlyKPI


_TO_EQUAL_AREA = Transformer.from_crs('EPSG:4326', 'EPSG:6933', always_xy=True).transform


def cluster_feature_map(sites_data):
    """Build the six persisted cluster features from current sites and MAOS data."""
    groups = defaultdict(list)
    for row in sites_data:
        cluster_id = row.get('cluster_id', -1)
        # Each DBSCAN noise site is a separate singleton for feature purposes.
        group_key = (cluster_id, row['site_id'] if cluster_id == -1 else None)
        groups[group_key].append(row)

    latest_month = MAOSMonthlyKPI.objects.aggregate(month=Max('month_date'))['month']
    maos_by_site = {}
    if latest_month:
        for row in MAOSMonthlyKPI.objects.filter(month_date=latest_month).values('cell__site__site_id').annotate(
            traffic_bits=Sum('thrp_bits_dl'), users=Sum('active_users_avg')
        ):
            maos_by_site[row['cell__site__site_id']] = {
                'traffic': (row['traffic_bits'] or 0) / 8_000_000_000,
                'users': row['users'] or 0,
            }

    result = {}
    for (cluster_id, _noise_site_id), members in groups.items():
        projected = [
            transform_geometry(_TO_EQUAL_AREA, Point(member['longitude'], member['latitude']))
            for member in members
        ]
        hull = MultiPoint(projected).convex_hull
        if len(members) == 1 or hull.geom_type == 'LineString' or hull.area <= 0:
            area_km2 = max(hull.buffer(100).area, 3.141592653589793 * 100**2) / 1_000_000
        else:
            area_km2 = hull.area / 1_000_000
        traffic_values = [maos_by_site.get(member['site_id'], {}).get('traffic', 0) for member in members]
        user_values = [maos_by_site.get(member['site_id'], {}).get('users', 0) for member in members]
        centroid = MultiPoint(projected).centroid
        for member, point in zip(members, projected):
            result[member['site_id']] = {
                'cluster_id': cluster_id,
                'cluster_size': len(members),
                'cluster_density_sites_per_km2': len(members) / area_km2 if area_km2 else 0,
                'cluster_avg_traffic_gb': sum(traffic_values) / len(members),
                'cluster_avg_users': sum(user_values) / len(members),
                'dist_to_cluster_centroid_m': point.distance(centroid),
            }
    return result


def configuration_feature_values(site):
    """Summarize cell-plan configuration and infer pre-event technology activity.

    MAOS KPI activity is the only historical evidence available for whether a
    technology was already serving the site. Cell-plan rows describe the
    current configuration, so they cannot by themselves establish a before
    state or historical band additions.
    """
    cells = list(site.cells.all())
    technologies = {cell.technology for cell in cells}
    added = [cell for cell in cells if cell.is_launched and cell.launch_date]
    event_date = site.launch_date or min((cell.launch_date for cell in added), default=None)
    kpi_fields = (
        'traffic_user_avg', 'thrp_bits_dl', 'thrp_bits_ul', 'prb_util_dl_pct',
        'prb_util_ul_pct', 'rrc_conn_avg', 'active_users_avg', 'cqi_avg',
        'rsrp_avg_dbm',
    )
    before = set()
    if event_date:
        activity = Q()
        for field in kpi_fields:
            activity |= Q(**{f'{field}__gt': 0}) | Q(**{f'{field}__lt': 0})
        before = set(MAOSMonthlyKPI.objects.filter(
            cell__site=site, month_date__lt=event_date,
        ).filter(activity).values_list('cell__technology', flat=True).distinct())

    if site.is_launched:
        event_type = 'NEW_SITE'
        tech_added = ''
    elif added:
        newly_serving = {cell.technology for cell in added} - before
        tech_added = next(iter(newly_serving)) if len(newly_serving) == 1 else ''
        event_type = 'TECH_ADD' if newly_serving else 'SECTOR_ADD'
    else:
        event_type = 'BASELINE'
        tech_added = ''

    sector_keys = {round(cell.azimuth / 5) * 5 for cell in cells}
    return {
        'event_type': event_type,
        'tech_added': tech_added,
        'has_2g_before': '2G' in before,
        'has_3g_before': '3G' in before,
        'has_4g_before': '4G' in before,
        'has_2g_after': '2G' in technologies,
        'has_3g_after': '3G' in technologies,
        'has_4g_after': '4G' in technologies,
        # No historical cell-plan snapshot exists to distinguish a new band
        # from the existing bands on the launched cell.
        'bands_added': '',
        'sector_count_after': len(sector_keys),
        'cells_per_sector_after': len(cells) / len(sector_keys) if sector_keys else 0,
        'antenna_height_m': sum(cell.antenna_height_m for cell in cells) / len(cells) if cells else 0,
        'total_bw_after_mhz': sum(cell.bandwidth_mhz for cell in cells),
        # The cell plan has no vendor capacity or spectral-efficiency input.
        'total_capacity_after_mbps': 0,
    }


def prelaunch_maos_values(site):
    """Derive pre-launch MAOS fields supported by stored monthly counters."""
    if not site.is_launched or not site.launch_date:
        return None
    # Monthly data cannot represent an exact 30-day window; use the latest
    # recorded month before the zero-KPI launch observation.
    month = MAOSMonthlyKPI.objects.filter(
        cell__site=site, month_date__lt=site.launch_date
    ).aggregate(month=Max('month_date'))['month']
    if month is None:
        return None
    rows = MAOSMonthlyKPI.objects.filter(cell__site=site, month_date=month)
    totals = rows.aggregate(
        dl_bits=Sum('thrp_bits_dl'), prb=Avg('prb_util_dl_pct'),
        rrc=Avg('rrc_conn_avg'),
    )
    days = monthrange(month.year, month.month)[1]
    dl_gb = (totals['dl_bits'] or 0) / 8_000_000_000
    return {
        'avg_prb_pre': totals['prb'] or 0,
        'avg_rrc_pre': totals['rrc'] or 0,
        'avg_throughput_pre': (totals['dl_bits'] or 0) / (days * 86_400 * 1_000_000),
        'dl_traffic_pre_gb_day': dl_gb / days,
    }
