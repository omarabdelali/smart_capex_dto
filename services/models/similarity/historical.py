"""Reconstruct time-bounded LTE context without reading current feature tables."""
from datetime import date

import numpy as np
from django.db.models import Count, Q, Sum
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


def event_labels(site, cutoff):
    """Frozen detector labels used for prefiltering before expensive feature extraction."""
    order = ('SITE_ADDED','TECHNOLOGY_ADDED','FREQUENCY_BAND_ADDED','CELL_ADDED',
             'BANDWIDTH_UPGRADE','BANDWIDTH_DOWNGRADE')
    events = [e for e in site.network_events.all() if e.is_current and e.effective_date == cutoff]
    if not events:
        return {}
    kind = min((e.event_type for e in events), key=order.index)
    relevant = [e for e in events if e.event_type == kind]
    technologies = {tech for e in relevant for tech in e.details.get('technologies',[])}
    bands = ','.join(sorted({band for e in relevant for band in e.details.get('bands',[])})) or None
    values = {'event_type':kind,
        'tech_added':'/'.join(sorted(technologies)) if kind=='TECHNOLOGY_ADDED' else None,
        'bands_added':bands if kind in ('TECHNOLOGY_ADDED','FREQUENCY_BAND_ADDED','SITE_ADDED') else None}
    return values


def event_feature_values(site, cutoff):
    """Recover event labels and technology evidence without current config values."""
    values = event_labels(site, cutoff)
    if not values:
        return {}
    kind = values['event_type']
    relevant = [e for e in site.network_events.all() if e.is_current and e.effective_date == cutoff and e.event_type == kind]
    technologies = {tech for e in relevant for tech in e.details.get('technologies', [])}
    evidence = {row['cell__technology']:row for row in MAOSMonthlyKPI.objects.filter(
        cell__site=site,month_date__lt=cutoff,thrp_bits_dl__gte=0,
    ).values('cell__technology').annotate(observed=Count('pk'),positive=Count('pk',filter=Q(thrp_bits_dl__gt=0)))}
    for tech in ('2G','3G','4G'):
        row = evidence.get(tech)
        before = bool(row['positive']) if row else None
        values[f'tech_before_{tech.lower()}'] = before
        values[f'tech_after_{tech.lower()}'] = True if tech in technologies else before
    return values


def load_network(cutoff):
    """Evidence in the three complete calendar months before cutoff only.

    No activity evidence means unknown, not proof that a site did not exist.
    Current coordinates/technology labels identify historical observations;
    coordinates are assumed stable, and no historical heights are inferred.
    """
    activity = Q(cell__technology='4G',thrp_bits_dl__gt=0)
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
    from services.models.features.neighborhood import inventory
    if origin.cluster_id == -1:
        return []
    groups,by_raw = inventory({})
    origin_key = by_raw.get(origin.site_id,origin.site_id)
    members = []
    for key,row in groups.items():
        if row['cluster_id']==origin.cluster_id and key!=origin_key and any(raw in network for raw in row['site_ids']):
            members.append(row)
    members.append({'site_id':origin.site_id,'latitude':origin.latitude,'longitude':origin.longitude})
    return members


def context_features(origin, network, cutoff, cache=None):
    from services.models.features.neighborhood import neighborhood, scheme
    context = neighborhood(origin,cutoff,cache)
    neighbors = context['scopes']['tier1']+context['scopes']['tier2']
    result = {'tier_scheme':context['tier_scheme'],'dist_nearest_site_m':context['nearest_eligible_site_m']}
    if context['nearest_eligible_site_m'] is None:
        return result
    distances = [row['distance_m'] for row in neighbors]
    for radius in (1,2,3):
        result[f'n_sites_{radius}km'] = sum(d<=radius*1000 for d in distances)
    for tech in ('2G','3G','4G'):
        result[f'n_{tech.lower()}_sites_2km'] = sum(row['distance_m']<=2000 for row in neighbors) if tech=='4G' else None
    result.update(ANPComputer(tier_scheme=context['tier_scheme']).compute_anp(
        origin.latitude,origin.longitude,[(r['latitude'],r['longitude']) for r in neighbors],distances))
    for index in (1,2):
        if not result[f'n_tier{index}']:
            result[f't{index}_nearest_m']=None
            result[f'avg_neighbor_dist_t{index}_m']=None
    return result
