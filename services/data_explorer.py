"""Read-only, paginated exploration of raw counters, pooled KPIs and event profiles."""
from datetime import date
import math

from django.db.models import Q, F, Value, Case, When, FloatField, CharField, ExpressionWrapper, Min, Max
from django.db.models.functions import NullIf
from core.models import Site, MAOSMonthlyKPI
from services.models.features.maos_context import monthly_annotations, scope_members
from services.models.preprocessing.maos_aggregation import normalize_monthly_totals
from services.models.features.maos_context import USER_CONTEXT_LABELS
from services.models.features.road_loader import ROAD_LABELS
from services.models.similarity.catalog import SIMILARITY_FIELDS, CONTEXT_LABELS, POPULATION_LABELS
from services.models.similarity.gower_distance import GowerDistance
from services.models.similarity.feature_vector import build_site_similarity_vector
from services.models.preprocessing.network_events import effective_event_date

RAW = {
    'thrp_bits_dl': ('DL traffic', 'bits'), 'traffic_user_avg': ('Traffic users', 'users'),
    'active_users_avg': ('Active users', 'users'), 'border_user_avg': ('Border users average', 'users'),
    'border_user_max': ('Border users maximum', 'users'), 'lowlatency_user_avg': ('Low-latency users', 'users'),
    'prb_dl_used_avg': ('DL PRBs used', 'PRBs'), 'prb_dl_available': ('DL PRBs available', 'PRBs'),
    'thrp_time_dl_ms': ('DL throughput time', 'ms'), 'thrp_bits_dl_last_tti': ('DL last-TTI traffic', 'bits'),
    'dl_packet_delay_time_ms': ('DL delay time', 'ms'), 'dl_packet_delay_packets': ('DL delay packet count', 'packets'),
    'cell_unavail_duration_s': ('Cell unavailable duration', 's'), 'observation_duration_s': ('Observed duration', 's'),
    'cqi_weighted_sum': ('CQI weighted total', 'CQI × samples'), 'cqi_sample_count': ('CQI sample count', 'samples'),
}
RAW_SOURCES = {
    'thrp_bits_dl': 'L.Thrp.bits.DL(bit)', 'traffic_user_avg': 'L.Traffic.User.Avg',
    'active_users_avg': 'L.Traffic.ActiveUser.Avg', 'border_user_avg': 'L.Traffic.User.BorderUE.Avg',
    'border_user_max': 'L.Traffic.User.BorderUE.Max', 'lowlatency_user_avg': 'L.Traffic.User.LowLatency.Avg',
    'prb_dl_used_avg': 'L.ChMeas.PRB.DL.Used.Avg', 'prb_dl_available': 'L.ChMeas.PRB.DL.Avail',
    'thrp_time_dl_ms': 'L.Thrp.Time.DL.RmvLastTTI(ms)', 'thrp_bits_dl_last_tti': 'L.Thrp.bits.DL.LastTTI(bit)',
    'dl_packet_delay_time_ms': 'L.Traffic.DL.PktDelay.Time(ms)', 'dl_packet_delay_packets': 'L.Traffic.DL.PktDelay.Num(packet)',
    'cell_unavail_duration_s': 'L.Cell.Unavail.Dur.Sys(s)',
    'observation_duration_s': 'Calendar-month observation assumption',
    'cqi_weighted_sum': 'L.ChMeas.CQI.DL.0 … 15 (retained histogram statistic)',
    'cqi_sample_count': 'L.ChMeas.CQI.DL.0 … 15 (retained histogram statistic)',
}
RAW_DERIVATIONS = {
    'observation_duration_s': 'Days in report month × 86400, only when unavailability is reported; not independently measured exposure.',
    'cqi_weighted_sum': 'SUM(bin index × reported bin count), retained during import; individual bins are not stored here.',
    'cqi_sample_count': 'SUM(reported CQI bin counts), retained during import; partial histogram coverage is not recorded.',
}
CALCULATED = {
    'thrp_dl_gb': ('DL traffic', 'GB/month', 'SUM(DL bits) / 8e9'),
    'active_users_avg': ('Active users (sum)', 'users', 'SUM(cell active-user averages)'),
    'traffic_user_avg': ('Traffic users (sum)', 'users', 'SUM(cell traffic-user averages)'),
    'prb_util_dl_pct': ('DL PRB utilization', '%', '100 × SUM(used PRBs) / SUM(available PRBs), paired valid rows'),
    'cqi_avg': ('Weighted CQI', '', 'SUM(weighted CQI) / SUM(CQI samples), paired valid rows'),
    'dl_throughput_kbps': ('DL throughput', 'kbit/s', 'SUM(bits − last-TTI bits) / SUM(time ms), paired valid rows'),
    'dl_packet_delay_ms': ('DL packet delay', 'ms', 'SUM(delay time) / SUM(packet count), paired valid rows'),
    'cell_availability_pct': ('Cell availability', '%', '100 × (1 − SUM(unavailable seconds) / SUM(observed seconds))'),
    'edge_user_share': ('Edge user share', 'ratio', 'SUM(BorderUE.Avg) / SUM(Traffic.User.Avg), paired rows'),
    'edge_user_peak_ratio': ('Edge user peak ratio', 'ratio', 'SUM(BorderUE.Max) / SUM(BorderUE.Avg), paired rows'),
    'lowlatency_user_share': ('Low-latency user share', 'ratio', 'SUM(LowLatency.Avg) / SUM(Traffic.User.Avg), paired rows'),
}


