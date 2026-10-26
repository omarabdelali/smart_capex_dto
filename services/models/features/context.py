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
    from services.models.preprocessing.network_events import primary_event
    event = primary_event(site)
    event_date = event.effective_date if event else site.launch_date
    before = set()
    if event_date:
        before = set(MAOSMonthlyKPI.objects.filter(
            cell__site=site, month_date__lt=event_date, thrp_bits_dl__gt=0,
        ).values_list('cell__technology', flat=True).distinct())
    event_type = event.event_type if event else 'BASELINE'
    added_technologies = event.details.get('technologies', []) if event and event.event_type == 'TECHNOLOGY_ADDED' else []
    tech_added = added_technologies[0] if len(added_technologies) == 1 else ''

    sector_keys = {round(cell.azimuth / 5) * 5 for cell in cells}
    values = {
        'event_type': event_type,
        'tech_added': tech_added,
        'bands_added': ', '.join(event.details.get('bands', [])) if event and event.event_type == 'FREQUENCY_BAND_ADDED' else '',
        'has_2g_before': '2G' in before,
        'has_3g_before': '3G' in before,
        'has_4g_before': '4G' in before,
        'has_2g_after': '2G' in technologies,
        'has_3g_after': '3G' in technologies,
        'has_4g_after': '4G' in technologies,
        # Sector/height/bandwidth fields below are current-plan summaries.
        'sector_count_after': len(sector_keys),
        'cells_per_sector_after': len(cells) / len(sector_keys) if sector_keys else 0,
        'antenna_height_m': sum(cell.antenna_height_m for cell in cells) / len(cells) if cells else 0,
        'total_bw_after_mhz': sum(cell.bandwidth_mhz for cell in cells),
        # The cell plan has no vendor capacity or spectral-efficiency input.
        'total_capacity_after_mbps': 0,
    }
    from services.models.features.approved_context import post_event_configuration
    from services.models.preprocessing.network_events import effective_event_date
    from services.models.similarity.historical import month_offset
    from datetime import date
    cutoff=effective_event_date(site)
    if cutoff is None:
        latest=MAOSMonthlyKPI.objects.aggregate(month=Max('month_date'))['month']
        cutoff=month_offset(latest,1) if latest else date.today().replace(day=1)
    derived=post_event_configuration(site,cutoff)
    derived.pop('post_event_configuration_support')
    values.update(derived)
    return values



def prelaunch_maos_values(site):
    """Derive pre-launch MAOS fields supported by stored monthly counters."""
    if not site.is_launched or not site.launch_date:
        return None
    # Monthly data cannot represent an exact 30-day window; use the latest
    # recorded month before traffic-confirmed group completion.
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
