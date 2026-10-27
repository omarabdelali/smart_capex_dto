"""Retrospective action context for interpretation, never a forecast input."""
from collections import defaultdict
from services.models.features.neighborhood import offset


def other_site_actions(events,origin,selected_key,cutoff):
    groups=defaultdict(list)
    for event in events:
        site=event.site
        key=getattr(site,'canonical_site_id','') or getattr(site,'site_id',None)
        if key!=origin or getattr(event,'event_key',None)==selected_key:
            continue
        if cutoff<=event.effective_date<=offset(cutoff,6):
            groups[event.effective_date].append(event)
    return [{'date':month.isoformat(),'phase':'concurrent' if month==cutoff else 'later',
        'event_count':len(values),'event_types':sorted({e.event_type for e in values}),
        'affected_cells':len({c for e in values for c in e.details.get('cell_ids',[])})}
        for month,values in sorted(groups.items())]
