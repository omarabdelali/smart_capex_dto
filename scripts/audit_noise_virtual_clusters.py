"""Read-only reference pre-check; does not implement production virtual clusters.

Run via manage.py shell/runpy. Separates raw noise-labelled rows from the 987
physical groups with no real-cluster member after 50 m location grouping.
"""
from collections import Counter, defaultdict
from datetime import date
import csv
import json
import math
from pathlib import Path
from statistics import median

import numpy as np
from sklearn.cluster import DBSCAN
from django.db.models import Min, Max, Sum
from core.models import Site, MAOSMonthlyKPI
from services.models.preprocessing.network_events import effective_event_date
from services.models.similarity.historical import month_offset
from services.utils.geo_utils import haversine, compute_bearing


def numeric_site_id(value):
    try:
        return 0, int(value)
    except ValueError:
        return 1, str(value)


def angular_bin(bearing):
    normalized = round(bearing % 360, 6) % 360
    return math.floor(normalized / 30) % 12, normalized


def select_members(candidates, radius, eligible=None, first_traffic=None, cutoff=None):
    bins = {}
    for candidate in candidates:
        if not 50 <= candidate['distance_m'] < radius:
            continue
        key = candidate['site_id']
        if eligible is not None and key not in eligible:
            continue
        # A site first showing LTE traffic in/after the cutoff cannot be a
        # pre-existing event recipient. Missing first evidence is not zero.
        if cutoff is not None and (key not in first_traffic or first_traffic[key] >= cutoff):
            continue
        bin_id = candidate['bin']
        tie_key = (math.floor(candidate['distance_m'] + .5), numeric_site_id(key))
        if bin_id not in bins or tie_key < bins[bin_id][0]:
            item = {**candidate, 'member_recent_launch':
                bool(cutoff and month_offset(cutoff, -3) <= first_traffic[key] < cutoff)
                if first_traffic is not None else None}
            bins[bin_id] = tie_key, item
    return [bins[key][1] for key in sorted(bins)]


def member_summary(members):
    distances = [r['distance_m'] for r in members]
    count = len(members)
    return {'n_bins_filled': count, 'n_members': count,
            'nearest_member_m': min(distances) if distances else None,
            'median_member_m': median(distances) if distances else None,
            'max_member_m': max(distances) if distances else None,
            'support_level': 'isolated' if count == 0 else 'low' if count <= 2 else 'ok',
            'members': members}


def aggregate(rows, field):
    counts = Counter('0' if row[field]['n_members'] == 0 else '1-2' if row[field]['n_members'] <= 2 else '3+' for row in rows)
    nearest = [row[field]['nearest_member_m'] for row in rows if row[field]['nearest_member_m'] is not None]
    medians = [row[field]['median_member_m'] for row in rows if row[field]['median_member_m'] is not None]
    pooled = [m['distance_m'] for row in rows for m in row[field]['members']]
    return {'sites': len(rows), 'filled_bins_counts': dict(counts),
            'filled_bins_shares_pct': {key: 100 * counts[key] / len(rows) for key in ('0', '1-2', '3+')},
            'mean_bins_filled': sum(row[field]['n_members'] for row in rows) / len(rows),
            'median_nearest_member_m': median(nearest) if nearest else None,
            'median_of_site_member_medians_m': median(medians) if medians else None,
            'pooled_median_member_m': median(pooled) if pooled else None,
            'minimum_nearest_member_m': min(nearest) if nearest else None,
            'maximum_nearest_member_m': max(nearest) if nearest else None}


