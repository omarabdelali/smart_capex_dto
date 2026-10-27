"""Case-based event impact forecasts from historical site launches."""
from collections import defaultdict
from datetime import date
from statistics import median

import numpy as np
from django.db.models import Max, Min

from core.models import Cell, MAOSMonthlyKPI, Site
from services.models.preprocessing.maos_aggregation import normalize_monthly_totals
from services.models.similarity import build_site_similarity_vector, rank_similar_cases
from services.models.similarity.gower_distance import GowerDistance
from services.models.similarity.historical import cluster_members
from services.models.features.road_loader import ROAD_FIELDS
from services.models.features.maos_context import monthly_annotations
from services.utils.geo_utils import haversine
from services.models.preprocessing.network_events import event_rules


METRICS = {
    'downlink_traffic_gb': {
        'label': 'Downlink traffic', 'unit': 'GB/month', 'kind': 'sum', 'available': True,
    },
    'rsrp_dbm': {
        'label': 'RSRP', 'unit': 'dBm', 'kind': 'mean', 'available': False,
        'reason': 'The imported LTE report does not contain a supported RSRP measurement.',
    },
    'cqi_avg': {'label': 'CQI', 'unit': '', 'kind': 'mean', 'available': True},
    'rrc_users': {
        'label': 'RRC users', 'unit': 'users', 'kind': 'sum', 'available': False,
        'reason': 'The imported LTE report does not contain an average RRC user counter.',
    },
    'active_users': {'label': 'Active users', 'unit': 'users', 'kind': 'sum', 'available': True},
    'dl_throughput_kbps': {
        'label': 'DL user throughput', 'unit': 'kbit/s', 'kind': 'mean', 'available': True,
    },
    'dl_packet_delay_ms': {'label': 'Latency', 'unit': 'ms', 'kind': 'mean', 'available': True},
}

RAW_FIELDS = (
    'traffic_bits', 'dl_bits', 'dl_last_tti_bits', 'dl_time_ms', 'prb_used',
    'prb_available', 'delay_time_ms', 'delay_packets', 'unavailable_s',
    'observation_s', 'cqi_weighted_total', 'cqi_sample_count', 'active_users',
    'traffic_users', 'reporting_cells',
)
OUTPUT_FIELDS = {
    'downlink_traffic_gb': 'thrp_dl_gb',
    'cqi_avg': 'cqi_avg',
    'active_users': 'active_users_avg',
    'dl_throughput_kbps': 'dl_throughput_kbps',
    'dl_packet_delay_ms': 'dl_packet_delay_ms',
}
OFFSETS = tuple(range(-3, 7))
PREDICT_OFFSETS = tuple(range(event_rules()['effect_start_offset'], 7))


def _next_month(value):
    year, month = (value.year + 1, 1) if value.month == 12 else (value.year, value.month + 1)
    return date(year, month, 1)


def _month_at_offset(event_date, offset):
    month_index = event_date.year * 12 + event_date.month - 1 + offset
    year, month_zero = divmod(month_index, 12)
    return date(year, month_zero + 1, 1)


def _row_value(row, key):
    if row is None:
        return None
    if key in ('rrc_users', 'rsrp_dbm'):
        return None
    return normalize_monthly_totals(row).get(OUTPUT_FIELDS[key])


def _month_rows():
    from services.models.features.neighborhood import inventory
    _,by_raw = inventory({})
    queryset = MAOSMonthlyKPI.objects.values('cell__site__site_id','month_date').annotate(**monthly_annotations())
    grouped = defaultdict(lambda: defaultdict(list))
    for row in queryset.iterator(chunk_size=10000):
        key=by_raw.get(row['cell__site__site_id'],row['cell__site__site_id'])
        grouped[key][row['month_date']].append(row)
    return {key:{month:_merge_raw_rows(rows) for month,rows in months.items()} for key,months in grouped.items()}


