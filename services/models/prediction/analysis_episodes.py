"""One physical-origin/month analysis unit; preserve raw detections and dates."""
from collections import defaultdict,Counter
from types import SimpleNamespace
import hashlib
import json
from django.db import transaction
from core.models import Site,RadioNetworkEvent,AnalysisEpisode,AnalysisEpisodeMember

VERSION='analysis-episode-v1'
ADDITIONS={'SITE_ADDED','TECHNOLOGY_ADDED','FREQUENCY_BAND_ADDED','CELL_ADDED'}


def grouped_episodes(events,sites):
    grouped=defaultdict(list)
    for event in events:
        key=event.site.canonical_site_id or event.site.site_id
        grouped[key,event.effective_date.replace(day=1)].append(event)
    result=[]
    for (key,month),members in sorted(grouped.items()):
        members=sorted(members,key=lambda e:e.event_key)
        actions=[{'event_key':e.event_key,'event_type':e.event_type,'cell_ids':sorted(e.details.get('cell_ids',[])),
            'effective_date':e.effective_date.isoformat(),'configuration_date':e.configuration_date.isoformat() if e.configuration_date else None,
            'previous_bandwidth_mhz':e.previous_bandwidth_mhz,'new_bandwidth_mhz':e.new_bandwidth_mhz,
            'details':e.details,'detector_version':e.detector_version} for e in members]
        kinds=sorted({e.event_type for e in members});signature='+'.join(kinds)
        details={'analysis_unit':'episode','label':f"{month:%Y-%m}: {', '.join(kinds)} ({len(members)} actions)",
            'raw_event_keys':[e.event_key for e in members],'actions':actions,'action_signature':signature,
            'cell_ids':sorted({c for e in members for c in e.details.get('cell_ids',[])}),
            'technologies':sorted({t for e in members for t in e.details.get('technologies',[])}),
            'bands':sorted({b for e in members for b in e.details.get('bands',[])}),
            'cell_activation_months':{c:v for e in members for c,v in e.details.get('cell_activation_months',{}).items()},
            'added_cell_ids':sorted({c for e in members if e.event_type in ADDITIONS for c in e.details.get('cell_ids',[])})}
        digest=hashlib.sha256(json.dumps({'version':VERSION,'site':key,'month':month.isoformat(),'actions':actions},sort_keys=True).encode()).hexdigest()
        result.append({'episode_key':digest,'site':sites.get(key,members[0].site),'effective_date':month,
            'event_type':kinds[0] if len(kinds)==1 else 'COMPOUND_EVENT','action_signature':signature,'details':details,'members':members})
    return result


def refresh_episodes():
    sites={s.site_id:s for s in Site.objects.all()}
    events=list(RadioNetworkEvent.objects.filter(is_current=True).select_related('site'))
    rows=grouped_episodes(events,sites);keys=[r['episode_key'] for r in rows]
    with transaction.atomic():
        AnalysisEpisode.objects.filter(is_current=True).exclude(episode_key__in=keys).update(is_current=False)
        existing=set(AnalysisEpisode.objects.filter(episode_key__in=keys).values_list('episode_key',flat=True))
        AnalysisEpisode.objects.bulk_create([AnalysisEpisode(**{k:v for k,v in row.items() if k!='members'}) for row in rows if row['episode_key'] not in existing],batch_size=500)
        AnalysisEpisode.objects.filter(episode_key__in=keys).update(is_current=True)
        by_key={e.episode_key:e for e in AnalysisEpisode.objects.filter(episode_key__in=keys)}
        AnalysisEpisodeMember.objects.bulk_create([AnalysisEpisodeMember(episode=by_key[row['episode_key']],raw_event=event)
            for row in rows if row['episode_key'] not in existing for event in row['members']],batch_size=500)
    return {'version':VERSION,'raw_events':len(events),'episodes':len(rows),'multi_action_episodes':sum(len(r['members'])>1 for r in rows),
        'raw_events_in_multi_action_episodes':sum(len(r['members']) for r in rows if len(r['members'])>1),
        'episode_types':dict(Counter(r['event_type'] for r in rows)),'new_versions':len(rows)-len(existing)}


def as_event(episode):
    return SimpleNamespace(event_key=episode.episode_key,site=episode.site,event_type=episode.event_type,
        effective_date=episode.effective_date,configuration_date=None,previous_bandwidth_mhz=None,
        new_bandwidth_mhz=None,details=episode.details,is_current=episode.is_current)


def site_episodes(site):
    return AnalysisEpisode.objects.filter(site__site_id=site.canonical_site_id or site.site_id,is_current=True).select_related('site')


def episode_magnitude(event,prbs):
    """Each addition cell and bandwidth transition contributes once; unknown stays NULL."""
    added=event.details.get('added_cell_ids',[])
    values=[prbs.get((key,event.effective_date)) for key in added];transitions={}
    for action in event.details.get('actions',[]):
        if action['event_type'] in ('BANDWIDTH_UPGRADE','BANDWIDTH_DOWNGRADE'):
            for key in action['cell_ids']:
                signature=(key,action['previous_bandwidth_mhz'],action['new_bandwidth_mhz'])
                transitions[signature]=5*(signature[2]-signature[1]) if signature[1] is not None and signature[2] is not None else None
    values+=list(transitions.values())
    return {'event_prb_delta':sum(values) if values and all(v is not None for v in values) else None,'event_added_cells':len(added)}
