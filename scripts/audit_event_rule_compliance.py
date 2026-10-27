"""Read-only audit of the requested activation, taxonomy and outcome timing rules.

Run through manage.py shell/runpy. Does not redetect or update persisted events.
The persistence scenario is checked against the configured production policy.
"""
from collections import Counter, defaultdict
from datetime import date
import json
from pathlib import Path
from types import SimpleNamespace

from django.db.models import Min
from core.models import Cell, MAOSMonthlyKPI, RadioNetworkEvent
from services.models.preprocessing.network_events import (
    ADDITION_TYPES, analyze_cell, bandwidth_from_prb, classify_additions, next_month, event_payload, event_rules, VERSION,
)
from services.models.prediction.cbr_impact import PREDICT_OFFSETS, _event_group_responses


def run():
    first = dict(MAOSMonthlyKPI.objects.filter(thrp_bits_dl__gt=0).values('cell_id').annotate(
        first=Min('month_date')).values_list('cell_id', 'first'))
    cells = list(Cell.objects.all())
    by_id = {c.cell_id: c for c in cells}
    by_site = defaultdict(list)
    for cell in cells:
        by_site[cell.site_id].append(cell)
    events = list(RadioNetworkEvent.objects.filter(is_current=True).select_related('site'))
    added = [e for e in events if e.event_type in ADDITION_TYPES]
    changes = [e for e in events if e.event_type in ('BANDWIDTH_UPGRADE', 'BANDWIDTH_DOWNGRADE')]
    mismatch_cells = [c.cell_id for c in cells if c.effective_activation_month != first.get(c.pk)]
    event_date_mismatches, activation_metadata_mismatches = [], []
    consumed = Counter()
    completeness = Counter()
    examples = {}
    combined_technologies = 0
    prior_same_band_different_frequency = []
    for event in added:
        members = [by_id[key] for key in event.details['cell_ids']]
        dates = [first.get(c.pk) for c in members]
        if any(d is None for d in dates) or event.effective_date != max(dates):
            event_date_mismatches.append(event.event_key)
        expected = {c.cell_id: first[c.pk].isoformat() for c in members if c.pk in first}
        if event.details.get('cell_activation_months') != expected:
            activation_metadata_mismatches.append(event.event_key)
        consumed.update(event.details['cell_ids'])
        if event.event_type == 'CELL_ADDED':
            continue
        inventory = by_site[event.site_id]
        techs = {c.technology for c in members}
        bands = {(c.technology, c.band) for c in members}
        if event.event_type == 'TECHNOLOGY_ADDED' and len(techs) > 1:
            combined_technologies += 1
        relevant = (inventory if event.event_type == 'SITE_ADDED' else
                    [c for c in inventory if c.technology in techs] if event.event_type == 'TECHNOLOGY_ADDED' else
                    [c for c in inventory if (c.technology, c.band) in bands])
        unknown = [c.cell_id for c in relevant if c.pk not in first]
        later = [c.cell_id for c in relevant if first.get(c.pk, date.min) > event.effective_date]
        if later or unknown:
            completeness[event.event_type] += 1
            examples.setdefault(event.event_type, {'site_id': event.site.site_id, 'site_name': event.site.site_name,
                'event_month': event.effective_date, 'member_cells': event.details['cell_ids'],
                'later_same_group_cells': later, 'unknown_same_group_cells': unknown,
                'label': event_payload(event)['event_label']})
        if event.event_type == 'FREQUENCY_BAND_ADDED':
            prior = [c.cell_id for c in relevant if c.pk in first and first[c.pk] < event.effective_date]
            if prior:
                prior_same_band_different_frequency.append({'site_id': event.site.site_id,
                    'event_month': event.effective_date, 'prior_same_band_cells': prior,
                    'member_cells': event.details['cell_ids'], 'bands': event.details['bands']})
    raw = defaultdict(dict)
    changed_keys = {key for e in changes for key in e.details['cell_ids']}
    for key, month, traffic, prbs in MAOSMonthlyKPI.objects.filter(cell__cell_id__in=changed_keys).values_list(
            'cell__cell_id', 'month_date', 'thrp_bits_dl', 'prb_dl_available').iterator(chunk_size=10000):
        raw[key][month] = (traffic, bandwidth_from_prb(prbs))
    sustained_counts, bw_examples = Counter(), {}
    wrong_bw_dates = []
    dynamic_labels = Counter()
    for event in events:
        label = str(event_payload(event)['event_label'])
        if event.event_type == 'TECHNOLOGY_ADDED':
            dynamic_labels['technology_specific'] += int(label != event.event_type)
        elif event.event_type == 'FREQUENCY_BAND_ADDED':
            dynamic_labels['band_specific'] += int(label != event.event_type)
        elif event.event_type in ('BANDWIDTH_UPGRADE', 'BANDWIDTH_DOWNGRADE'):
            dynamic_labels['bandwidth_from_to_specific'] += int(label != event.event_type)
    for event in changes:
        key, = event.details['cell_ids']
        onset = date.fromisoformat(event.details['first_changed_prb_month'])
        current, months, positive = onset, 0, []
        while current in raw[key] and raw[key][current][1] == event.new_bandwidth_mhz:
            months += 1
            traffic = raw[key][current][0]
            if traffic is not None and traffic > 0:
                positive.append(current)
            current = next_month(current)
        if not positive or positive[0] != event.effective_date:
            wrong_bw_dates.append(event.event_key)
        if months >= 2:
            status = 'at_least_two_consecutive_mapped_months'
        elif current in raw[key] and raw[key][current][1] == event.previous_bandwidth_mhz:
            status = 'one_month_then_reverted'
        else:
            status = 'one_month_without_confirming_followup'
        sustained_counts[status] += 1
        bw_examples.setdefault(status, {'site_id': event.site.site_id, 'cell_id': key,
            'effective_month': event.effective_date, 'old_mhz': event.previous_bandwidth_mhz,
            'new_mhz': event.new_bandwidth_mhz, 'first_changed_month': onset,
            'consecutive_new_state_months': months, 'following_month': current,
            'following_state': raw[key].get(current)})
    oct_, nov_, dec_ = date(2023, 10, 1), date(2023, 11, 1), date(2023, 12, 1)
    transient = analyze_cell([(oct_, 1, 25), (nov_, 1, 100), (dec_, 1, 25)], '4G', oct_)
    # Full current-plan grouping differs from the implemented monthly action rule.
    fixture = [SimpleNamespace(pk=i, cell_id=str(i), site_id=1, technology=tech, band=band, frequency=freq)
               for i, tech, band, freq in [(1, '3G', 'U2100', 2100), (2, '4G', 'L1800', 1800), (3, '4G', 'L1800', 1800)]]
    states = {i: {'activation': m, 'evidence': 'fixture'} for i, m in [(1, oct_), (2, nov_), (3, dec_)]}
    staggered = classify_additions(fixture, states, oct_)
    history = {'neighbor': {oct_: {'traffic_bits': 10 * 8e9}, nov_: {'traffic_bits': 15 * 8e9}, dec_: {'traffic_bits': 20 * 8e9}}}
    responses, _ = _event_group_responses(['neighbor'], nov_, history)
    report = {
        'audit_date': '2026-10-27', 'scope': 'Read-only verification of refreshed events',
        'detector_version': VERSION, 'event_rules': event_rules(),
        'cells_checked': len(cells), 'events_checked': len(events),
        'counts': dict(Counter(e.event_type for e in events)),
        'cell_first_positive_mismatch_count': len(mismatch_cells),
        'addition_group_date_mismatch_count': len(event_date_mismatches),
        'addition_cell_date_metadata_mismatch_count': len(activation_metadata_mismatches),
        'duplicate_added_cell_count': sum(n > 1 for n in consumed.values()),
        'bandwidth_first_positive_new_state_date_mismatch_count': len(wrong_bw_dates),
        'strict_current_plan_group_incomplete_counts': dict(completeness),
        'strict_current_plan_group_examples': examples,
        'technology_events_combining_multiple_technologies': combined_technologies,
        'band_events_with_prior_same_technology_band_count': len(prior_same_band_different_frequency),
        'band_events_with_prior_same_technology_band_examples': prior_same_band_different_frequency[:5],
        'specific_labels': dict(dynamic_labels),
        'sustained_shift_audit_definition': 'At least two consecutive observations mapped to the same new bandwidth, matching the configured production threshold.',
        'bandwidth_persistence_counts': dict(sustained_counts), 'bandwidth_persistence_examples': bw_examples,
        'synthetic_one_month_reversal_detected_events': transient['bandwidth_changes'],
        'synthetic_staggered_technology_events': staggered,
        'effect_prediction_offsets': list(PREDICT_OFFSETS),
        'synthetic_effects_including_month_zero': responses['downlink_traffic_gb'],
        'left_censoring_note': 'First-positive cells at the first dataset month are baseline inventory, not proven new launches.',
        'taxonomy_note': 'User confirmed monthly cohorts on 2026-10-27: November initial addition and separate December cells. Full-current-plan completion is a different, intentionally unused policy.',
    }
    report['compliance_checks'] = {
        'first_positive_activation_dates': not mismatch_cells,
        'monthly_group_dates_and_metadata': not event_date_mismatches and not activation_metadata_mismatches,
        'no_duplicate_cell_assignments': not any(n > 1 for n in consumed.values()),
        'bandwidth_effective_dates': not wrong_bw_dates,
        'all_bandwidth_shifts_sustained': sustained_counts['at_least_two_consecutive_mapped_months'] == len(changes),
        'synthetic_transient_rejected': not transient['bandwidth_changes'],
        'bands_not_split_by_frequency': not prior_same_band_different_frequency,
        'band_specific_labels': dynamic_labels['band_specific'] == sum(e.event_type=='FREQUENCY_BAND_ADDED' for e in events),
        'bandwidth_specific_labels': dynamic_labels['bandwidth_from_to_specific'] == len(changes),
        'effects_start_at_one': min(PREDICT_OFFSETS) == 1 and 0 not in responses['downlink_traffic_gb'],
        'approved_monthly_action_scope': all(e.details.get('completion_scope') == 'activation_month_cohort' for e in added),
    }
    output = Path('docs/verification/event_rule_compliance/2026-10-27-current.json')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, default=str), encoding='utf-8')
    assert all(report['compliance_checks'].values()), report['compliance_checks']
    print(json.dumps({k: v for k, v in report.items() if not k.endswith('examples') and not k.startswith('synthetic_')}, indent=2, default=str))


run()
