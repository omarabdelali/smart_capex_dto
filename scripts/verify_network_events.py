"""Independent persisted-event reconciliation; run using manage.py shell/runpy."""
from collections import Counter
from datetime import date
import json
from pathlib import Path

from django.db.models import Min
from core.models import Cell, MAOSMonthlyKPI, RadioNetworkEvent, Site
from services.models.preprocessing.network_events import ADDITION_TYPES, bandwidth_from_prb, next_month, VERSION, event_rules

first = dict(MAOSMonthlyKPI.objects.filter(thrp_bits_dl__gt=0).values('cell__cell_id').annotate(
    first=Min('month_date')).values_list('cell__cell_id','first'))
events = list(RadioNetworkEvent.objects.filter(is_current=True).select_related('site'))
bandwidth_cells = {key for e in events if e.event_type not in ADDITION_TYPES for key in e.details['cell_ids']}
raw = {(key,month):(traffic,prbs) for key,month,traffic,prbs in MAOSMonthlyKPI.objects.filter(
    cell__cell_id__in=bandwidth_cells).values_list('cell__cell_id','month_date','thrp_bits_dl','prb_dl_available')}
consumed = set()
examples = {}
for cell in Cell.objects.all().iterator():
    assert cell.effective_activation_month == first.get(cell.cell_id), cell.cell_id
for event in events:
    details = event.details
    assert event.detector_version == VERSION
    assert event.configuration_date is None  # Current source contains no dated plan snapshots.
    if event.event_type in ADDITION_TYPES:
        activations = {key:first[key].isoformat() for key in details['cell_ids']}
        assert activations == details['cell_activation_months']
        assert event.effective_date == max(first[key] for key in details['cell_ids'])
        assert set(activations.values()) == {event.effective_date.isoformat()}
        assert details['completion_scope'] == 'activation_month_cohort'
        assert not consumed.intersection(details['cell_ids']), event.event_key
        consumed.update(details['cell_ids'])
    else:
        key, = details['cell_ids']
        traffic,prbs = raw[key,event.effective_date]
        assert traffic is not None and traffic>0
        assert bandwidth_from_prb(prbs) == event.new_bandwidth_mhz
        old_month = date.fromisoformat(details['previous_prb_month'])
        old_traffic,old_prbs = raw[key,old_month]
        assert old_traffic is not None and old_traffic>0
        assert bandwidth_from_prb(old_prbs) == event.previous_bandwidth_mhz
        assert (event.new_bandwidth_mhz > event.previous_bandwidth_mhz) == (event.event_type=='BANDWIDTH_UPGRADE')
        first_changed = date.fromisoformat(details['first_changed_prb_month'])
        confirmation = date.fromisoformat(details['confirmation_month'])
        observed_months, positive_months = [], []
        current = first_changed
        while current <= confirmation:
            assert (key,current) in raw, (key,current)
            traffic,prbs = raw[key,current]
            assert bandwidth_from_prb(prbs) == event.new_bandwidth_mhz
            observed_months.append(current.isoformat())
            if traffic is not None and traffic>0:
                positive_months.append(current)
            current = next_month(current)
        assert len(observed_months) >= event_rules()['bandwidth_confirmation_months']
        assert event.effective_date == min(positive_months)
        assert observed_months == details['confirmation_observation_months']
        assert details['confirmed_at'] == next_month(confirmation).isoformat()
        assert details['label'].startswith(f'bandwidth_{event.previous_bandwidth_mhz:g}_to_{event.new_bandwidth_mhz:g}_')
    if event.event_type == 'FREQUENCY_BAND_ADDED':
        assert details['label'] == '/'.join(sorted(details['bands'])) + '_ADDED'
        assert not Cell.objects.filter(site=event.site,technology__in=details['technologies'],
            band__in=details['bands'],effective_activation_month__lt=event.effective_date).exists()
    if event.event_type=='SITE_ADDED':
        assert set(details['cell_ids']) == set(Cell.objects.filter(site=event.site,
            effective_activation_month__lte=event.effective_date).values_list('cell_id',flat=True))
        assert event.site.launch_date == event.effective_date
        assert not Cell.objects.filter(site=event.site,effective_activation_month__lt=event.effective_date).exists()
    examples.setdefault(event.event_type,{'site_id':event.site.site_id,'site_name':event.site.site_name,
        'date':event.effective_date.isoformat(),'details':details,
        'previous_bandwidth_mhz':event.previous_bandwidth_mhz,'new_bandwidth_mhz':event.new_bandwidth_mhz})
assert consumed == set(Cell.objects.filter(is_launched=True).values_list('cell_id',flat=True))
report={'checked_on':date.today().isoformat(),'events_checked':len(events),
    'cells_checked':Cell.objects.count(),'added_cells_covered_exactly_once':len(consumed),
    'event_counts':dict(Counter(e.event_type for e in events)),'examples':examples,'mismatches':0,
    'detector_version':VERSION, 'event_rules':event_rules()}
output=Path('docs/verification/network_events/validation.json')
output.parent.mkdir(parents=True,exist_ok=True)
output.write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({key:value for key,value in report.items() if key!='examples'},indent=2))
