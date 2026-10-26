"""User-approved static context, event configuration and cluster KPI formulas."""
from collections import defaultdict
from datetime import date
from functools import lru_cache
import json
import math
from pathlib import Path

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Avg, Max
from pyproj import Transformer
from shapely.geometry import MultiPoint, Point

from core.models import Cell, MAOSMonthlyKPI, Site
from services.models.preprocessing.maos_aggregation import normalize_monthly_totals
from services.models.preprocessing.network_events import bandwidth_from_prb
from services.utils.geo_utils import haversine
from services.visualization.dem_processor import DEMProcessor

ROOT = Path(__file__).resolve().parents[3]


@lru_cache(maxsize=1)
def context_policy():
    return json.loads((ROOT/'config/feature_context.json').read_text(encoding='utf-8'))


def terrain_relief(slope):
    if slope is None or not math.isfinite(slope):
        return None
    policy=context_policy()
    index=sum(slope>=threshold for threshold in policy['terrain_relief_thresholds_deg'])
    return policy['terrain_relief_classes'][index]


@lru_cache(maxsize=8192)
def ground_elevation(latitude,longitude):
    return DEMProcessor(str(ROOT/'data/geographic/dem/copernicus_glo30.vrt')).get_elevation(latitude,longitude)


def relation(site,name):
    try:
        return getattr(site,name)
    except ObjectDoesNotExist:
        return None


def antenna_height(cells):
    values=[c.antenna_height_m for c in cells if c.antenna_height_m is not None
            and math.isfinite(c.antenna_height_m) and c.antenna_height_m>0]
    return sum(values)/len(values) if values else context_policy()['default_antenna_height_m']


def post_event_configuration(site,cutoff,histories=None):
    """KPI-active earlier cells plus this action's cells, projected to the plan.

    PRB configuration may use the event month, but never a later month. It is
    distinct from pre-event performance features and from predicted outcomes.
    """
    cells=list(site.cells.all())
    rows=histories if histories is not None else list(MAOSMonthlyKPI.objects.filter(
        cell__site=site,month_date__lte=cutoff,
    ).order_by('month_date').values_list('cell_id','month_date','thrp_bits_dl','prb_dl_available'))
    active=set()
    latest_prb={}
    for pk,month,traffic,prb in rows:
        if month>cutoff:
            continue
        if traffic is not None and traffic>0:
            active.add(pk)
        if prb is not None and math.isfinite(prb) and prb>=0:
            previous=latest_prb.get(pk)
            if previous is None or month>previous[0]:
                latest_prb[pk]=(month,prb)
    added={key for event in site.network_events.all() if event.is_current and event.effective_date<=cutoff
           for key in event.details.get('cell_ids',[])
           if event.details.get('cell_activation_months',{}).get(key,'9999')<=cutoff.isoformat()}
    after=[c for c in cells if c.pk in active or c.cell_id in added]
    # For a current non-event profile, the cutoff is after the last report.
    tolerance=context_policy()['sector_azimuth_tolerance_deg']
    sectors={int(round((c.azimuth%360)/tolerance))%int(360/tolerance) for c in after}
    lte=[c for c in after if c.technology=='4G']
    prbs=[latest_prb.get(c.pk,(None,None))[1] for c in lte]
    bandwidths=[bandwidth_from_prb(value) for value in prbs]
    total_prb=sum(prbs) if prbs and all(value is not None for value in prbs) else None
    total_bw=sum(bandwidths) if bandwidths and all(value is not None for value in bandwidths) else None
    return {'sector_count_after':len(sectors) if after else None,
        'cells_per_sector_after':len(after)/len(sectors) if sectors else None,
        'antenna_height_m':antenna_height(after or cells),
        'total_bw_after_mhz':total_bw,'total_prb_available':total_prb,
        'post_event_configuration_support':{'cell_ids':[c.cell_id for c in after],
            'evidenced_cells':len(after),'plan_cells':len(cells),'lte_cells':len(lte),
            'prb_reporting_cells':sum(value is not None for value in prbs),
            'unmapped_bandwidth_prbs':{c.cell_id:prb for c,prb,bw in zip(lte,prbs,bandwidths) if prb is not None and bw is None},
            'configuration_cutoff':cutoff.isoformat(),'performance_uses_event_month':False,
            'scope':'KPI-evidenced LTE capacity; no PRB inference for unreported 2G/3G',
            'antenna_height_source':'positive cell-plan value or approved 25 m fallback'}}


