"""Physical locations, tier policy and event-valid angular traffic samples."""
from collections import defaultdict
from datetime import date
from functools import lru_cache
import json
import math
from pathlib import Path
from statistics import median

import numpy as np
from sklearn.cluster import DBSCAN
from django.db import transaction
from django.db.models import Min, Max
from core.models import Site, MAOSMonthlyKPI
from services.utils.geo_utils import haversine, compute_bearing


@lru_cache(maxsize=1)
def policy():
    return json.loads((Path(__file__).resolve().parents[3]/'config/neighborhood.json').read_text(encoding='utf-8'))


def offset(month, n):
    y,m = divmod(month.year*12+month.month-1+n,12)
    return date(y,m+1,1)


def id_key(value):
    try:
        return 0,int(value)
    except ValueError:
        return 1,str(value)


def scheme(site):
    return 'extended' if site.cluster_id == -1 else 'standard'


def tier(distance_m, tier_scheme):
    if distance_m < policy()['minimum_neighbor_distance_m']:
        return None
    if tier_scheme == 'extended':
        return 'tier1' if distance_m < 5000 else 'tier2' if distance_m < 10000 else None
    return 'tier1' if distance_m <= 2000 else 'tier2' if distance_m <= 5000 else None


def distance_band(distance_m):
    if distance_m < 50 or distance_m >= 10000:
        return None
    return 'distance_0_2' if distance_m <= 2000 else 'distance_2_5' if distance_m < 5000 else 'distance_5_10'


def bin_and_bearing(bearing):
    value = round(bearing % 360,policy()['bearing_decimals']) % 360
    return math.floor(value/30) % 12,value


def labels(tier_scheme):
    return {'tier1':'Tier 1 (<5 km)' if tier_scheme=='extended' else 'Tier 1 (50 m-2 km)',
            'tier2':'Tier 2 (5-<10 km)' if tier_scheme=='extended' else 'Tier 2 (>2-5 km)',
            'cluster':'Real DBSCAN cluster', 'virtual_cluster':'Virtual sampled traffic (one site/bin)',
            'distance_0_2':'0-2 km', 'distance_2_5':'2-5 km', 'distance_5_10':'5-10 km'}


def reconcile_locations(dry_run=False):
    """Propagate an unambiguous real label across co-located source rows.

    Raw rows/cells are retained. A component spanning several real labels is
    rejected before mutation rather than arbitrarily merging DBSCAN clusters.
    """
    sites = list(Site.objects.order_by('site_id'))
    if not sites:
        return {'sites':0,'locations':0,'changed_labels':0,'noise_locations':0}
    groups = defaultdict(list)
    coordinates = np.radians([[s.latitude,s.longitude] for s in sites])
    group_ids = DBSCAN(eps=policy()['location_tolerance_m']/6371000,min_samples=1,metric='haversine').fit_predict(coordinates)
    for site, group in zip(sites,group_ids):
        groups[int(group)].append(site)
    conflicts = [[s.site_id for s in members] for members in groups.values() if len({s.cluster_id for s in members if s.cluster_id!=-1})>1]
    if conflicts:
        raise ValueError(f'Ambiguous co-location groups contain distinct real clusters: {conflicts[:5]}')
    changed, noise = 0,0
    for members in groups.values():
        real = {s.cluster_id for s in members if s.cluster_id!=-1}
        label = next(iter(real),-1)
        canonical = min(members,key=lambda s:id_key(s.site_id)).site_id
        noise += int(label==-1)
        for site in members:
            if site.original_cluster_id is None:
                site.original_cluster_id = site.cluster_id
            changed += int(site.cluster_id!=label)
            site.cluster_id,site.canonical_site_id = label,canonical
            site.tier_scheme = 'extended' if label==-1 else 'standard'
    if not dry_run:
        with transaction.atomic():
            Site.objects.bulk_update(sites,['original_cluster_id','cluster_id','canonical_site_id','tier_scheme'],batch_size=500)
            from core.models import ClusterFeatures
            labels_by_pk={s.pk:s.cluster_id for s in sites}
            summaries=list(ClusterFeatures.objects.all())
            for summary in summaries:
                summary.cluster_id=labels_by_pk[summary.site_id]
            if summaries:
                ClusterFeatures.objects.bulk_update(summaries,['cluster_id'],batch_size=500)
    return {'sites':len(sites),'locations':len(groups),'changed_labels':changed,'noise_locations':noise,
            'noise_rows':sum(s.cluster_id==-1 for s in sites),'dry_run':dry_run}


