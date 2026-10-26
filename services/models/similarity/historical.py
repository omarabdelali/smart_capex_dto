"""Reconstruct time-bounded LTE context without reading current feature tables."""
from datetime import date

import numpy as np
from django.db.models import Q, Sum
from pyproj import Transformer
from shapely.geometry import MultiPoint, Point
from sklearn.cluster import DBSCAN

from core.models import MAOSMonthlyKPI, Site
from services.models.features.anp import ANPComputer
from services.utils.geo_utils import haversine


def month_offset(value, offset):
    index = value.year * 12 + value.month - 1 + offset
    year, month = divmod(index, 12)
    return date(year, month+1, 1)


def load_network(cutoff):
    """Evidence in the three complete calendar months before cutoff only.

    No activity evidence means unknown, not proof that a site did not exist.
    Current coordinates/technology labels identify historical observations;
    coordinates are assumed stable, and no historical heights are inferred.
    """
    activity = Q()
    for field in ('thrp_bits_dl', 'active_users_avg', 'traffic_user_avg', 'cqi_avg'):
        activity |= Q(**{field+'__gt': 0})
    rows = list(MAOSMonthlyKPI.objects.filter(
        month_date__gte=month_offset(cutoff, -3), month_date__lt=cutoff,
    ).filter(activity).values('cell__site__site_id', 'cell__technology', 'month_date').annotate(
        traffic=Sum('thrp_bits_dl'), users=Sum('active_users_avg'),
    ))
    return network_from_rows(list(Site.objects.values('site_id', 'latitude', 'longitude')), rows)


def network_from_rows(sites, rows):
    records = {row['site_id']: {**row, 'technologies': set(), 'monthly': {}} for row in sites}
    for row in rows:
        record = records.get(row['cell__site__site_id'])
        if record is None:
            continue
        record['technologies'].add(row['cell__technology'])
        monthly = record['monthly'].setdefault(row['month_date'], {'traffic': [], 'users': []})
        for field in ('traffic', 'users'):
            if row[field] is not None:
                monthly[field].append(row[field])
    return {key: value for key, value in records.items() if value['technologies']}


def cluster_members(origin, network):
    """Scenario cluster using only evidenced pre-event sites plus origin.

    Labels are local to this reconstruction and never become similarity IDs.
    """
    members = [record for key, record in network.items() if key != origin.site_id]
    members.append({'site_id': origin.site_id, 'latitude': origin.latitude, 'longitude': origin.longitude})
    coords = np.radians([[row['latitude'], row['longitude']] for row in members])
    labels = DBSCAN(eps=2/6371.0, min_samples=3, metric='haversine', algorithm='ball_tree').fit_predict(coords)
    label = labels[-1]
    return [row for row, candidate_label in zip(members, labels) if label != -1 and candidate_label == label]


def context_features(origin, network, cutoff):
    neighbors = [record for key, record in network.items() if key != origin.site_id]
    distances = [haversine(origin.latitude, origin.longitude, row['latitude'], row['longitude']) for row in neighbors]
    # With no evidence the context is unknown; ANP's isolated-site defaults
    # would otherwise manufacture certainty from an empty observation window.
    if not neighbors:
        return {}
    result = {
        'dist_nearest_site_m': min(distances),
        'neighbor_avg_antenna_height_m': None,
    }
    for radius in (1, 2, 3):
        result[f'n_sites_{radius}km'] = sum(d <= radius*1000 for d in distances)
    for tech in ('2G', '3G', '4G'):
        result[f'n_{tech.lower()}_sites_2km'] = (
            sum(d <= 2000 and tech in row['technologies'] for row, d in zip(neighbors, distances))
            if any(tech in row['technologies'] for row in neighbors) else None
        )
    result.update(ANPComputer().compute_anp(
        origin.latitude, origin.longitude,
        [(row['latitude'], row['longitude']) for row in neighbors], distances,
    ))
    group = cluster_members(origin, network)
    if not group:
        group = [{'site_id': origin.site_id, 'latitude': origin.latitude, 'longitude': origin.longitude}]
    project = Transformer.from_crs('EPSG:4326', 'EPSG:32632', always_xy=True)
    points = [Point(*project.transform(row['longitude'], row['latitude'])) for row in group]
    hull = MultiPoint(points).convex_hull
    area = hull.area if hull.area > 0 else hull.buffer(100).area
    x, y = project.transform(origin.longitude, origin.latitude)
    result.update({'cluster_id': None, 'cluster_size': len(group),
                   'cluster_density_sites_per_km2': len(group)/(area/1e6),
                   'dist_to_cluster_centroid_m': Point(x,y).distance(MultiPoint(points).centroid)})
    latest = month_offset(cutoff, -1)
    for output, field, divisor in (('cluster_avg_traffic_gb', 'traffic', 8e9), ('cluster_avg_users', 'users', 1)):
        values = []
        for row in group:
            # Origin is the intervention, not a pre-existing recipient.
            if row['site_id'] == origin.site_id:
                continue
            data = network.get(row['site_id'], {}).get('monthly', {}).get(latest, {}).get(field, [])
            if data:
                values.append(sum(data)/divisor)
        result[output] = sum(values)/len(values) if values else None
    return {key: (None if isinstance(value, (float, np.floating)) and not np.isfinite(value) else value)
            for key, value in result.items()}
