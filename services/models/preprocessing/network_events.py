"""Strict traffic-confirmed monthly radio events; no missing-to-zero inference."""
from collections import Counter, defaultdict
from datetime import date
from hashlib import sha256
from functools import lru_cache
import json
import math
from pathlib import Path
from django.db import transaction
from django.db.models import Min
from core.models import Cell, MAOSMonthlyKPI, RadioNetworkEvent, Site

VERSION = 'positive-traffic-sustained-v3'
ADDITION_TYPES = ('SITE_ADDED', 'TECHNOLOGY_ADDED', 'FREQUENCY_BAND_ADDED', 'CELL_ADDED')
PRB_BANDWIDTH = {25:5, 50:10, 75:15, 100:20}


@lru_cache(maxsize=1)
def event_rules():
    rules = json.loads((Path(__file__).resolve().parents[3] / 'config/event_rules.json').read_text(encoding='utf-8'))
    if rules['bandwidth_confirmation_months'] < 2 or rules['effect_start_offset'] != 1:
        raise ValueError('Bandwidth confirmation needs >=2 months and complete effects must start at +1.')
    return rules


def descriptive_event_label(kind, technologies=(), bands=(), old=None, new=None):
    if kind == 'TECHNOLOGY_ADDED':
        return '/'.join(sorted(technologies)) + '_ADDED'
    if kind == 'FREQUENCY_BAND_ADDED':
        return '/'.join(sorted(bands)) + '_ADDED'
    if kind in ('BANDWIDTH_UPGRADE', 'BANDWIDTH_DOWNGRADE') and old is not None and new is not None:
        direction = 'upgrade' if new > old else 'downgrade'
        return f'bandwidth_{old:g}_to_{new:g}_{direction}'
    return kind


def bandwidth_from_prb(value):
    if value is None or not math.isfinite(value):
        return None
    return next((bw for prb,bw in PRB_BANDWIDTH.items() if abs(value-prb)<=5), None)


def next_month(month):
    return date(month.year+(month.month==12), month.month%12+1, 1)


def analyze_cell(rows, technology, data_start):
    """Traffic dates activation; consecutive mapped runs confirm bandwidth shifts.

    A rejected one-month spike cannot create a reverse event on return to the
    accepted state. Gaps/unmapped values start a new segment, so unknown months
    cannot confirm persistence. Confirmation is recorded separately from onset.
    """
    activation, evidence, saw_zero = None, 'no_positive_traffic', False
    segments, segment, run = [], [], []
    previous, changes, skipped = None, [], 0
    for month,traffic,prbs in rows:
        positive = traffic is not None and traffic>0
        if positive and activation is None:
            activation = month
            evidence = ('baseline_left_censored' if month==data_start else
                        'zero_to_positive' if saw_zero else 'first_positive_observed')
        if traffic==0:
            saw_zero=True
        if technology!='4G':
            continue
        bw = bandwidth_from_prb(prbs)
        contiguous = previous is not None and next_month(previous[0])==month
        if bw is None or not contiguous:
            if previous is not None and bw is not None and bw != previous[1]:
                skipped+=1
            if segment:
                segments.append(segment)
            segment, run = [], []
        if bw is not None:
            if not run or run[-1][3] != bw:
                run = []
                segment.append(run)
            run.append((month, traffic, prbs, bw))
        previous=(month,bw,positive) if bw is not None else None
    if segment:
        segments.append(segment)
    required = event_rules()['bandwidth_confirmation_months']
    rejected = unconfirmed = 0
    for runs in segments:
        reference = runs[0]
        for candidate in runs[1:]:
            old, new = reference[-1][3], candidate[-1][3]
            if new == old:
                reference = reference + candidate
                continue
            if len(candidate) < required:
                if candidate is runs[-1]:
                    unconfirmed += 1
                else:
                    rejected += 1
                continue
            old_active = [r for r in reference if r[1] is not None and r[1] > 0]
            new_active = [r for r in candidate if r[1] is not None and r[1] > 0]
            if new_active and old_active:
                effective = new_active[0]
                confirmation = max(candidate[required - 1][0], effective[0])
                kind = 'BANDWIDTH_UPGRADE' if new > old else 'BANDWIDTH_DOWNGRADE'
                changes.append({'event_type': kind, 'effective_date': effective[0],
                    'previous_bandwidth_mhz': old, 'new_bandwidth_mhz': new,
                    'details': {'label': descriptive_event_label(kind, old=old, new=new),
                        'first_changed_prb_month': candidate[0][0].isoformat(),
                        'previous_prb_month': old_active[-1][0].isoformat(), 'available_prbs': effective[2],
                        'confirmation_month': confirmation.isoformat(), 'confirmation_months_required': required,
                        'confirmation_observation_months': [r[0].isoformat() for r in candidate if r[0] <= confirmation],
                        'confirmed_at': next_month(confirmation).isoformat(),
                        'date_basis': 'first_positive_traffic_in_sustained_new_prb_state',
                        'configuration_source': 'monthly_prb_inference', 'prb_tolerance': 5,
                        'effect_start_offset': event_rules()['effect_start_offset']}})
            # An observed positive new state establishes inventory even without
            # a positive old state; unknown old operation cannot invent an event.
            if new_active:
                reference = candidate
    return {'activation':activation,'evidence':evidence,'bandwidth_changes':changes,
            'skipped_gap_transitions':skipped, 'rejected_transient_bandwidth_runs': rejected,
            'unconfirmed_bandwidth_runs': unconfirmed}


