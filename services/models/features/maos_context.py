"""MAOS series and pre-event user ratios for site, distance tiers and cluster."""
from collections import defaultdict
from datetime import date
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q, F, Sum, Count, Max, Min

from core.models import Site, MAOSMonthlyKPI, UserContextFeatures
from services.models.preprocessing.maos_aggregation import normalize_monthly_totals, USER_RATIOS, user_ratio_annotations, user_ratio_values
from services.utils.geo_utils import haversine

SCOPES = ('tier1','tier2','cluster')
USER_CONTEXT_FIELDS = tuple(f'{scope}_{metric}' for scope in SCOPES for metric in USER_RATIOS)
USER_CONTEXT_LABELS = {f'{scope}_{metric}': (f'{label} - {name}', 'ratio')
    for scope,label in [('tier1','Tier 1 (origin scheme)'),('tier2','Tier 2 (origin scheme)'),('cluster','Total cluster')]
    for metric,name in [('edge_user_share','Edge user share'),('edge_user_peak_ratio','Edge user peak ratio'),('lowlatency_user_share','Low-latency user share')]}


def monthly_annotations():
    throughput = Q(thrp_time_dl_ms__isnull=False,thrp_bits_dl_last_tti__isnull=False,thrp_bits_dl__gte=F('thrp_bits_dl_last_tti'))
    prb = Q(prb_dl_used_avg__isnull=False,prb_dl_available__gt=0)
    delay = Q(dl_packet_delay_time_ms__isnull=False,dl_packet_delay_packets__gt=0)
    availability = Q(cell_unavail_duration_s__isnull=False,observation_duration_s__gt=0)
    cqi = Q(cqi_weighted_sum__isnull=False,cqi_sample_count__gt=0)
    return {
        'traffic_users':Sum('traffic_user_avg'),'active_users':Sum('active_users_avg'),'traffic_bits':Sum('thrp_bits_dl'),
        'dl_bits':Sum('thrp_bits_dl',filter=throughput),'dl_last_tti_bits':Sum('thrp_bits_dl_last_tti',filter=throughput),'dl_time_ms':Sum('thrp_time_dl_ms',filter=throughput),
        'prb_used':Sum('prb_dl_used_avg',filter=prb),'prb_available':Sum('prb_dl_available',filter=prb),
        'delay_time_ms':Sum('dl_packet_delay_time_ms',filter=delay),'delay_packets':Sum('dl_packet_delay_packets',filter=delay),
        'unavailable_s':Sum('cell_unavail_duration_s',filter=availability),'observation_s':Sum('observation_duration_s',filter=availability),
        'cqi_weighted_total':Sum('cqi_weighted_sum',filter=cqi),'cqi_sample_count':Sum('cqi_sample_count',filter=cqi),
        'reporting_cells':Count('cell_id',distinct=True),'reporting_sites':Count('cell__site_id',distinct=True),
        **user_ratio_annotations(),
    }


def monthly_series(site_ids):
    rows = MAOSMonthlyKPI.objects.filter(cell__site__site_id__in=site_ids).values('month_date').annotate(**monthly_annotations()).order_by('month_date')
    return [{'month':row['month_date'].strftime('%Y-%m'),**normalize_monthly_totals(row),
             'reporting_sites':row['reporting_sites'],
             'user_ratio_support':ratio_support(row)} for row in rows]


def ratio_support(totals):
    support = {}
    for metric in USER_RATIOS:
        numerator,denominator = totals.get(metric+'_num'),totals.get(metric+'_den')
        reason = 'no_paired_counters' if numerator is None or denominator is None else 'zero_denominator' if denominator == 0 else None
        support[metric] = {'numerator_sum':numerator,'denominator_sum':denominator,
                           'paired_cell_months':totals.get(metric+'_rows',0),'unavailable_reason':reason}
    return support


def scope_members(site, network=None, cutoff=None, cache=None):
    from .neighborhood import neighborhood, raw_ids, inventory
    context = neighborhood(site, cutoff=cutoff, cache=cache)
    result = {'site':[site.site_id], **{key:raw_ids(members) for key,members in context['scopes'].items()}}
    if site.cluster_id != -1:
        groups,_ = inventory(cache if cache is not None else {})
        result['cluster'] = [key for group in groups.values() if group['cluster_id']==site.cluster_id for key in group['site_ids']]
    return result