def inventory(cache):
    if '_neighborhood_inventory' not in cache:
        groups = {}
        rows = list(Site.objects.values('site_id','site_name','latitude','longitude','cluster_id','canonical_site_id','launch_date'))
        by_raw = {}
        for row in rows:
            key = row['canonical_site_id'] or row['site_id']
            by_raw[row['site_id']] = key
            if key not in groups:
                groups[key] = {**row,'site_id':key,'site_ids':[],'launch_dates':[]}
            groups[key]['site_ids'].append(row['site_id'])
            if row['launch_date']:
                groups[key]['launch_dates'].append(row['launch_date'].replace(day=1))
            if row['site_id']==key:
                groups[key].update({k:row[k] for k in ('site_name','latitude','longitude','cluster_id')})
        cache['_neighborhood_inventory'] = groups,by_raw
    return cache['_neighborhood_inventory']


def traffic_history(cache):
    if '_neighborhood_positive' not in cache:
        _,by_raw = inventory(cache)
        months = defaultdict(set)
        first = {}
        query = MAOSMonthlyKPI.objects.filter(cell__technology='4G',thrp_bits_dl__gt=0)
        for raw,month in query.order_by().values_list('cell__site__site_id','month_date').distinct().iterator(chunk_size=10000):
            key = by_raw.get(raw,raw)
            months[month].add(key)
            first[key] = min(first.get(key,month),month)
        cache['_neighborhood_positive'] = months,first
    return cache['_neighborhood_positive']


def select_virtual(candidates):
    bins = {}
    for candidate in candidates:
        if not 50 <= candidate['distance_m'] < 10000:
            continue
        bin_id,bearing = bin_and_bearing(candidate['bearing_deg'])
        key = math.floor(candidate['distance_m']+.5),id_key(candidate['site_id'])
        if bin_id not in bins or key < bins[bin_id][0]:
            bins[bin_id] = key,{**candidate,'bin':bin_id,'bearing_deg':bearing}
    return [bins[key][1] for key in sorted(bins)]


def neighborhood(site,cutoff=None,cache=None):
    cache = cache if cache is not None else {}
    groups,by_raw = inventory(cache)
    origin = by_raw.get(site.site_id,site.site_id)
    mode = scheme(site)
    first = {}
    eligible = None
    if cutoff is not None:
        cutoff = cutoff.replace(day=1)
        months,first = traffic_history(cache)
        eligible = set().union(*(months[offset(cutoff,i)] for i in (-3,-2,-1)))
    if '_neighborhood_geometry' not in cache:
        rows=list(groups.values())
        cache['_neighborhood_geometry']=(rows,np.radians([r['latitude'] for r in rows]),
            np.radians([r['longitude'] for r in rows]),np.asarray([r['cluster_id'] for r in rows]))
    rows,latitudes,longitudes,clusters=cache['_neighborhood_geometry']
    lat,lon=math.radians(site.latitude),math.radians(site.longitude)
    a=np.sin((latitudes-lat)/2)**2+math.cos(lat)*np.cos(latitudes)*np.sin((longitudes-lon)/2)**2
    distances=6371000*2*np.arcsin(np.sqrt(np.clip(a,0,1)))
    allowed=np.asarray([r['site_id']!=origin and (eligible is None or r['site_id'] in eligible)
        and (cutoff is None or (cutoff not in r['launch_dates'] and first.get(r['site_id'],date.max)<cutoff)) for r in rows]) & (distances>=50)
    nearest_eligible=float(distances[allowed].min()) if allowed.any() else None
    wanted=(distances<10000.001) | ((clusters==site.cluster_id) if site.cluster_id!=-1 else False)
    wanted &= allowed
    candidates = []
    for index in np.where(wanted)[0]:
        row=rows[index]
        key=row['site_id']
        if key == origin or (eligible is not None and key not in eligible):
            continue
        if cutoff is not None and (cutoff in row['launch_dates'] or first.get(key,date.max)>=cutoff):
            continue
        distance = haversine(site.latitude,site.longitude,row['latitude'],row['longitude'])
        if distance < 50:
            continue
        recent_known = min((d for d in row['launch_dates'] if cutoff is None or d<cutoff),default=None)
        recent_basis = 'site_launch' if recent_known else 'site_launch_unknown; first_positive_lte_is_only_a_proxy'
        lte_start=first.get(key)
        candidates.append({'site_id':key,'site_ids':row['site_ids'],'site_name':row['site_name'],
            'latitude':row['latitude'],'longitude':row['longitude'],'cluster_id':row['cluster_id'],
            'distance_m':distance,'bearing_deg':compute_bearing(site.latitude,site.longitude,row['latitude'],row['longitude']),
            'tier':tier(distance,mode),'distance_band':distance_band(distance),
            'member_recent_launch':bool(offset(cutoff,-3)<=recent_known<cutoff) if cutoff and recent_known else None,
            'member_recent_lte_activation':bool(cutoff and lte_start and offset(cutoff,-3)<=lte_start<cutoff),
            'recent_launch_basis':recent_basis})
    scopes = {'tier1':[],'tier2':[],'cluster':[],'virtual_cluster':[],
              'distance_0_2':[],'distance_2_5':[],'distance_5_10':[]}
    for row in candidates:
        if row['tier']:
            scopes[row['tier']].append(row)
        if row['distance_band']:
            scopes[row['distance_band']].append(row)
        if site.cluster_id!=-1 and row['cluster_id']==site.cluster_id:
            scopes['cluster'].append(row)
    if mode=='extended':
        scopes['virtual_cluster'] = select_virtual(candidates)
    members = scopes['virtual_cluster']
    distances = [r['distance_m'] for r in members]
    return {'tier_scheme':mode,'cluster_id':site.cluster_id,'canonical_site_id':origin,
        'nearest_eligible_site_m':nearest_eligible,
        'labels':labels(mode),'cutoff':cutoff.isoformat() if cutoff else None,'scopes':scopes,
        'virtual_id':f'V_{site.site_id}' if mode=='extended' and members else None,
        'virtual_name':f'{site.site_name}_vis_cluster' if mode=='extended' and members else None,
        'vis_members':members,'vis_n_bins_filled':len(members) if mode=='extended' else None,
        'vis_n_members':len(members) if mode=='extended' else None,
        'vis_max_dist_m':max(distances) if distances else None,
        'vis_median_dist_m':median(distances) if distances else None,
        'support_level':('isolated' if not members else 'low' if len(members)<=2 else 'ok') if mode=='extended' else None,
        'membership_version':policy()['version'],
        'membership_note':'Positive LTE traffic in the three complete pre-cutoff months; same-month launches and co-located/event sites excluded.' if cutoff else 'Current geographic inventory; not event-time membership.'}