def profile_metadata():
    labels = {**POPULATION_LABELS, **ROAD_LABELS, **USER_CONTEXT_LABELS, **CONTEXT_LABELS}
    return [{'key': f, 'label': labels.get(f, (f.replace('_', ' '), ''))[0],
             'unit': labels.get(f, ('', ''))[1], 'group': GowerDistance()._get_feature_group(f),
             'type': 'numeric' if f in GowerDistance.NUMERIC_FEATURES else 'categorical',
             'source': 'Land-cover class prior; no measured building-height source' if f == 'avg_building_height_m' else 'Event-safe similarity profile; see feature_eng.md',
             'formula': ('Lookup: urban 18 m, suburban 8 m, rural 4 m, forest/water 0 m convention. Not an average of building measurements.'
                         if f == 'avg_building_height_m' else 'Same service and timing policy as Similarity; not an undated stored feature row.')}
            for f in SIMILARITY_FIELDS]


def metadata():
    bounds = MAOSMonthlyKPI.objects.aggregate(first=Min('month_date'), last=Max('month_date'))
    return {'datasets': {
        'raw': [{'key': f, 'label': label, 'unit': unit, 'type': 'numeric', 'source': RAW_SOURCES[f],
                 'formula': RAW_DERIVATIONS.get(f, 'Imported cell-month counter; no cross-cell aggregation.')} for f, (label, unit) in RAW.items()],
        'calculated': [{'key': f, 'label': label, 'unit': unit, 'type': 'numeric', 'source': 'MAOS paired raw components',
                        'formula': formula} for f, (label, unit, formula) in CALCULATED.items()],
        'features': profile_metadata()}, 'month_bounds': bounds,
        'clusters': list(Site.objects.values_list('cluster_id', flat=True).distinct().order_by('cluster_id')),
        'technologies': ['2G', '3G', '4G'],
        'note': 'NULL means unavailable; zero is an observed value. Raw records are imported monthly counters, not instantaneous samples. Noise sites remain separate in cluster rollups.'}


def month(value):
    if not value:
        return None
    try:
        parsed = date.fromisoformat(value + '-01' if len(value) == 7 else value)
        if parsed.day != 1:
            raise ValueError()
        return parsed
    except (ValueError, TypeError):
        raise ValueError('Dates must be calendar months (YYYY-MM).')


def positive_int(value, label, maximum):
    try:
        result = int(value)
        if result < 1 or result > maximum:
            raise ValueError()
        return result
    except (ValueError, TypeError):
        raise ValueError(f'{label} must be an integer from 1 to {maximum}.')


def filter_sites(params):
    sites = Site.objects.all()
    search = params.get('search', '').strip()
    if search:
        sites = sites.filter(Q(site_id__icontains=search) | Q(site_name__icontains=search)
            | Q(cells__cell_name__icontains=search) | Q(cells__cell_id__icontains=search)).distinct()
    if params.get('site_id'):
        sites = sites.filter(site_id=params['site_id'])
    if params.get('cluster_id') not in (None, ''):
        try:
            cluster = int(params['cluster_id'])
        except ValueError:
            raise ValueError('cluster_id must be an integer (noise is -1).')
        sites = sites.filter(cluster_id=cluster)
    technology = params.get('technology', '')
    if params.get('tier_scheme'):
        if params['tier_scheme'] not in ('standard','extended'):
            raise ValueError('tier_scheme must be standard or extended.')
        sites=sites.filter(tier_scheme=params['tier_scheme'])
    if technology:
        if technology not in ('2G', '3G', '4G'):
            raise ValueError('technology must be 2G, 3G or 4G.')
        sites = sites.filter(cells__technology=technology).distinct()
    return sites