def _merge_raw_rows(rows):
    merged = {}
    for field in RAW_FIELDS:
        values = [row[field] for row in rows if row and row.get(field) is not None]
        merged[field] = sum(values) if values else None
    return merged


def _aggregate_metric(site_ids, month, by_site, metric):
    merged = _merge_raw_rows([by_site.get(site_id, {}).get(month) for site_id in site_ids])
    return _row_value(merged, metric)


def _baseline(site_id, event_date, by_site, metric):
    values = [
        _row_value(by_site.get(site_id, {}).get(_month_at_offset(event_date, offset)), metric)
        for offset in (-3, -2, -1)
    ]
    values = [value for value in values if value is not None and np.isfinite(value)]
    return median(values) if values else None


def _site_is_active(site_id, event_date, by_site):
    for offset in (-3, -2, -1):
        row = by_site.get(site_id, {}).get(_month_at_offset(event_date, offset))
        if not row:
            continue
        normalized = normalize_monthly_totals(row)
        if any(
            normalized.get(key) not in (None, 0)
            for key in ('thrp_dl_gb', 'active_users_avg', 'traffic_user_avg', 'cqi_avg', 'dl_throughput_kbps', 'dl_packet_delay_ms')
        ):
            return True
    return False


def _available_site_ids(site_ids, event_date, by_site):
    return [site_id for site_id in site_ids if _site_is_active(site_id, event_date, by_site)]


def _event_group_responses(site_ids, event_date, by_site, available_before=None):
    """Average per-recipient KPI changes for a historic event cohort."""
    active = _available_site_ids(site_ids, event_date, by_site)
    responses = {metric: {} for metric in METRICS}
    counts = {}
    for metric, definition in METRICS.items():
        if not definition['available']:
            continue
        baselines = {site_id: _baseline(site_id, event_date, by_site, metric) for site_id in active}
        eligible = [site_id for site_id, value in baselines.items() if value is not None]
        counts[metric] = len(eligible)
        for offset in PREDICT_OFFSETS:
            deltas = []
            month = _month_at_offset(event_date, offset)
            if available_before is not None and month >= available_before.replace(day=1):
                continue
            for site_id in eligible:
                value = _row_value(by_site.get(site_id, {}).get(month), metric)
                if value is not None and np.isfinite(value):
                    deltas.append(value - baselines[site_id])
            if deltas:
                responses[metric][offset] = float(sum(deltas) / len(deltas))
    return responses, counts


def _weighted_bootstrap(values, weights, seed):
    if not values:
        return None, None, None
    values_array = np.asarray(values, dtype=float)
    normalized = np.asarray(weights, dtype=float)
    normalized = normalized / normalized.sum()
    estimate = float(np.dot(values_array, normalized))
    rng = np.random.default_rng(seed)
    draws = np.asarray([
        float(np.mean(rng.choice(values_array, size=len(values), replace=True, p=normalized)))
        for _ in range(500)
    ])
    low, high = np.percentile(draws, [2.5, 97.5])
    return estimate, float(low), float(high)


def _predict_delta(ranked_cases, outcomes_by_site, scope, metric, offset):
    if offset not in PREDICT_OFFSETS:
        return None, None, None, 0
    values, weights = [], []
    for case in ranked_cases:
        site_id = case['features'].get('site_id')
        value = outcomes_by_site.get(site_id, {}).get(scope, {}).get(metric, {}).get(offset)
        if value is not None:
            values.append(value)
            weights.append(case['weight'])
    if len(values) < 2:
        return None, None, None, len(values)
    estimate, low, high = _weighted_bootstrap(values, weights, seed=offset + len(values))
    return estimate, low, high, len(values)


def _scope_members(origin, all_sites, by_site, event_date, cache=None):
    from services.models.features.neighborhood import neighborhood
    context=neighborhood(origin,event_date,cache)
    scopes={key:[r['site_id'] for r in members] for key,members in context['scopes'].items()}
    distances={r['site_id']:r['distance_m'] for members in context['scopes'].values() for r in members}
    return scopes,distances