def raw_ids(members):
    return list(dict.fromkeys(key for member in members for key in member['site_ids']))


def monthly_rows(month,cache):
    if ('_neighborhood_totals',month) not in cache:
        from .maos_context import monthly_annotations
        rows = MAOSMonthlyKPI.objects.filter(month_date=month).values('cell__site__site_id').annotate(**monthly_annotations())
        cache['_neighborhood_totals',month] = {r['cell__site__site_id']:r for r in rows}
    return cache['_neighborhood_totals',month]


def traffic_sample(context,cache):
    if context['tier_scheme']!='extended' or not context['cutoff']:
        return {'vis_sampled_traffic_gb':None,'vis_mean_traffic_per_member_gb':None,'traffic_all_sites_within_R':None}
    previous = offset(date.fromisoformat(context['cutoff']),-1)
    totals = monthly_rows(previous,cache)
    def total(members):
        values = []
        for member in members:
            observed = [totals[key].get('traffic_bits') for key in member['site_ids'] if key in totals and totals[key].get('traffic_bits') is not None]
            if not observed:
                return None  # fixed membership: no partial sum masquerading as total
            values.append(sum(observed)/8e9)
        return sum(values) if values else None
    sampled = total(context['vis_members'])
    all_members = context['scopes']['tier1']+context['scopes']['tier2']
    return {'vis_sampled_traffic_gb':sampled,'vis_mean_traffic_per_member_gb':sampled/context['vis_n_members'] if sampled is not None and context['vis_n_members'] else None,
            'traffic_all_sites_within_R':total(all_members),'traffic_month':previous.isoformat(),
            'traffic_note':'GB/month sampled from one location per bin. Mean divides by selected locations. Complete 10 km total reported separately; missing members keep totals NULL.'}