def metric_expressions():
    def ratio(numerator, denominator):
        return ExpressionWrapper(1.0 * numerator / NullIf(denominator, Value(0.)), output_field=FloatField())
    expressions = {
        'thrp_dl_gb': F('traffic_bits') / 8e9, 'active_users_avg': F('active_users'), 'traffic_user_avg': F('traffic_users'),
        'prb_util_dl_pct': 100 * ratio(F('prb_used'), F('prb_available')),
        'cqi_avg': ratio(F('cqi_weighted_total'), F('cqi_sample_count')),
        'dl_throughput_kbps': ratio(F('dl_bits') - F('dl_last_tti_bits'), F('dl_time_ms')),
        'dl_packet_delay_ms': ratio(F('delay_time_ms'), F('delay_packets')),
        'cell_availability_pct': 100 * (1 - ratio(F('unavailable_s'), F('observation_s'))),
    }
    for key in ('edge_user_share', 'edge_user_peak_ratio', 'lowlatency_user_share'):
        expressions[key] = ratio(F(key + '_num'), F(key + '_den'))
    return {'metric_' + key: ExpressionWrapper(value, output_field=FloatField()) for key, value in expressions.items()}


def value_filter(params, fields):
    key = params.get('value_field', '')
    op = params.get('value_op', 'gte')
    if not key:
        return None
    if key not in fields:
        raise ValueError('Unknown value-filter field.')
    if op not in ('gte', 'lte', 'eq', 'missing', 'present'):
        raise ValueError('Unknown value-filter operator.')
    value = params.get('value', '')
    numeric = key in GowerDistance.NUMERIC_FEATURES if params.get('dataset') == 'features' else True
    if op not in ('missing', 'present') and numeric:
        try:
            value = float(value)
            if not math.isfinite(value):
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError('The numeric filter needs a finite value.')
    elif not numeric and op not in ('eq', 'missing', 'present'):
        raise ValueError('Categorical fields support equals, missing or present.')
    return key, op, value


def apply_sql_filter(queryset, rule, prefix=''):
    if not rule:
        return queryset
    key, op, value = rule
    if op in ('missing', 'present'):
        return queryset.filter(**{prefix + key + '__isnull': op == 'missing'})
    return queryset.filter(**{prefix + key + ('__exact' if op == 'eq' else '__' + op): value})


def explore(params):
    try:
        return _explore(params), 200
    except ValueError as error:
        return {'error': str(error)}, 400


def _explore(params):
    dataset = params.get('dataset', 'raw')
    fields = RAW if dataset == 'raw' else CALCULATED if dataset == 'calculated' else SIMILARITY_FIELDS if dataset == 'features' else None
    if fields is None:
        raise ValueError('dataset must be raw, calculated or features.')
    selected = list(dict.fromkeys(params.get('columns', ','.join(list(fields)[:6])).split(',')))
    if not selected or any(f not in fields for f in selected):
        raise ValueError('Select known columns from the selected dataset.')
    page = positive_int(params.get('page', 1), 'page', 1000000)
    size = positive_int(params.get('page_size', 50), 'page_size', 200)
    start, end = (page - 1) * size, page * size
    lower, upper = month(params.get('month_from')), month(params.get('month_to'))
    if lower and upper and lower > upper:
        raise ValueError('The first month must not follow the last month.')
    rule = value_filter(params, fields)
    sites = filter_sites(params)
    if dataset == 'features':
        return explore_features(params, sites, selected, rule, page, size)
    queryset = MAOSMonthlyKPI.objects.filter(cell__site__in=sites)
    if params.get('search', '').strip():
        search = params['search'].strip()
        queryset = queryset.filter(Q(cell__site__site_id__icontains=search) | Q(cell__site__site_name__icontains=search)
            | Q(cell__cell_name__icontains=search) | Q(cell__cell_id__icontains=search))
    if params.get('technology'):
        queryset = queryset.filter(cell__technology=params['technology'])
    if params.get('cell'):
        queryset = queryset.filter(Q(cell__cell_id__icontains=params['cell']) | Q(cell__cell_name__icontains=params['cell']))
    if lower:
        queryset = queryset.filter(month_date__gte=lower)
    if upper:
        queryset = queryset.filter(month_date__lte=upper)
    scope = params.get('scope', 'site')
    if dataset == 'raw':
        queryset = apply_sql_filter(queryset, rule)
        count = queryset.count()
        rows = []
        for row in queryset.order_by('month_date', 'cell_id').values('month_date', 'cell__site__site_id', 'cell__site__site_name',
                'cell__site__cluster_id', 'cell__cell_id', 'cell__cell_name', 'cell__technology', *selected)[start:end]:
            rows.append({'month': row['month_date'], 'site_id': row['cell__site__site_id'], 'site_name': row['cell__site__site_name'],
                         'cluster_id': row['cell__site__cluster_id'], 'cell': row['cell__cell_name'], 'cell_id': row['cell__cell_id'],
                         'technology': row['cell__technology'], **{f: row[f] for f in selected}})
        scope = 'cell'
    else:
        if scope not in ('cell', 'site', 'cluster', 'tier1', 'tier2','virtual_cluster','distance_0_2','distance_2_5','distance_5_10'):
            raise ValueError('Unknown calculated KPI scope.')
        grouping = ['month_date']
        if scope in ('tier1', 'tier2','virtual_cluster','distance_0_2','distance_2_5','distance_5_10'):
            origin = Site.objects.filter(site_id=params.get('origin_site_id', '')).first()
            if origin is None:
                raise ValueError('Tier scopes require an existing origin_site_id.')
            if scope=='virtual_cluster' and selected!=['thrp_dl_gb']:
                raise ValueError('Virtual samples are traffic-only: select thrp_dl_gb.')
            from services.models.features.neighborhood import offset
            latest=MAOSMonthlyKPI.objects.aggregate(value=Max('month_date'))['value']
            cutoff=offset(latest,1) if latest else date.today().replace(day=1)
            queryset = queryset.filter(cell__site__site_id__in=scope_members(origin,cutoff=cutoff)[scope])
        elif scope == 'cluster':
            queryset=queryset.exclude(cell__site__cluster_id=-1)
            queryset = queryset.annotate(noise_site=Case(When(cell__site__cluster_id=-1, then=F('cell__site__site_id')), default=Value(''), output_field=CharField()))
            grouping += ['cell__site__cluster_id', 'noise_site']
        else:
            grouping += ['cell__site__site_id', 'cell__site__site_name', 'cell__site__cluster_id']
            if scope == 'cell':
                grouping += ['cell__cell_name', 'cell__cell_id', 'cell__technology']
        queryset = queryset.values(*grouping).annotate(**monthly_annotations()).annotate(**metric_expressions())
        queryset = apply_sql_filter(queryset, rule, prefix='metric_')
        count = queryset.count()
        rows = []
        for row in queryset.order_by(*grouping)[start:end]:
            values = normalize_monthly_totals(row)
            rows.append({'month': row['month_date'], 'site_id': row.get('cell__site__site_id') or row.get('noise_site'),
                'site_name': row.get('cell__site__site_name'), 'cluster_id': row.get('cell__site__cluster_id'),
                'cell': row.get('cell__cell_name'), 'technology': row.get('cell__technology'),
                'reporting_cells': row['reporting_cells'], 'reporting_sites': row['reporting_sites'], **{f: values[f] for f in selected}})
    return {'dataset': dataset, 'scope': scope, 'count': count, 'page': page, 'page_size': size, 'columns': selected, 'rows': rows,
            'note': 'Filters apply before aggregation. Ratios pool paired raw counters. Month range is inclusive. Radius scopes use current membership and tier scheme of the origin. Virtual traffic is a one-per-bin sample, not the complete total. Cluster excludes noise. NULL is not zero.'}