def _baseline_scope(site_ids, event_date, by_site, metric):
    values = [_baseline(site_id, event_date, by_site, metric) for site_id in site_ids]
    values = [value for value in values if value is not None and np.isfinite(value)]
    if not values:
        return None
    return sum(values) if METRICS[metric]['kind'] == 'sum' else sum(values)/len(values)


def _cohort_observed(site_ids, month, by_site, metric):
    """Keep the same metric-specific cohort; never plot a partial sum as total."""
    values = [_row_value(by_site.get(site_id, {}).get(month), metric) for site_id in site_ids]
    valid = [value for value in values if value is not None and np.isfinite(value)]
    if not values or len(valid) != len(values):
        return None, len(valid)
    return (sum(valid) if METRICS[metric]['kind'] == 'sum' else sum(valid)/len(valid)), len(valid)


def _prediction_values(baseline, impact, low, high, metric):
    if baseline is None or impact is None:
        return None, None, None, None
    ceiling = 15 if metric == 'cqi_avg' else float('inf')
    bound = lambda value: float(min(ceiling, max(0, value)))
    prediction = bound(baseline+impact)
    return prediction, prediction-baseline, bound(baseline+low), bound(baseline+high)


def _group_series(scope, site_ids, event_date, by_site, outcomes_by_site, ranked_cases):
    series = {}
    for metric, definition in METRICS.items():
        points = []
        if not definition['available'] or (scope=='virtual_cluster' and metric!='downlink_traffic_gb'):
            series[metric] = points
            continue
        baseline = _baseline_scope(site_ids, event_date, by_site, metric)
        eligible = [site_id for site_id in site_ids if _baseline(site_id, event_date, by_site, metric) is not None]
        for offset in OFFSETS:
            month = _month_at_offset(event_date, offset)
            actual, observed_sites = _cohort_observed(eligible, month, by_site, metric)
            if offset < event_rules()['effect_start_offset']:
                impact = low = high = None
                case_count = 0
            else:
                impact, low, high, case_count = _predict_delta(
                    ranked_cases, outcomes_by_site, scope, metric, offset
                )
                if impact is not None and definition['kind'] == 'sum':
                    metric_sites = len(eligible)
                    impact *= metric_sites
                    low *= metric_sites
                    high *= metric_sites
            prediction, impact, lower, upper = _prediction_values(baseline, impact, low, high, metric)
            points.append({
                'offset': offset,
                'month': month.strftime('%Y-%m'),
                'observed': actual,
                'predicted': prediction,
                'predicted_impact': impact,
                'lower_95': lower,
                'upper_95': upper,
                'analog_cases': case_count,
                'baseline': baseline,
                'eligible_sites': len(eligible),
                'observed_sites': observed_sites,
                'is_partial_event_month': offset == 0,
                'effect_eligible': offset >= event_rules()['effect_start_offset'],
            })
        series[metric] = points
    return series