def addition(kind,cells,states):
    activations={c.cell_id:states[c.pk]['activation'].isoformat() for c in cells}
    techs=sorted({c.technology for c in cells})
    return {'site_id':cells[0].site_id,'event_type':kind,
        'effective_date':max(states[c.pk]['activation'] for c in cells),
        'details':{'cell_ids':sorted(activations),'cell_activation_months':activations,
            'technologies':techs,'bands':sorted({c.band for c in cells}),
            'label':descriptive_event_label(kind, technologies=techs, bands={c.band for c in cells}),
            'date_basis':'last_required_cell_first_positive_traffic',
            'membership_source':'current_cell_plan','configuration_source':'current_snapshot_only',
            'action_boundary':'activation_month',
            'completion_scope':'activation_month_cohort',
            'later_additions':'separate_monthly_actions',
            'effect_start_offset':event_rules()['effect_start_offset'],
            'activation_evidence':{c.cell_id:states[c.pk]['evidence'] for c in cells}}}


def classify_additions(cells,states,data_start):
    """Classify each monthly action against only earlier active inventory.

    Future additions cannot turn an initial site/technology action into one
    lifetime event. Without rollout IDs, different months are distinct actions.
    Unknown plan members block a claim that their whole group was added.
    """
    cohorts=defaultdict(list)
    unknown=[c for c in cells if states[c.pk]['activation'] is None]
    for c in cells:
        activation=states[c.pk]['activation']
        if activation is not None and activation>data_start:
            cohorts[activation].append(c)
    events=[]
    for month,members in sorted(cohorts.items()):
        prior=[c for c in cells if states[c.pk]['activation'] is not None
               and states[c.pk]['activation']<month]
        if not prior and not unknown:
            events.append(addition('SITE_ADDED',members,states))
            continue
        consumed=set()
        new_techs={c.technology for c in members}-{c.technology for c in prior}-{c.technology for c in unknown}
        tech_members=[c for c in members if c.technology in new_techs]
        if tech_members:
            events.append(addition('TECHNOLOGY_ADDED',tech_members,states))
            consumed.update(c.pk for c in tech_members)
        band_key=lambda c:(c.technology,c.band)
        prior_bands={band_key(c) for c in prior+unknown}
        new_bands=defaultdict(list)
        for c in members:
            if c.pk not in consumed and band_key(c) not in prior_bands:
                new_bands[band_key(c)].append(c)
        for band_members in new_bands.values():
            events.append(addition('FREQUENCY_BAND_ADDED',band_members,states))
            consumed.update(c.pk for c in band_members)
        remaining=[c for c in members if c.pk not in consumed]
        if remaining:
            events.append(addition('CELL_ADDED',remaining,states))
    return events


def detect_events():
    start=MAOSMonthlyKPI.objects.aggregate(month=Min('month_date'))['month']
    cells=list(Cell.objects.all())
    histories=defaultdict(list)
    for pk,month,traffic,prbs in MAOSMonthlyKPI.objects.order_by('cell_id','month_date').values_list(
            'cell_id','month_date','thrp_bits_dl','prb_dl_available').iterator(chunk_size=10000):
        histories[pk].append((month,traffic,prbs))
    history_count=len(histories)
    states,by_site,events={},defaultdict(list),[]
    for c in cells:
        state=analyze_cell(histories.pop(c.pk,[]),c.technology,start)
        states[c.pk]=state
        by_site[c.site_id].append(c)
        for change in state['bandwidth_changes']:
            change['site_id']=c.site_id
            change['details'].update({'cell_ids':[c.cell_id],'technologies':[c.technology],
                'cell_activation_months':{c.cell_id:state['activation'].isoformat()}})
            events.append(change)
    if start:
        for members in by_site.values():
            events.extend(classify_additions(members,states,start))
    for event in events:
        key=f"{event['site_id']}:{event['event_type']}:{event['effective_date']}:{','.join(event['details']['cell_ids'])}"
        event['event_key']=sha256(key.encode()).hexdigest()
    stats={'cells_evaluated':len(cells),'cells_with_kpi_history':history_count,'detected_cells':sum(
        s['activation'] is not None and s['activation']>start for s in states.values()) if start else 0,
        'detected_sites':sum(e['event_type']=='SITE_ADDED' for e in events),
        'detected_site_technologies':sum(e['event_type']=='TECHNOLOGY_ADDED' for e in events),
        'event_counts':dict(Counter(e['event_type'] for e in events)),
        'skipped_gap_bandwidth_transitions':sum(s['skipped_gap_transitions'] for s in states.values()),
        'rejected_transient_bandwidth_runs':sum(s['rejected_transient_bandwidth_runs'] for s in states.values()),
        'unconfirmed_bandwidth_runs':sum(s['unconfirmed_bandwidth_runs'] for s in states.values()),
        'event_rules':event_rules(),
        'activation_evidence_counts':dict(Counter(s['evidence'] for s in states.values())),
        'data_start':start}
    return cells,states,events,stats