def sample_series(members):
    """Traffic-only current-membership series; incomplete samples stay NULL."""
    from django.db.models import Sum
    ids=raw_ids(members)
    totals=defaultdict(dict)
    for row in MAOSMonthlyKPI.objects.filter(cell__site__site_id__in=ids).values('month_date','cell__site__site_id').annotate(bits=Sum('thrp_bits_dl')):
        totals[row['month_date']][row['cell__site__site_id']]=row['bits']
    result=[]
    for month,rows in sorted(totals.items()):
        values=[]
        for member in members:
            observed=[rows[key] for key in member['site_ids'] if rows.get(key) is not None]
            if observed:
                values.append(sum(observed)/8e9)
        total=sum(values) if len(values)==len(members) and members else None
        result.append({'month':month.strftime('%Y-%m'),'thrp_dl_gb':total,'vis_sampled_traffic_gb':total,
            'vis_mean_traffic_per_member_gb':total/len(members) if total is not None else None,
            'vis_n_members':len(members),'reporting_members':len(values),'reporting_sites':len(values)})
    return result


def public_context(site,cutoff,cache=None):
    cache = cache if cache is not None else {}
    context = neighborhood(site,cutoff,cache)
    return {**{k:v for k,v in context.items() if k!='scopes'},**traffic_sample(context,cache)}


def analysis_payload(site,params=None):
    from .maos_context import default_profile_cutoff
    params=params or {}
    events=[e for e in site.network_events.all() if e.is_current]
    cutoff=default_profile_cutoff(site)
    if params.get('event_key'):
        chosen=next((e for e in events if e.event_key==params['event_key']),None)
        if chosen is None:
            return {'error':'Event was not found at this site.'},404
        cutoff=chosen.effective_date
    elif params.get('as_of'):
        try:
            value=params['as_of']
            cutoff=date.fromisoformat(value+'-01' if len(value)==7 else value)
            if cutoff.day!=1:
                raise ValueError()
        except (ValueError,TypeError):
            return {'error':'as_of must be a calendar month (YYYY-MM).'},400
    cache=getattr(site,'_live_neighborhood_cache',None)
    if cache is None:
        cache={};site._live_neighborhood_cache=cache
    return {'current':current_snapshot(site),'event':public_context(site,cutoff,cache),
        'events':[{'event_key':e.event_key,'date':e.effective_date.isoformat(),
            'label':e.details.get('label',e.event_type)} for e in events]},200


def current_snapshot(site):
    return {'snapshot_kind':'current','cutoff':site.vis_snapshot_cutoff,'tier_scheme':scheme(site),
        'cluster_id':site.cluster_id,'canonical_site_id':site.canonical_site_id or site.site_id,
        **{name:getattr(site,name) for name in ('vis_members','vis_n_bins_filled','vis_n_members','vis_max_dist_m','vis_median_dist_m',
            'vis_sampled_traffic_gb','vis_mean_traffic_per_member_gb','traffic_all_sites_within_R','support_level')},
        'virtual_id':f'V_{site.site_id}' if site.cluster_id==-1 and site.vis_n_members else None,
        'virtual_name':f'{site.site_name}_vis_cluster' if site.cluster_id==-1 and site.vis_n_members else None,
        'labels':labels(scheme(site)), 'note':'Stored current version; historical event membership is rebuilt separately.'}


def angular_bins(site):
    context=current_runtime(site)
    bins=[0]*12
    for row in context['scopes']['tier1']+context['scopes']['tier2']:
        bin_id,_=bin_and_bearing(row['bearing_deg'])
        bins[bin_id]+=1
    return bins


def current_runtime(site):
    if not hasattr(site,'_live_neighborhood'):
        cache=getattr(site,'_live_neighborhood_cache',None)
        if cache is None:
            cache={};site._live_neighborhood_cache=cache
        latest=MAOSMonthlyKPI.objects.aggregate(value=Max('month_date'))['value']
        cutoff=offset(latest,1) if latest else date.today().replace(day=1)
        site._live_neighborhood=neighborhood(site,cutoff,cache)
    return site._live_neighborhood


def map_links(site):
    """Current, canonical tier links; noise draws only its virtual sample."""
    context=current_runtime(site)
    virtual=context['tier_scheme']=='extended'
    members=context['vis_members'] if virtual else context['scopes']['tier1']+context['scopes']['tier2']
    return {'tier_scheme':context['tier_scheme'],'cluster_id':site.cluster_id,
        'membership_kind':'current','cutoff':context['cutoff'],'labels':context['labels'],
        'link_scope':'virtual_cluster' if virtual else 'tiers','members':members}