def build_cbr_impact_prediction(site_id,event_key=None):
    """Predict KPI changes for the selected site's T1/T2 and cluster neighbors."""
    query_site = Site.objects.select_related(
        'config_features', 'geometric_features', 'clutter_features', 'spatial_features',
        'anp_features', 'cluster_features', 'prelaunch_kpi',
    ).prefetch_related('cells','network_events').filter(site_id=site_id).first()
    if query_site is None:
        return None

    latest_month = MAOSMonthlyKPI.objects.aggregate(month=Max('month_date'))['month']
    if latest_month is None:
        return {'error': 'No monthly MAOS data is available.'}
    from services.models.preprocessing.network_events import effective_event_date,primary_event
    events=[e for e in query_site.network_events.all() if e.is_current]
    chosen=next((e for e in events if e.event_key==event_key),None) if event_key else primary_event(query_site)
    if event_key and chosen is None:
        return {'error':'The selected event does not belong to this site.'}
    query_event_date = chosen.effective_date if chosen else effective_event_date(query_site)
    detected_event = query_event_date is not None
    event_date = query_event_date or _next_month(latest_month)
    cutoff = event_date.replace(day=1)
    snapshot_cache = {}
    query_vector = build_site_similarity_vector(
        query_site, as_of_date=cutoff, snapshot_cache=snapshot_cache
    )
    if event_key:
        query_vector.update(event_type=chosen.event_type,
            tech_added='/'.join(chosen.details.get('technologies',[])) if chosen.event_type=='TECHNOLOGY_ADDED' else None,
            bands_added=','.join(chosen.details.get('bands',[])) if chosen.event_type in ('SITE_ADDED','TECHNOLOGY_ADDED','FREQUENCY_BAND_ADDED') else None)

    site_launches = list(Site.objects.filter(
        is_launched=True, launch_date__isnull=False, launch_date__lt=cutoff,
    ).exclude(pk=query_site.pk).select_related(
        'config_features', 'geometric_features', 'clutter_features', 'spatial_features',
        'anp_features', 'cluster_features', 'prelaunch_kpi',
    ).order_by('launch_date', 'site_id'))
    site_launches = [site for site in site_launches if (site.cluster_id==-1)==(query_site.cluster_id==-1) and (not query_site.canonical_site_id or site.canonical_site_id!=query_site.canonical_site_id)]
    launch_dates = {site.site_id: site.launch_date for site in site_launches}
    candidates = [
        build_site_similarity_vector(site, as_of_date=site.launch_date, snapshot_cache=snapshot_cache)
        for site in site_launches
    ]

    by_site = _month_rows()
    all_sites = list(Site.objects.all().only(
        'id', 'site_id', 'site_name', 'latitude', 'longitude', 'cluster_id',
    ))
    scope_members, distances = _scope_members(query_site, all_sites, by_site, event_date, snapshot_cache)
    site_by_id = {site.site_id: site for site in all_sites}

    outcomes_by_site = {}
    for event_site in site_launches:
        case_date = launch_dates[event_site.site_id]
        members = _scope_members(event_site, all_sites, by_site, case_date, snapshot_cache)[0]
        outcomes_by_site[event_site.site_id] = {
            scope: _event_group_responses(site_ids, case_date, by_site, available_before=cutoff)[0]
            for scope, site_ids in members.items()
        }

    selected_features = [
        field for field in GowerDistance.NUMERIC_FEATURES + GowerDistance.CATEGORICAL_FEATURES
        if field not in ROAD_FIELDS and not GowerDistance._is_missing(query_vector.get(field))
    ]
    ranking = rank_similar_cases(
        query_vector, candidates, k=10, selected_features=selected_features
    )
    ranked_cases = [
        {
            'site_id': item['features'].get('site_id'),
            'event_date': launch_dates.get(item['features'].get('site_id')),
            'similarity': item['similarity'],
            'weight': item['weight'],
            'features': item['features'],
        }
        for item in ranking['cases']
    ]

    from services.models.features.neighborhood import public_context, labels, scheme
    neighborhood_context = public_context(query_site,event_date,snapshot_cache)
    scopes = {}
    for scope, site_ids in scope_members.items():
        scopes[scope] = {
            'site_count': len(site_ids),
            'label': labels(scheme(query_site)).get(scope,scope),
            'is_sample': scope=='virtual_cluster',
            'status': 'available' if site_ids else 'no_active_neighbor_sites',
            'series': _group_series(scope, site_ids, event_date, by_site, outcomes_by_site, ranked_cases),
        }
    if not scope_members['cluster']:
        scopes['cluster'] = {
            'site_count': 0,
            'status': 'no_historical_cluster',
            'series': {metric: [] for metric in METRICS},
        }

    site_predictions = []
    for scope in ('tier1', 'tier2'):
        for neighbor_id in scope_members[scope]:
            neighbor = site_by_id[neighbor_id]
            points_by_metric = {}
            for metric, definition in METRICS.items():
                points = []
                if definition['available']:
                    baseline = _baseline(neighbor_id, event_date, by_site, metric)
                    for offset in OFFSETS:
                        actual = _row_value(
                            by_site.get(neighbor_id, {}).get(_month_at_offset(event_date, offset)), metric
                        )
                        if offset < event_rules()['effect_start_offset']:
                            impact = low = high = None
                            count = 0
                        else:
                            impact, low, high, count = _predict_delta(
                                ranked_cases, outcomes_by_site, scope, metric, offset
                            )
                        predicted, impact, lower, upper = _prediction_values(baseline, impact, low, high, metric)
                        points.append({
                            'offset': offset,
                            'month': _month_at_offset(event_date, offset).strftime('%Y-%m'),
                            'observed': actual,
                            'predicted': predicted,
                            'predicted_impact': impact,
                            'lower_95': lower,
                            'upper_95': upper,
                            'analog_cases': count,
                            'baseline': baseline,
                            'eligible_sites': 1 if baseline is not None else 0,
                            'observed_sites': 1 if actual is not None else 0,
                            'is_partial_event_month': offset == 0,
                            'effect_eligible': offset >= event_rules()['effect_start_offset'],
                        })
                points_by_metric[metric] = points
            site_predictions.append({
                'site_id': neighbor.site_id,
                'site_name': neighbor.site_name,
                'tier': scope,
                'site_count': 1,
                'status': 'available',
                'distance_m': distances.get(neighbor.site_id),
                'series': points_by_metric,
            })

    return {
        'query': {
            'site_id': query_site.site_id,
            'site_name': query_site.site_name,
            'cluster_id': query_site.cluster_id,
            'tier_scheme': scheme(query_site),
            'event_key':chosen.event_key if chosen else None,
            'event_date': event_date.isoformat(),
            'event_date_detected': detected_event,
            'date_note': 'Detected event date' if detected_event else 'Scenario date: month after latest available MAOS data',
            'latest_maos_month': latest_month.isoformat(),
        },
        'neighborhood': neighborhood_context,
        'available_events':[{'event_key':e.event_key,'date':e.effective_date.isoformat(),'label':e.details.get('label',e.event_type)} for e in events],
        'scope_labels': labels(scheme(query_site)),
        'distance_band_responses': {key:scopes[key] for key in ('distance_0_2','distance_2_5','distance_5_10')},
        'metrics': METRICS,
        'scopes': scopes,
        'site_predictions': site_predictions,
        'cases': ranked_cases,
        'case_count': len(ranked_cases),
        'active_features': ranking['active_features'],
        'feature_timing_note': query_vector['feature_timing_note'],
        'prediction_cutoff': cutoff.isoformat(),
        'effect_start_offset': event_rules()['effect_start_offset'],
        'event_month_note': 'Month 0 is a partial activation month shown for context only. Effect estimates and analog outcomes start at month +1.',
        'population_features': {key: query_vector.get(key) for key in ('population_density_1km_per_km2', 'population_tier1', 'population_tier2')},
        'population_quality': query_vector.get('population_quality'),
        'filter_explanation': ranking['filter_explanation'],
        'method_note': 'CBR estimates KPI changes from historical site-launch analogs relative to each recipient cohort’s three-month pre-event baseline. These are observational estimates, not a causal counterfactual.',
        'data_note': 'Only analog launches and completed outcome months strictly before the query event month enter predictions. Later query observations are display-only. Current MAOS import is LTE-only; RSRP, average RRC users and 2G/3G KPI histories are unavailable. Cluster cohorts are reconstructed from pre-event LTE activity.',
        'aggregation_note': 'Traffic/users use sums of individual recipient baselines and changes; CQI, throughput and delay use arithmetic means of site KPIs and changes. Observations use the same baseline-eligible cohort and show gaps when incomplete. Predicted levels and intervals respect physical bounds.',
    }
