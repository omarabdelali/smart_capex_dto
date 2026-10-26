"""Pure transformations for rollups of report-backed MAOS counters."""


USER_RATIOS = {
    'edge_user_share': ('border_user_avg', 'traffic_user_avg'),
    'edge_user_peak_ratio': ('border_user_max', 'border_user_avg'),
    'lowlatency_user_share': ('lowlatency_user_avg', 'traffic_user_avg'),
}


def user_ratio_values(row):
    result = {}
    for metric in USER_RATIOS:
        numerator, denominator = row.get(metric+'_num'), row.get(metric+'_den')
        result[metric] = numerator/denominator if numerator is not None and denominator is not None and denominator > 0 else None
    return result


def user_ratio_annotations():
    from django.db.models import Q, Sum, Count
    result = {}
    for metric, (numerator, denominator) in USER_RATIOS.items():
        paired = Q(**{numerator+'__gte':0, denominator+'__gte':0})
        result[metric+'_num'] = Sum(numerator, filter=paired)
        result[metric+'_den'] = Sum(denominator, filter=paired)
        result[metric+'_rows'] = Count('pk', filter=paired)
    return result


def normalize_monthly_totals(row):
    """Convert summed counter components into correctly weighted monthly KPIs."""
    bits = row.get('traffic_bits', row.get('dl_bits'))
    throughput_bits = row.get('dl_bits')
    last_tti_bits = row.get('dl_last_tti_bits')
    time_ms = row.get('dl_time_ms')
    used = row.get('prb_used')
    available = row.get('prb_available')
    delay_time = row.get('delay_time_ms')
    delay_packets = row.get('delay_packets')
    downtime = row.get('unavailable_s')
    observed = row.get('observation_s')
    cqi_weighted_sum = row.get('cqi_weighted_total', row.get('cqi_weighted_sum'))
    cqi_sample_count = row.get('cqi_sample_count')

    throughput_kbps = None
    if throughput_bits is not None and last_tti_bits is not None and time_ms is not None and time_ms > 0 and throughput_bits >= last_tti_bits:
        throughput_kbps = (throughput_bits - last_tti_bits) / time_ms

    return {
        'traffic_user_avg': row.get('traffic_users'),
        'active_users_avg': row.get('active_users'),
        'thrp_dl_gb': bits / 8_000_000_000 if bits is not None else None,
        'thrp_ul_gb': None,
        'prb_util_dl_pct': used / available * 100 if used is not None and available is not None and available > 0 else None,
        'cqi_avg': cqi_weighted_sum / cqi_sample_count if cqi_weighted_sum is not None and cqi_sample_count is not None and cqi_sample_count > 0 else None,
        'dl_throughput_kbps': throughput_kbps,
        'dl_packet_delay_ms': delay_time / delay_packets if delay_time is not None and delay_packets is not None and delay_packets > 0 else None,
        'cell_availability_pct': 100 * (1 - downtime / observed) if downtime is not None and observed is not None and observed > 0 else None,
        'reporting_cells': row.get('reporting_cells'),
        **user_ratio_values(row),
    }