def static_inventory(cache):
    key='_approved_static_inventory'
    if key not in cache:
        heights={row['site_id']:row['height'] for row in Cell.objects.filter(antenna_height_m__gt=0)
                 .values('site_id').annotate(height=Avg('antenna_height_m'))}
        cache[key]=[{**row,'antenna_height_m':heights.get(row['id'],context_policy()['default_antenna_height_m'])}
            for row in Site.objects.values('id','site_id','latitude','longitude','cluster_id',
                'clutter_features__avg_building_height_m','geometric_features__z_antenna_m')]
    return cache[key]


def absolute_antenna_elevation(row, prefer_stored=True):
    if prefer_stored and row.get('geometric_features__z_antenna_m') is not None:
        return row['geometric_features__z_antenna_m']
    ground=ground_elevation(row['latitude'],row['longitude'])
    building=row.get('clutter_features__avg_building_height_m')
    if ground is None or building is None:
        return None
    return ground+building+row['antenna_height_m']


def static_context(site,cache):
    inventory=static_inventory(cache)
    row=next((r for r in inventory if r['site_id']==site.site_id),None)
    values={'cluster_id':site.cluster_id}
    if row:
        values['z_antenna_m']=absolute_antenna_elevation(row,not cache.get('_force_dem',False))
    neighbors=[r for r in inventory if r['site_id']!=site.site_id and
        haversine(site.latitude,site.longitude,r['latitude'],r['longitude'])<=context_policy()['neighbor_radius_m']]
    heights=[absolute_antenna_elevation(r,not cache.get('_force_dem',False)) for r in neighbors]
    supported=[height for height in heights if height is not None]
    values['neighbor_avg_antenna_height_m']=sum(supported)/len(supported) if supported else None
    values['static_context_support']={'neighbor_count':len(neighbors),'neighbor_height_count':len(supported),
        'height_formula':'DEM ground elevation + stored building-height estimate + antenna height',
        'static_population':True,'static_geographic_context':True}
    group=[r for r in inventory if r['cluster_id']==site.cluster_id] if site.cluster_id!=-1 else [row] if row else []
    if group:
        project=Transformer.from_crs('EPSG:4326','EPSG:32632',always_xy=True)
        points=[Point(*project.transform(r['longitude'],r['latitude'])) for r in group]
        hull=MultiPoint(points).convex_hull
        area=hull.area if hull.area>0 else hull.buffer(100).area
        origin=Point(*project.transform(site.longitude,site.latitude))
        values.update({'cluster_size':len(group),'cluster_density_sites_per_km2':len(group)/(area/1e6),
            'dist_to_cluster_centroid_m':origin.distance(MultiPoint(points).centroid)})
    return values


def cluster_prelaunch_values(site,cutoff,cache):
    from services.models.features.maos_context import monthly_annotations
    from services.models.similarity.historical import month_offset
    previous=month_offset(cutoff,-1)
    cache_key=('_cluster_previous_month',previous)
    if cache_key not in cache:
        rows=MAOSMonthlyKPI.objects.filter(month_date=previous).values('cell__site__site_id').annotate(**monthly_annotations())
        cache[cache_key]={r['cell__site__site_id']:r for r in rows}
    inventory=static_inventory(cache)
    members=[r['site_id'] for r in inventory if r['cluster_id']==site.cluster_id] if site.cluster_id!=-1 else [site.site_id]
    rows=[cache[cache_key][member] for member in members if member in cache[cache_key]]
    sums={}
    for name in monthly_annotations():
        observed=[r[name] for r in rows if r.get(name) is not None]
        sums[name]=sum(observed) if observed else None
    metrics=normalize_monthly_totals(sums)
    return {'avg_traffic_dl_gb':metrics['thrp_dl_gb'],'avg_users':metrics['active_users_avg'],
        'avg_prb_util_pct':metrics['prb_util_dl_pct'],'avg_cqi':metrics['cqi_avg'],
        'cluster_avg_users':metrics['active_users_avg'],
        'cluster_avg_traffic_gb':metrics['thrp_dl_gb']/len(rows) if metrics['thrp_dl_gb'] is not None and rows else None,
        'cluster_pre_dl_throughput_kbps':metrics['dl_throughput_kbps'],
        'cluster_pre_dl_packet_delay_ms':metrics['dl_packet_delay_ms'],
        'cluster_pre_cell_availability_pct':metrics['cell_availability_pct'],
        'cluster_prelaunch_support':{'month':previous.isoformat(),'member_sites':len(members),
            'reporting_sites':len(rows),'reporting_cells':sums.get('reporting_cells'),
            'membership':'static site cluster; noise is an independent singleton',
            'active_users_aggregation':'sum of cell averages'}}