def default_profile_cutoff(site, latest_month=None):
    from services.models.similarity.historical import month_offset
    from services.models.preprocessing.network_events import effective_event_date
    event = effective_event_date(site)
    latest = latest_month or MAOSMonthlyKPI.objects.aggregate(value=Max('month_date'))['value']
    return (event or (month_offset(latest,1) if latest else date.today())).replace(day=1)


def calculate_user_context(site, cutoff, network=None, totals_by_site=None, cache=None):
    from services.models.similarity.historical import load_network, month_offset
    network = load_network(cutoff) if network is None else network
    members = scope_members(site,network,cutoff,cache)
    values, support = {}, {}
    for scope in SCOPES:
        if totals_by_site is None:
            totals = MAOSMonthlyKPI.objects.filter(cell__site__site_id__in=members[scope],
                month_date__gte=month_offset(cutoff,-3),month_date__lt=cutoff).aggregate(**user_ratio_annotations())
        else:
            records = [totals_by_site.get(site_id,{}).get(month_offset(cutoff,offset),{})
                       for site_id in members[scope] for offset in (-3,-2,-1)]
            totals = {}
            for name in user_ratio_annotations():
                observed = [row[name] for row in records if row.get(name) is not None]
                totals[name] = sum(observed) if observed else None
        values.update({f'{scope}_{key}':value for key,value in user_ratio_values(totals).items()})
        support[scope] = {'site_count':len(members[scope]),'ratios':ratio_support(totals)}
    return {**values,'profile_as_of_date':cutoff,'support':{**support,'neighborhood_version':'neighborhood-v1'}}


def user_context_values(site, cutoff, network=None, cache=None):
    try:
        stored = site.user_context_features
    except ObjectDoesNotExist:
        stored = None
    if stored is not None and stored.profile_as_of_date == cutoff and stored.support.get('neighborhood_version')=='neighborhood-v1':
        return {**{name:getattr(stored,name) for name in USER_CONTEXT_FIELDS},
                'user_context_support':stored.support}
    values = calculate_user_context(site,cutoff,network,cache=cache)
    return {**{name:values[name] for name in USER_CONTEXT_FIELDS},'user_context_support':values['support']}


def save_user_context(site, network_cache=None):
    from services.models.similarity.historical import load_network
    cutoff = default_profile_cutoff(site)
    cache = network_cache if network_cache is not None else {}
    if cutoff not in cache:
        cache[cutoff] = load_network(cutoff)
    values = calculate_user_context(site,cutoff,cache[cutoff],cache=cache)
    UserContextFeatures.objects.update_or_create(site=site,defaults=values)
    return values


def backfill_user_context(progress_callback=None):
    from services.models.similarity.historical import load_network
    rows = MAOSMonthlyKPI.objects.values('cell__site__site_id','month_date').annotate(**user_ratio_annotations())
    totals = defaultdict(dict)
    for row in rows.iterator(chunk_size=10000):
        totals[row['cell__site__site_id']][row['month_date']] = row
    latest = MAOSMonthlyKPI.objects.aggregate(value=Max('month_date'))['value']
    sites = list(Site.objects.all().prefetch_related('cells'))
    network_cache, pending = {}, []
    report = {'total':len(sites),'computed':0,'all_unavailable':0,'errors':0,'available_by_feature':dict.fromkeys(USER_CONTEXT_FIELDS,0),
              'unavailable_reasons':{}}
    for index,site in enumerate(sites,1):
        cutoff = default_profile_cutoff(site,latest)
        if cutoff not in network_cache:
            network_cache[cutoff] = load_network(cutoff)
        values = calculate_user_context(site,cutoff,network_cache[cutoff],totals,cache=network_cache)
        available = [name for name in USER_CONTEXT_FIELDS if values[name] is not None]
        report['computed' if available else 'all_unavailable'] += 1
        for name in available:
            report['available_by_feature'][name] += 1
        for scope in SCOPES:
            for metric,data in values['support'][scope]['ratios'].items():
                reason = data['unavailable_reason']
                if reason:
                    report['unavailable_reasons'][reason] = report['unavailable_reasons'].get(reason,0)+1
        pending.append(UserContextFeatures(site=site,**values))
        if progress_callback and (index==1 or index%100==0 or index==len(sites)):
            progress_callback({'stage':'user_context','processed':index,'total':len(sites)})
    UserContextFeatures.objects.bulk_create(pending,update_conflicts=True,unique_fields=['site'],
        update_fields=[*USER_CONTEXT_FIELDS,'profile_as_of_date','support','updated_at'],batch_size=200)
    return report


