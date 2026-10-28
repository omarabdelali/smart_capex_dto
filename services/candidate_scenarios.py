"""Plan a site without adding it to the operational network."""
from datetime import date
from statistics import median
from calendar import monthrange
import math
from types import SimpleNamespace
import numpy as np
from sklearn.cluster import DBSCAN
from django.db.models import Max
from core.models import CandidateScenario, MAOSMonthlyKPI, Site, RadioNetworkEvent
from services.models.features.neighborhood import inventory, neighborhood
from services.models.similarity.historical import month_offset, load_network, context_features
from services.models.features.approved_context import cluster_prelaunch_values, context_policy, static_context
from services.models.features.maos_context import calculate_user_context, USER_CONTEXT_FIELDS
from services.models.features.geometric import GeometricFeatureExtractor
from services.models.features.clutter import ClutterFeatureExtractor
from services.models.features.population import population_features
from services.models.features.road_features import RoadFeatureExtractor
from services.models.similarity.catalog import SIMILARITY_FIELDS, OPTIONAL
from services.data_scope import tdd_cell, normalized


def clean(value):
    if isinstance(value,dict): return {str(k):clean(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)): return [clean(v) for v in value]
    if isinstance(value,(np.integer,np.floating)): value=value.item()
    if isinstance(value,float) and not math.isfinite(value): return None
    if isinstance(value,date): return value.isoformat()
    return value


def physical_sites(site):
    return Site.objects.filter(canonical_site_id=site.canonical_site_id) if site.canonical_site_id else Site.objects.filter(pk=site.pk)


def validate(data):
    try:
        lat=float(data['latitude']); lon=float(data['longitude']); sectors=int(data['sector_count'])
        name=str(data.get('name','Candidate site')).strip()
        latest=MAOSMonthlyKPI.objects.aggregate(month=Max('month_date'))['month']
        cutoff=date.fromisoformat(str(data['event_month'])[:7]+'-01') if data.get('event_month') else (month_offset(latest,1) if latest else date.today().replace(day=1))
    except (ValueError,TypeError,KeyError):
        raise ValueError('Provide valid coordinates, sector count, technology, band and planned month.')
    if not (30<=lat<=38 and 7<=lon<=12): raise ValueError('Choose coordinates within the supported Tunisia map extent.')
    if not 1<=sectors<=12 or not name or len(name)>120:
        raise ValueError('Provide a name and 1–12 sectors.')
    mode=data.get('mode','new'); action=data.get('action','technology')
    if mode not in ('new','existing') or action not in ('technology','band','cell','bandwidth'):
        raise ValueError('Choose a supported site and addition type.')
    entries=data.get('technologies') or [{'technology':data.get('technology'),'bands':data.get('band')}]
    if not isinstance(entries,list) or not entries: raise ValueError('Add at least one technology and its bands.')
    additions=[]; seen=set()
    for entry in entries:
        technology=str(entry.get('technology','')).upper().strip().replace('LTE','4G')
        bands=entry.get('bands',[])
        if isinstance(bands,str): bands=bands.replace(';',',').split(',')
        if not isinstance(bands,list): raise ValueError('Bands must be a list or separated by commas or semicolons.')
        bands=sorted({str(b).upper().strip() for b in bands if str(b).strip()})
        if technology not in ('2G','3G','4G') or technology in seen or not bands:
            raise ValueError('Select each technology once and enter at least one band for it.')
        if any(tdd_cell(b) or 'TDD' in normalized(b) for b in bands):
            raise ValueError('TDD and C-band cells are excluded from the current project scope.')
        seen.add(technology);additions.append({'technology':technology,'bands':bands})
    additions.sort(key=lambda item:item['technology'])
    site=None
    if mode=='existing':
        site=Site.objects.filter(site_id=str(data.get('site_id',''))).first()
        if not site: raise ValueError('Choose an existing site before calculating an addition.')
        lat,lon=site.latitude,site.longitude
        from core.models import Cell
        cells=Cell.objects.filter(site__in=physical_sites(site))
        present=set(cells.values_list('technology',flat=True))
        if action=='technology' and present&seen:
            raise ValueError('Technology addition requires technologies that are not already in the site plan; choose band or cell addition for an existing technology.')
        if action in ('band','cell','bandwidth') and (len(seen)!=1 or not seen<=present):
            raise ValueError('Band, cell or bandwidth changes require one technology already present at the site.')
        if action=='band':
            existing={str(b).upper() for b in cells.filter(technology=additions[0]['technology']).values_list('band',flat=True)}
            if existing.intersection(additions[0]['bands']):
                raise ValueError('A selected band already exists at this site; use cell addition for an existing band.')
        if action=='bandwidth':
            target=cells.filter(cell_id=str(data.get('cell_id',''))).first()
            if not target or target.technology!='4G' or additions[0]['technology']!='4G':
                raise ValueError('Choose an existing LTE cell ID for a bandwidth change.')
            if additions[0]['bands']!=[target.band.upper()]:
                raise ValueError('Enter the selected cell’s existing band for a bandwidth change.')
            try:
                old=float(data['previous_bandwidth_mhz']);new=float(data['new_bandwidth_mhz'])
            except (ValueError,TypeError,KeyError):
                raise ValueError('Enter the previous and new LTE bandwidths in MHz.')
            if old not in (5,10,15,20) or new not in (5,10,15,20) or old==new:
                raise ValueError('LTE bandwidths must be different values from 5, 10, 15 or 20 MHz.')
    else:
        action='technology'
    event_type=('TECHNOLOGY_ADDED' if mode=='new' and len(additions)==1 else 'SITE_ADDED' if mode=='new'
        else ('BANDWIDTH_UPGRADE' if new>old else 'BANDWIDTH_DOWNGRADE') if action=='bandwidth'
        else {'technology':'TECHNOLOGY_ADDED','band':'FREQUENCY_BAND_ADDED','cell':'CELL_ADDED'}[action])
    if latest and cutoff<month_offset(latest,1): raise ValueError('The planned month must be after the latest available KPI month.')
    return {'name':name,'latitude':lat,'longitude':lon,'sector_count':sectors,'mode':mode,'action':action,
        'site_id':site.site_id if site else None,'technologies':additions,'event_type':event_type,
        'cell_id':str(data.get('cell_id','')) if action=='bandwidth' else None,
        'previous_bandwidth_mhz':old if action=='bandwidth' else None,'new_bandwidth_mhz':new if action=='bandwidth' else None,
        'profile_id':str(data.get('profile_id') or ''),'event_month':cutoff.isoformat()}