def run():
    sites = list(Site.objects.only('site_id','site_name','latitude','longitude','cluster_id','is_launched','launch_date').prefetch_related('cells','network_events').order_by('site_id'))
    noise = [s for s in sites if s.cluster_id == -1]
    coordinates = np.radians([[s.latitude,s.longitude] for s in sites])
    labels = DBSCAN(eps=50/6371000, min_samples=1, metric='haversine').fit_predict(coordinates)
    groups = defaultdict(list)
    for site, label in zip(sites, labels):
        groups[int(label)].append(site)
    physical_groups = [g for g in groups.values() if all(s.cluster_id == -1 for s in g)]
    representatives = {min(g, key=lambda s: numeric_site_id(s.site_id)).site_id for g in physical_groups}
    latest = MAOSMonthlyKPI.objects.aggregate(value=Max('month_date'))['value']
    current_cutoff = month_offset(latest, 1)
    positive = MAOSMonthlyKPI.objects.filter(cell__technology='4G',thrp_bits_dl__gt=0)
    first = dict(positive.values('cell__site__site_id').annotate(value=Min('month_date')).values_list('cell__site__site_id','value'))
    launched = {s.site_id: s.launch_date.replace(day=1) for s in sites if s.is_launched and s.launch_date}
    active_by_month = defaultdict(set)
    for key, month in positive.values_list('cell__site__site_id','month_date').distinct():
        active_by_month[month].add(key)
    eligible_cache = {}

    def eligible(cutoff):
        if cutoff not in eligible_cache:
            ids = set().union(*(active_by_month[month_offset(cutoff,i)] for i in (-3,-2,-1)))
            eligible_cache[cutoff] = {key for key in ids if launched.get(key) != cutoff}
        return eligible_cache[cutoff]

    # Verify the requested boundary/tie convention before using the reference.
    assert angular_bin(30.0) == (1,30.0)
    assert angular_bin(359.9999999) == (0,0.)
    tied = [{'site_id': key, 'distance_m': d, 'bin': 1, 'bearing_deg': 30., 'tier': 'tier1'} for key,d in [('10',100.1),('2',100.4)]]
    assert select_members(tied,5000)[0]['site_id'] == '2'
    assert select_members([{**tied[0],'distance_m':49.999}],10000) == []
    assert select_members([{**tied[0],'distance_m':10000}],10000) == []

    records = []
    lon = coordinates[:,1]
    lat = coordinates[:,0]
    for index, origin in enumerate(noise, 1):
        phi, lam = math.radians(origin.latitude), math.radians(origin.longitude)
        dphi, dlam = lat-phi, lon-lam
        a = np.sin(dphi/2)**2 + math.cos(phi)*np.cos(lat)*np.sin(dlam/2)**2
        distances = 6371000 * 2 * np.arcsin(np.sqrt(np.clip(a,0,1)))
        candidates = []
        for i in np.where((distances>=50) & (distances<10000))[0]:
            other = sites[i]
            if other.site_id == origin.site_id:
                continue
            # Scalar formulas match the existing project helpers exactly.
            distance = haversine(origin.latitude,origin.longitude,other.latitude,other.longitude)
            bin_id, bearing = angular_bin(compute_bearing(origin.latitude,origin.longitude,other.latitude,other.longitude))
            candidates.append({'site_id':other.site_id,'bin':bin_id,'distance_m':distance,
                'bearing_deg':bearing,'tier':'tier1' if distance<5000 else 'tier2'})
        event_date = effective_event_date(origin)
        cutoff = event_date.replace(day=1) if event_date else current_cutoff
        row = {'site_id':origin.site_id,'site_name':origin.site_name,'cluster_id':origin.cluster_id,
               'physical_noise_representative':origin.site_id in representatives,
               'event_cutoff':cutoff.isoformat(),'cutoff_kind':'detected_event' if event_date else 'current_scenario'}
        for radius in (5000,10000):
            row[f'geometry_{radius}'] = member_summary(select_members(candidates,radius))
            row[f'current_lte_{radius}'] = member_summary(select_members(candidates,radius,eligible(current_cutoff),first,current_cutoff))
            row[f'event_lte_{radius}'] = member_summary(select_members(candidates,radius,eligible(cutoff),first,cutoff))
        records.append(row)
        if index % 400 == 0:
            print(f'Noise rows audited: {index}/{len(noise)}',flush=True)
    physical = [r for r in records if r['physical_noise_representative']]
    fields = [f'{scope}_{radius}' for scope in ('geometry','current_lte','event_lte') for radius in (5000,10000)]
    report = {'audit_date':'2026-10-27','read_only':True,'total_site_rows':len(sites),'raw_noise_rows':len(noise),
        'physical_noise_locations':len(physical),'physical_location_groups_50m':len(groups),
        'mixed_noise_and_real_cluster_location_groups':sum(any(s.cluster_id==-1 for s in g) and any(s.cluster_id!=-1 for s in g) for g in groups.values()),
        'current_cutoff':current_cutoff.isoformat(),
        'definitions':{'physical_noise_locations':'50 m connected-component groups whose every stored row has cluster_id=-1; representative is smallest numeric site ID. Diagnostic grouping only; no labels changed.',
            'candidates':'All stored sites; exclude self and distance<50 m. One per rounded true-north bearing bin. Radius uses actual distance<R.',
            'geometry':'Current inventory only; no traffic eligibility, for spatial support pre-check.',
            'current_lte':'Positive LTE DL traffic in any of three complete months before current cutoff; exclude same-month launches.',
            'event_lte':'Same eligibility rebuilt at each noise site primary event cutoff; undated sites use current scenario.',
            'distance_ties':'Same nearest whole metre (floor(distance+0.5)); smaller numeric site ID wins, with lexical fallback for nonnumeric IDs.',
            'recent_launch':'Flag first positive LTE month inside the 3-month baseline; actual dated site launch is also excluded at the event month.',
            'distance_summaries':'Median nearest distance and median of per-site selected-member medians, supported sites only. Pooled member median also provided. Empty membership stays NULL.'},
        'physical_noise_precheck':{field:aggregate(physical,field) for field in fields},
        'raw_noise_precheck':{field:aggregate(records,field) for field in fields},
        'schema_fields_present':{name:any(f.name==name for f in Site._meta.fields) for name in (
            'tier_scheme','vis_members','vis_n_bins_filled','vis_n_members','vis_max_dist_m','vis_median_dist_m','vis_sampled_traffic_gb','support_level')},
        'per_site':records}
    output = Path('docs/verification/noise_virtual_clusters')
    output.mkdir(parents=True,exist_ok=True)
    (output/'precheck-2026-10-27.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    keys = ['site_id','site_name','cluster_id','physical_noise_representative','event_cutoff','cutoff_kind']
    summary_keys = ['n_bins_filled','nearest_member_m','median_member_m','max_member_m','support_level']
    with (output/'precheck-2026-10-27.csv').open('w',newline='',encoding='utf-8') as stream:
        writer = csv.DictWriter(stream,fieldnames=keys+[field+'_'+key for field in fields for key in summary_keys])
        writer.writeheader()
        for row in records:
            writer.writerow({**{key:row[key] for key in keys},**{field+'_'+key:row[field][key] for field in fields for key in summary_keys}})
    print(json.dumps({k:v for k,v in report.items() if k not in ('per_site','raw_noise_precheck','definitions')},indent=2))


run()