def explore_features(params, sites, selected, rule, page, size):
    cutoff = month(params.get('as_of'))
    if params.get('cell'):
        sites = sites.filter(cells__cell_name__icontains=params['cell']).distinct()
    # Profiles have an event cutoff, not a monthly measurement series.
    if params.get('month_from') or params.get('month_to'):
        raise ValueError('Use as_of for feature profiles; month ranges apply to monthly KPI datasets.')
    sites = sites.select_related('config_features', 'geometric_features', 'clutter_features', 'spatial_features',
        'anp_features', 'cluster_features', 'prelaunch_kpi', 'road_features', 'user_context_features').prefetch_related('cells', 'network_events').order_by('site_id')
    start, end = (page - 1) * size, page * size
    count = sites.count()
    candidates = sites if rule else sites[start:end]
    rows, cache = [], {}
    matched = 0
    for site in candidates.iterator(chunk_size=100):
        vector = build_site_similarity_vector(site, as_of_date=cutoff, snapshot_cache=cache, allow_current_roads=True)
        if rule:
            key, op, value = rule
            observed = vector.get(key)
            missing = GowerDistance._is_missing(observed)
            if op == 'missing':
                keep = missing
            elif op == 'present':
                keep = not missing
            elif missing:
                keep = False
            elif op == 'eq':
                keep = observed == value or str(observed).lower() == str(value).lower()
            else:
                keep = observed >= value if op == 'gte' else observed <= value
            if not keep:
                continue
            matched += 1
            if not start < matched <= end:
                continue
        rows.append({'site_id': site.site_id, 'site_name': site.site_name, 'cluster_id': site.cluster_id,
            'tier_scheme':vector.get('tier_scheme'),
            'as_of': vector['feature_as_of_date'], 'event_date': effective_event_date(site),
            **{f: None if GowerDistance._is_missing(vector.get(f)) else vector.get(f) for f in selected}})
    return {'dataset': 'features', 'scope': 'site', 'count': matched if rule else count, 'page': page, 'page_size': size,
            'columns': selected, 'rows': rows,
            'note': 'Full-site profiles; technology/cell filters select sites, not a partial-site feature recalculation. Default cutoff is each site event (or latest own history). Static geography/population policy applies. Value filtering scans matching profiles.'}