def classify_location(lat,lon,cache):
    groups,_=inventory(cache); rows=list(groups.values())
    if not rows: return -1,{'method':'DBSCAN','nearby_clusters':[]}
    from services.utils.geo_utils import haversine
    nearest=min(haversine(lat,lon,r['latitude'],r['longitude']) for r in rows)
    if nearest<50: raise ValueError('The point is within 50 m of an existing physical site; choose a new location.')
    coords=np.radians([[r['latitude'],r['longitude']] for r in rows]+[[lat,lon]])
    labels=DBSCAN(eps=2000/6371000,min_samples=3,metric='haversine',algorithm='ball_tree').fit_predict(coords)
    candidate=labels[-1]
    adjacent=sorted({r['cluster_id'] for r,label in zip(rows,labels[:-1]) if label==candidate and r['cluster_id']!=-1}) if candidate!=-1 else []
    if candidate==-1:
        cluster=-1;members=[];kind='virtual'
    else:
        members=[r['site_id'] for r,label in zip(rows,labels[:-1]) if label==candidate]
        cluster=adjacent[0] if len(adjacent)==1 else -2
        kind='existing' if len(adjacent)==1 else 'new' if not adjacent else 'merged'
        # Only this local calculation sees the hypothetical memberships.
        for key in members:
            groups[key]={**groups[key],'cluster_id':cluster}
    return cluster,{'method':'hypothetical DBSCAN (2 km, minimum 3 physical locations)',
        'kind':kind,'nearby_clusters':adjacent,'member_site_ids':members,
        'nearest_site_m':nearest,'inventory':'current physical locations; hypothetical labels are not persisted'}


