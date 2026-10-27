"""Explicit training-reference generation; no database mutations."""
from collections import Counter
from pathlib import Path
from django.conf import settings
from core.models import RadioNetworkEvent
from .calibration import policy,freeze_reference
from .feature_vector import build_site_similarity_vector


def build_reference(per_type=12,progress=print):
    if per_type<1:
        raise ValueError('per-type must be positive')
    counts=Counter();rows=[];cache={}
    events=RadioNetworkEvent.objects.filter(is_current=True).select_related('site').order_by('effective_date','event_key')
    # Earliest deterministic cases give historical queries a usable prior reference.
    seen=set()
    for event in events:
        if counts[event.event_type]>=per_type:
            continue
        key=(event.site.canonical_site_id or event.site_id,event.effective_date,event.event_type)
        if key in seen:
            continue
        seen.add(key)
        vector=build_site_similarity_vector(event.site,as_of_date=event.effective_date,snapshot_cache=cache,allow_current_roads=True)
        vector.update(event_type=event.event_type,event_key=event.event_key,
            tech_added='/'.join(event.details.get('technologies',[])) or None,
            bands_added=','.join(event.details.get('bands',[])) or None)
        rows.append(vector);counts[event.event_type]+=1
        progress(f'Reference profile {len(rows)}: {event.event_type} {event.site.site_id} {event.effective_date}')
    artifact=freeze_reference(rows,Path(settings.BASE_DIR)/policy()['reference_path'],
        {'sampling':'earliest distinct physical-site/month/type profiles, capped per type',
         'per_type':per_type,'counts':dict(counts),'status':'frozen, representative initial reference; not tuned'})
    return {'profiles':len(rows),'reference_id':artifact['reference_id'],'counts':dict(counts)}