def detect_and_save_events():
    cells,states,events,stats=detect_events()
    site_dates={e['site_id']:e['effective_date'] for e in events if e['event_type']=='SITE_ADDED'}
    with transaction.atomic():
        # Retain prior detections as inactive evidence instead of deleting history.
        RadioNetworkEvent.objects.filter(is_current=True).update(is_current=False)
        RadioNetworkEvent.objects.bulk_create([RadioNetworkEvent(**e,detector_version=VERSION) for e in events],
            update_conflicts=True,unique_fields=['event_key'],update_fields=['event_type','effective_date',
                'details','previous_bandwidth_mhz','new_bandwidth_mhz','is_current','detector_version'],batch_size=500)
        for c in cells:
            state=states[c.pk]
            c.effective_activation_month=state['activation']
            c.activation_evidence=state['evidence']
            c.is_launched=bool(state['activation'] and state['activation']>stats['data_start'])
            c.launch_date=state['activation'] if c.is_launched else None
        Cell.objects.bulk_update(cells,['effective_activation_month','activation_evidence','is_launched','launch_date'],batch_size=500)
        sites=list(Site.objects.all())
        for site in sites:
            site.is_launched=site.pk in site_dates
            site.launch_date=site_dates.get(site.pk)
        Site.objects.bulk_update(sites,['is_launched','launch_date'],batch_size=500)
    return stats


def event_payload(event):
    return {'event_key':event.event_key,'event_type':event.event_type,
        'date_precision':'month',
        'first_full_effect_month':next_month(event.effective_date).isoformat(),
        'event_label':event.details.get('label') or descriptive_event_label(event.event_type,
            technologies=event.details.get('technologies',()), bands=event.details.get('bands',()),
            old=event.previous_bandwidth_mhz, new=event.new_bandwidth_mhz),
        'launch_date':event.effective_date.isoformat(),'event_date':event.effective_date.isoformat(),
        'configuration_date':event.configuration_date.isoformat() if event.configuration_date else None,
        'previous_bandwidth_mhz':event.previous_bandwidth_mhz,'new_bandwidth_mhz':event.new_bandwidth_mhz,
        **event.details}


def site_event_data(site):
    cached=getattr(site,'_site_addition_display_data',None)
    if cached is not None:
        return cached
    events=[event_payload(e) for e in site.network_events.all() if e.is_current]
    additions=[e for e in events if e['event_type'] in ADDITION_TYPES]
    by_cell={key:e for e in additions for key in e['cell_ids']}
    added=[{'cell_id':c.cell_id,'cell_name':c.cell_name,'technology':c.technology,
        'event_type':by_cell[c.cell_id]['event_type'],
        'launch_date':by_cell[c.cell_id]['cell_activation_months'][c.cell_id],
        'group_effective_date':by_cell[c.cell_id]['launch_date'],'activation_evidence':c.activation_evidence}
        for c in site.cells.all() if c.cell_id in by_cell]
    result={'events':additions,'network_events':events,'added_cells':added}
    site._site_addition_display_data=result
    return result


def primary_event(site):
    """The first officially completed group, never its earliest member cell."""
    events = [e for e in site.network_events.all() if e.is_current]
    additions = [e for e in events if e.event_type in ADDITION_TYPES]
    return min(additions or events, key=lambda e:(e.effective_date,e.event_key), default=None)


def effective_event_date(site):
    event = primary_event(site)
    if event is not None:
        return event.effective_date
    # Compatibility for manually dated scenarios with no persisted detection.
    return site.launch_date or min((c.launch_date for c in site.cells.all()
        if c.is_launched and c.launch_date), default=None)


def refresh_event_configuration():
    """Refresh only configuration summaries; geographic extraction is unchanged."""
    from core.models import ConfigurationFeatures
    from services.models.features.context import configuration_feature_values
    updated = 0
    for site in Site.objects.prefetch_related('cells','network_events').iterator(chunk_size=100):
        values = configuration_feature_values(site)
        updated += ConfigurationFeatures.objects.filter(site=site).update(**values)
    return updated


def cluster_events(cluster_id):
    cells={c.cell_id:c for c in Cell.objects.filter(site__cluster_id=cluster_id)}
    result=[]
    for e in RadioNetworkEvent.objects.filter(site__cluster_id=cluster_id,is_current=True).select_related('site'):
        payload=event_payload(e)
        members=[cells[key] for key in payload['cell_ids'] if key in cells]
        payload.update({'site_id':e.site.site_id,'site_name':e.site.site_name,
            'cell_id':', '.join(c.cell_id for c in members),'cell_name':', '.join(c.cell_name for c in members),
            'technology':'/'.join(payload['technologies'])})
        result.append(payload)
    return result