def site_maos_payload(site, added_cells=()):
    if hasattr(site,'_maos_context_payload'):
        return site._maos_context_payload
    from .neighborhood import neighborhood, raw_ids, current_snapshot, offset, sample_series
    latest = MAOSMonthlyKPI.objects.aggregate(value=Max('month_date'))['value']
    cutoff = offset(latest,1) if latest else date.today().replace(day=1)
    context = neighborhood(site,cutoff,{})
    members = scope_members(site,cutoff=cutoff)
    scopes = {key:{'site_count':len(context['scopes'].get(key,[])) if key!='site' else 1,
        'label':context['labels'].get(key,key), 'records':monthly_series(ids),
        'tier_scheme':context['tier_scheme'], 'membership_kind':'current', 'membership_cutoff':cutoff.isoformat()}
        for key,ids in members.items()}
    if site.cluster_id!=-1:
        scopes['cluster']['site_count'] += 1
    scopes['virtual_cluster']['records'] = sample_series(context['vis_members'])
    scopes['virtual_cluster']['note'] = 'Traffic sample only, at most one location per 30-degree bin; current membership.'

    added = {item['cell_name']:item for item in added_cells}
    fields = ('traffic_user_avg','active_users_avg','prb_util_dl_pct','prb_util_ul_pct','rrc_conn_avg','cqi_avg',
              'rsrp_avg_dbm','thrp_bits_dl','dl_throughput_kbps','dl_packet_delay_ms','cell_availability_pct',
              'border_user_avg','border_user_max','lowlatency_user_avg')
    cells = {}
    rows = MAOSMonthlyKPI.objects.filter(cell__site=site).values('cell__cell_name','cell__technology','month_date',*fields).order_by('cell__cell_name','month_date')
    for row in rows.iterator(chunk_size=2000):
        name = row['cell__cell_name']
        entry = cells.setdefault(name,{'cell_name':name,'technology':row['cell__technology'],
            'is_added':name in added,'launch_date':added.get(name,{}).get('launch_date'),'records':[]})
        paired = {}
        for metric,(num,den) in USER_RATIOS.items():
            a,b = row[num],row[den]
            if a is not None and b is not None and a >= 0 and b >= 0:
                paired.update({metric+'_num':a,metric+'_den':b})
        entry['records'].append({'month':row['month_date'].strftime('%Y-%m'),**{name:row[name] for name in fields},
            'thrp_dl_gb':row['thrp_bits_dl']/8e9 if row['thrp_bits_dl'] is not None else None,
            'thrp_ul_gb':None,**user_ratio_values(paired)})
    site._maos_context_payload = {'scopes':scopes,'cells':list(cells.values())}
    return site._maos_context_payload


def cluster_monthly_series(cluster_id):
    ids = Site.objects.filter(cluster_id=cluster_id).values_list('site_id',flat=True)
    result = []
    for row in monthly_series(ids):
        result.append({**row,'month':row['month']+'-01','downlink_traffic_gb':row['thrp_dl_gb'],
            'active_users_sum':row['active_users_avg'],'traffic_users_sum':row['traffic_user_avg'],
            'downlink_prb_avg_pct':row['prb_util_dl_pct']})
    return result


def feature_availability_audit():
    from core.models import ConfigurationFeatures, GeometricFeatures, ClutterFeatures, SpatialFeatures, ANPFeatures, ClusterFeatures, RoadFeatures, KPIFeatures, PreLaunchKPI
    models=(ConfigurationFeatures,GeometricFeatures,ClutterFeatures,SpatialFeatures,ANPFeatures,ClusterFeatures,RoadFeatures,UserContextFeatures,KPIFeatures,PreLaunchKPI)
    counts={model.__name__:model.objects.count() for model in models}
    source=MAOSMonthlyKPI.objects.aggregate(rows=Count('pk'),border_average_present=Count('border_user_avg'),
        border_maximum_present=Count('border_user_max'),lowlatency_average_present=Count('lowlatency_user_avg'))
    report={'stored_groups':counts,'source_rows':source,
        'remaining_unavailable_explanations':[
            'User ratios require paired source rows and a positive summed denominator; no eligible cohort or zero denominator stays NULL.',
            'Own-site charts can be empty for 2G/3G-only sites because the imported report is LTE-only; tier/cluster charts use linked neighboring LTE sites.',
            'Historical configuration, clutter/building snapshots, undated legacy KPIs and future road/population epochs are deliberately excluded from historical vectors.',
            'Equivalent RSRP, average RRC, busy-hour load and congestion duration are unsupported by the selected report; recalculation cannot invent these measurements.',
        ]}
    return report