def calculate_features(inputs):
    cutoff=date.fromisoformat(inputs['event_month']); cache={}
    lat,lon=inputs['latitude'],inputs['longitude']
    technologies=[item['technology'] for item in inputs['technologies']]
    bands=sorted({band for item in inputs['technologies'] for band in item['bands']})
    if inputs['mode']=='existing':
        from services.models.similarity.feature_vector import build_site_similarity_vector
        site=Site.objects.prefetch_related('cells','network_events').get(site_id=inputs['site_id'])
        values=build_site_similarity_vector(site,as_of_date=cutoff,snapshot_cache=cache,allow_current_roads=True)
        from core.models import Cell
        present=set(Cell.objects.filter(site__in=physical_sites(site)).values_list('technology',flat=True))
        from services.models.features.maos_context import monthly_annotations
        from services.models.preprocessing.maos_aggregation import normalize_monthly_totals
        rows=MAOSMonthlyKPI.objects.filter(cell__site__in=physical_sites(site),month_date__gte=month_offset(cutoff,-3),month_date__lt=cutoff).values('month_date').annotate(**monthly_annotations()).order_by('month_date')
        monthly=[]
        for row in rows:
            m=normalize_monthly_totals(row);days=monthrange(row['month_date'].year,row['month_date'].month)[1]
            monthly.append({'pre_dl_traffic_gb_day':m['thrp_dl_gb']/days if m['thrp_dl_gb'] is not None else None,
                'pre_active_users':m['active_users_avg'],'pre_traffic_users':m['traffic_user_avg'],
                'pre_prb_util_dl_pct':m['prb_util_dl_pct'],'pre_cqi_avg':m['cqi_avg'],
                'pre_dl_throughput_kbps':m['dl_throughput_kbps'],'pre_dl_packet_delay_ms':m['dl_packet_delay_ms'],
                'pre_cell_availability_pct':m['cell_availability_pct']})
        for key in ('pre_dl_traffic_gb_day','pre_active_users','pre_traffic_users','pre_prb_util_dl_pct','pre_cqi_avg','pre_dl_throughput_kbps','pre_dl_packet_delay_ms','pre_cell_availability_pct'):
            found=[row[key] for row in monthly if row[key] is not None]
            values[key]=median(found) if found else None
        for out,key in [('pre_traffic_trend_3m_pct','pre_dl_traffic_gb_day'),('pre_prb_trend_3m_pct','pre_prb_util_dl_pct')]:
            found=[row[key] for row in monthly if row[key] is not None]
            values[out]=(found[-1]-found[0])/abs(found[0])*100 if len(found)>=2 and found[0]!=0 else None
        values['pre_profile_months_available']=len(monthly)
        values['pre_profile_completeness']=sum(v is not None for row in monthly for v in row.values())/(3*8)
        values.update(event_type=inputs['event_type'],tech_added='/'.join(technologies) if inputs['action']=='technology' else None,
            bands_added=','.join(bands) if inputs['action'] in ('technology','band') else None,
            sector_count_after=inputs['sector_count'],_event_technologies='/'.join(technologies))
        for tech in ('2g','3g','4g'):
            values['tech_before_'+tech]=tech.upper() in present
            values['tech_after_'+tech]=tech.upper() in (present|set(technologies))
        values['total_bw_after_mhz']=None;values['total_prb_available']=None
        values['total_capacity_after_mbps']=None;values['cells_per_sector_after']=None
        context=neighborhood(site,cutoff,cache)
        values['virtual_cluster_context']=context
        groups,_=inventory(cache)
        members=context['vis_members'] if site.cluster_id==-1 else [r for r in groups.values() if r['cluster_id']==site.cluster_id and site.site_id not in r['site_ids']]
        return clean(values),clean({'method':'existing site cluster','kind':'virtual' if site.cluster_id==-1 else 'existing',
            'nearby_clusters':[] if site.cluster_id==-1 else [site.cluster_id],'members':members})
    cluster,assignment=classify_location(lat,lon,cache)
    site=SimpleNamespace(pk=None,site_id='candidate',site_name=inputs['name'],latitude=lat,longitude=lon,
        cluster_id=cluster,canonical_site_id='')
    network=load_network(cutoff)
    values={key:None for key in SIMILARITY_FIELDS}
    values.update(site_id='candidate',event_type=inputs['event_type'],tech_added='/'.join(technologies) if inputs['event_type']=='TECHNOLOGY_ADDED' else None,bands_added=','.join(bands),
        sector_count_after=inputs['sector_count'],antenna_height_m=context_policy()['default_antenna_height_m'],
        feature_as_of_date=cutoff.isoformat(),tier_scheme='extended' if cluster==-1 else 'standard',cluster_id=cluster,
        _event_technologies='/'.join(technologies))
    for tech in ('2g','3g','4g'):
        values['tech_before_'+tech]=False
        values['tech_after_'+tech]=tech.upper() in technologies
    geometry=GeometricFeatureExtractor(); geo=geometry.extract_features('candidate',lat,lon,antenna_height_m=values['antenna_height_m'])
    clutter=ClutterFeatureExtractor(); land=clutter.extract_features('candidate',lat,lon)
    if geo.success: values.update(geometry.to_dict(geo))
    if land.success: values.update(clutter.to_dict(land))
    if geo.success and geo.elevation_m is not None and values.get('avg_building_height_m') is not None:
        values['z_antenna_m']=geo.elevation_m+values['avg_building_height_m']+values['antenna_height_m']
    else: values['z_antenna_m']=None
    population=population_features(lat,lon,values['tier_scheme']);values.update(population)
    values['population_quality']=values.pop('quality',None)
    values.update(context_features(site,network,cutoff,cache))
    spatial=static_context(site,cache)
    values['neighbor_avg_antenna_height_m']=spatial.get('neighbor_avg_antenna_height_m')
    if cluster!=-1:
        from pyproj import Transformer
        from shapely.geometry import MultiPoint,Point
        groups,_=inventory(cache)
        project=Transformer.from_crs('EPSG:4326','EPSG:32632',always_xy=True)
        points=[Point(*project.transform(r['longitude'],r['latitude'])) for r in groups.values() if r['cluster_id']==cluster]
        origin=Point(*project.transform(lon,lat));points.append(origin)
        hull=MultiPoint(points).convex_hull
        area=hull.area if hull.area>0 else hull.buffer(100).area
        values.update(cluster_size=len(points),cluster_density_sites_per_km2=len(points)/(area/1e6),
            dist_to_cluster_centroid_m=origin.distance(MultiPoint(points).centroid))
    values.update(cluster_prelaunch_values(site,cutoff,cache))
    ratios=calculate_user_context(site,cutoff,network,cache=cache)
    values.update({key:ratios[key] for key in USER_CONTEXT_FIELDS})
    road=RoadFeatureExtractor().extract(lat,lon)
    values.update(road)
    values['road_context_signature']='|'.join(map(str,(road['source_hash'],road['buffer_m'],road['method_version'],road['weights_version'])))
    values['virtual_cluster_context']=neighborhood(site,cutoff,cache)
    groups,_=inventory(cache)
    assignment['members']=values['virtual_cluster_context']['vis_members'] if cluster==-1 else [r for r in groups.values() if r['cluster_id']==cluster]
    values['road_context_note']='Current OSM snapshot, not event-time road history.'
    return clean(values),clean(assignment)