def popup_anp(site):
    from .anp import ANPComputer
    context=current_runtime(site)
    rows=context['scopes']['tier1']+context['scopes']['tier2']
    values=ANPComputer(tier_scheme=context['tier_scheme']).compute_anp(site.latitude,site.longitude,
        [(r['latitude'],r['longitude']) for r in rows],[r['distance_m'] for r in rows])
    for index in (1,2):
        if not values[f'n_tier{index}']:
            values[f't{index}_nearest_m']=None
            values[f'avg_neighbor_dist_t{index}_m']=None
    values['angular_bins']=angular_bins(site)
    return values


def popup_spatial(site):
    """Return current physical-neighbor values; legacy rows may lack NULL support."""
    from django.core.exceptions import ObjectDoesNotExist
    try:
        stored=site.spatial_features
    except ObjectDoesNotExist:
        return None
    context=current_runtime(site)
    rows=context['scopes']['tier1']+context['scopes']['tier2']
    result={key:getattr(stored,key) for key in ('n_2g_sites_2km','n_3g_sites_2km','neighbor_avg_antenna_height_m')}
    result['dist_nearest_site_m']=context['nearest_eligible_site_m']
    for radius in (1,2,3):
        result[f'n_sites_{radius}km']=sum(r['distance_m']<=radius*1000 for r in rows)
    result['n_4g_sites_2km']=result['n_sites_2km']
    return result


def refresh_current(progress=None):
    report = reconcile_locations()
    latest = MAOSMonthlyKPI.objects.aggregate(value=Max('month_date'))['value']
    cutoff = offset(latest,1) if latest else date.today().replace(day=1)
    cache, pending = {},[]
    fields = ['vis_members','vis_n_bins_filled','vis_n_members','vis_max_dist_m','vis_median_dist_m',
              'vis_sampled_traffic_gb','vis_mean_traffic_per_member_gb','traffic_all_sites_within_R','support_level']
    for index,site in enumerate(Site.objects.all(),1):
        context = public_context(site,cutoff,cache)
        for field in fields:
            setattr(site,field,context[field])
        site.vis_snapshot_cutoff,site.vis_snapshot_kind = cutoff,'current'
        pending.append(site)
        if progress and index%250==0:
            progress({'processed':index,'total':report['sites']})
    Site.objects.bulk_update(pending,fields+['vis_snapshot_cutoff','vis_snapshot_kind'],batch_size=100)
    report.update(cutoff=cutoff.isoformat(),snapshot_rows=len(pending),errors=0)
    return report


def refresh_context_features(progress=None):
    """Update radius-dependent persisted display features without raster work."""
    from core.models import ANPFeatures,SpatialFeatures
    from .anp import ANPComputer
    latest=MAOSMonthlyKPI.objects.aggregate(value=Max('month_date'))['value']
    cutoff=offset(latest,1) if latest else date.today().replace(day=1)
    cache={}
    anps={row.site_id:row for row in ANPFeatures.objects.all()}
    spatial={row.site_id:row for row in SpatialFeatures.objects.all()}
    anp_pending,spatial_pending=[],[]
    spatial_fields=['dist_nearest_site_m','n_sites_1km','n_sites_2km','n_sites_3km','n_4g_sites_2km']
    # Legacy spatial columns are non-nullable; only persist supported values.
    for index,site in enumerate(Site.objects.all(),1):
        context=neighborhood(site,cutoff,cache)
        neighbors=context['scopes']['tier1']+context['scopes']['tier2']
        values=ANPComputer(tier_scheme=context['tier_scheme']).compute_anp(site.latitude,site.longitude,
            [(r['latitude'],r['longitude']) for r in neighbors],[r['distance_m'] for r in neighbors])
        row=anps.get(site.pk)
        if row:
            for name,value in values.items():
                setattr(row,name,float(value))
            anp_pending.append(row)
        row=spatial.get(site.pk)
        if row and context['nearest_eligible_site_m'] is not None:
            row.dist_nearest_site_m=context['nearest_eligible_site_m']
            for radius in (1,2,3):
                setattr(row,f'n_sites_{radius}km',sum(r['distance_m']<=radius*1000 for r in neighbors))
            row.n_4g_sites_2km=row.n_sites_2km
            spatial_pending.append(row)
        if progress and index%500==0:
            progress({'processed':index})
    if anp_pending:
        ANPFeatures.objects.bulk_update(anp_pending,list(values),batch_size=200)
    if spatial_pending:
        SpatialFeatures.objects.bulk_update(spatial_pending,spatial_fields,batch_size=200)
    return {'anp_rows':len(anp_pending),'supported_spatial_rows':len(spatial_pending),'errors':0}