def approved_feature_values(site,cutoff,cache):
    values=post_event_configuration(site,cutoff)
    values.update(static_context(site,cache))
    geometry=relation(site,'geometric_features')
    values['terrain_relief_class']=terrain_relief(getattr(geometry,'terrain_slope_deg',None))
    clutter=relation(site,'clutter_features')
    for key in ('dominant_clutter','clutter_entropy_2km','pct_building_area_1km','avg_building_height_m'):
        values[key]=getattr(clutter,key,None)
    values.update(cluster_prelaunch_values(site,cutoff,cache))
    return values


def popup_context(site):
    cached=getattr(site,'_approved_popup_context',None)
    if cached is not None:
        return cached
    from services.models.features.maos_context import default_profile_cutoff
    cutoff=default_profile_cutoff(site)
    cache={}
    baseline=cluster_prelaunch_values(site,cutoff,cache)
    context=static_context(site,cache)
    fields=('cluster_id','cluster_size','cluster_density_sites_per_km2',
            'cluster_avg_traffic_gb','cluster_avg_users','dist_to_cluster_centroid_m')
    combined={**context,**baseline}
    result={'cluster_prelaunch':baseline,'cluster_context':{key:combined.get(key) for key in fields},
        'configuration_support':post_event_configuration(site,cutoff)['post_event_configuration_support']}
    site._approved_popup_context=result
    return result


def backfill_approved_context(progress=None):
    """Persist source-derived configuration and static heights without full raster extraction."""
    from core.models import ConfigurationFeatures, GeometricFeatures, SpatialFeatures
    from services.models.preprocessing.network_events import effective_event_date
    from services.models.similarity.historical import month_offset
    latest=MAOSMonthlyKPI.objects.aggregate(month=Max('month_date'))['month']
    histories=defaultdict(list)
    for pk,month,traffic,prb,site_pk in MAOSMonthlyKPI.objects.order_by('month_date').values_list(
        'cell_id','month_date','thrp_bits_dl','prb_dl_available','cell__site_id').iterator(chunk_size=10000):
        histories[site_pk].append((pk,month,traffic,prb))
    cache={'_force_dem':True}
    static_inventory(cache)
    count=0
    for site in Site.objects.prefetch_related('cells','network_events').select_related('geometric_features','clutter_features'):
        cutoff=effective_event_date(site) or (month_offset(latest,1) if latest else date.today().replace(day=1))
        config=post_event_configuration(site,cutoff,histories.get(site.pk,[]))
        config.pop('post_event_configuration_support')
        ConfigurationFeatures.objects.filter(site=site).update(**config)
        context=static_context(site,cache)
        geometry=relation(site,'geometric_features')
        if geometry and context.get('z_antenna_m') is not None:
            GeometricFeatures.objects.filter(site=site).update(z_antenna_m=context['z_antenna_m'],
                terrain_relief_class=terrain_relief(geometry.terrain_slope_deg))
        SpatialFeatures.objects.filter(site=site).update(neighbor_avg_antenna_height_m=context.get('neighbor_avg_antenna_height_m'))
        count+=1
        if progress and (count%250==0):
            progress({'processed':count})
    return {'sites_updated':count,'errors':0}


def backfill_approved_configuration():
    """Bulk KPI-only refresh; avoids re-reading unchanged static rasters."""
    from core.models import ConfigurationFeatures
    from services.models.preprocessing.network_events import effective_event_date
    from services.models.similarity.historical import month_offset
    latest=MAOSMonthlyKPI.objects.aggregate(month=Max('month_date'))['month']
    histories=defaultdict(list)
    for pk,month,traffic,prb,site_pk in MAOSMonthlyKPI.objects.values_list(
        'cell_id','month_date','thrp_bits_dl','prb_dl_available','cell__site_id').iterator(chunk_size=10000):
        histories[site_pk].append((pk,month,traffic,prb))
    fields=('sector_count_after','cells_per_sector_after','antenna_height_m','total_bw_after_mhz','total_prb_available')
    existing={row.site_id:row for row in ConfigurationFeatures.objects.all()}
    pending=[]
    for site in Site.objects.prefetch_related('cells','network_events'):
        cutoff=effective_event_date(site) or (month_offset(latest,1) if latest else date.today().replace(day=1))
        values=post_event_configuration(site,cutoff,histories.get(site.pk,[]))
        row=existing.get(site.pk)
        if row is not None:
            for field in fields:
                setattr(row,field,values[field])
            pending.append(row)
    ConfigurationFeatures.objects.bulk_update(pending,fields,batch_size=500)
    return {'configuration_rows_updated':len(pending),'errors':0}