def run_similarity(inputs,values,actor=None):
    from services.analysis_profiles import defaults
    from services.models.similarity.hierarchical_filter import HierarchicalFilter
    from services.models.similarity.profile_cache import cached_profile, profile_revision
    from services.models.similarity.case_selector import resolve_template,rank_cases,eligible_events,CaseSelectionError
    from services.models.similarity.kernel_weights import KernelWeights
    cutoff=date.fromisoformat(inputs['event_month'])
    params={'profile_id':inputs['profile_id']} if inputs.get('profile_id') else {}
    settings,profile=resolve_template(actor,params,values)
    settings=settings or defaults()
    values={**values,'_allow_filter_relaxation':settings['allow_filter_relaxation']}
    events=RadioNetworkEvent.objects.filter(is_current=True,event_type=values['event_type'],effective_date__lt=cutoff).select_related('site').order_by('effective_date','event_key')
    events=events.filter(site__cluster_id=-1) if values['tier_scheme']=='extended' else events.exclude(site__cluster_id=-1)
    if inputs.get('site_id'):
        origin=Site.objects.get(site_id=inputs['site_id'])
        events=events.exclude(site__canonical_site_id=origin.canonical_site_id) if origin.canonical_site_id else events.exclude(site=origin)
    raw=list(events.prefetch_related('site__cells','site__network_events'))
    events=eligible_events(raw,cutoff)
    total_events=len(events)
    labels=[{'tier_scheme':'extended' if event.site.cluster_id==-1 else 'standard','event_type':event.event_type,
        'tech_added':'/'.join(sorted(event.details.get('technologies',[]))) if event.event_type=='TECHNOLOGY_ADDED' else None,
        'bands_added':','.join(sorted(event.details.get('bands',[]))) if event.event_type in ('TECHNOLOGY_ADDED','FREQUENCY_BAND_ADDED','SITE_ADDED') else None} for event in events]
    indices=HierarchicalFilter().filter_cases(values,labels)
    events=[events[i] for i in indices];labels=[labels[i] for i in indices]
    cache={};revision=profile_revision();vectors=[]
    for event,label in zip(events,labels):
        vector={**cached_profile(event.site,event.effective_date,cache,revision),**label}
        vectors.append(vector)
    representation=settings['representation']
    try:
        selected=rank_cases(values,vectors,selected_features=None if representation=='pca' else settings['similarity_features'],
            profile_settings=settings,representation=representation,weighting_mode=settings['weighting_mode'],
            minimum_available_weight_share=settings['minimum_available_weight_share'],
            allow_filter_relaxation=settings['allow_filter_relaxation'],limit=max(1,len(vectors)),strict_selection=True)
    except CaseSelectionError as error:
        if representation!='pca': raise
        return clean({'cases':[],'pool_size':len(vectors),'total_event_sites':total_events,'selected_features':settings['similarity_features'],
            'active_features':[],'excluded_features':{},'profile':profile,'representation':'pca','pca':error.payload.get('pca'),
            'filter_explanation':str(error),'note':'PCA could not be fitted to the eligible cases.'})
    features=selected['selected_features'];pca=selected['prepared'];ranking=selected['ranking']
    unique=[];seen=set()
    for item in ranking['cases']:
        event=events[item['candidate_index']]
        physical=event.site.canonical_site_id or event.site.site_id
        if physical in seen: continue
        seen.add(physical);unique.append(item)
        if len(unique)==3: break
    weights=KernelWeights(bandwidth_method='median').compute_weights([item['distance'] for item in unique]) if unique else []
    cases=[]
    for item,weight in zip(unique,weights):
        event=events[item['candidate_index']];candidate=event.site
        cases.append({'site_id':candidate.site_id,'site_name':candidate.site_name,'latitude':candidate.latitude,
            'longitude':candidate.longitude,'event_date':event.effective_date.isoformat(),'event_key':event.event_key,'cluster_id':candidate.cluster_id,
            'similarity':item['similarity'],'distance':item['distance'],'weight':float(weight),
            'used_features':item['used_features'],'feature_weights':item['feature_weights']})
    return clean({'cases':cases,'pool_size':len(vectors),'total_event_sites':total_events,'selected_features':features,
        'active_features':ranking['active_features'],'excluded_features':ranking['excluded_features'],
        'filter_explanation':ranking['filter_explanation'],'reference':ranking.get('reference'),
        'profile':profile,'representation':representation,'pca':pca['report'] if pca else None,
        'note':'Retrieval only; absent candidate performance is not imputed. Historical events must predate the planned month.'})


def create_scenario(data,actor=None):
    inputs=validate(data)
    scenario=CandidateScenario.objects.create(name=inputs['name'],inputs=inputs,status='calculating')
    try:
        features,assignment=calculate_features(inputs)
        scenario.features=features;scenario.result={'assignment':assignment};scenario.status='features_ready'
        scenario.save(update_fields=['features','result','status','updated_at'])
        scenario.result={**scenario.result,'similarity':run_similarity(inputs,features,actor)}
        scenario.status='complete';scenario.save(update_fields=['result','status','updated_at'])
    except Exception as exc:
        scenario.status='failed';scenario.result={**scenario.result,'error':str(exc)}
        scenario.save(update_fields=['result','status','updated_at'])
        raise
    return scenario


def payload(scenario):
    return {'id':str(scenario.pk),'name':scenario.name,'inputs':scenario.inputs,'features':scenario.features,
        'result':scenario.result,'status':scenario.status,'created_at':scenario.created_at.isoformat(),'updated_at':scenario.updated_at.isoformat()}
