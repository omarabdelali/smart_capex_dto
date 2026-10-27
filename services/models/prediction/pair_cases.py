"""Historical event -> physical-recipient cases. Monthly outcomes are never inputs."""
from collections import defaultdict
from datetime import date
import hashlib
import json
from pathlib import Path
from statistics import median
import math
from django.db.models import Min,Max
from core.models import RadioNetworkEvent,Cell,MAOSMonthlyKPI
from services.models.features.neighborhood import neighborhood,inventory
from services.models.preprocessing.maos_aggregation import normalize_monthly_totals
from .cbr_impact import _month_rows,_month_at_offset,_row_value,OUTPUT_FIELDS

PAIR_NUMERIC=('distance_m','relative_bearing_deg','recipient_pre_dl_gb',
    'recipient_pre_active_users','recipient_pre_prb_util_pct','recipient_pre_cqi',
    'event_prb_delta','event_added_cells')
PAIR_CATEGORICAL=('same_band',)
PAIR_GROUPS={key:('geometry' if key in PAIR_NUMERIC[:2] else 'recipient_load') for key in PAIR_NUMERIC}
PAIR_GROUPS['same_band']='configuration'
PAIR_GROUPS.update(event_prb_delta='configuration',event_added_cells='configuration')


def event_magnitude(event,prbs):
    if event.details.get('analysis_unit')=='episode':
        from .analysis_episodes import episode_magnitude
        return episode_magnitude(event,prbs)
    keys=event.details.get('cell_ids',[])
    bandwidth=event.event_type in ('BANDWIDTH_UPGRADE','BANDWIDTH_DOWNGRADE')
    old,new=event.previous_bandwidth_mhz,event.new_bandwidth_mhz
    if bandwidth:
        delta=5*(new-old) if old is not None and new is not None else None
    else:
        values=[prbs.get((key,event.effective_date)) for key in keys]
        delta=sum(values) if values and all(v is not None for v in values) else None
    return {'event_prb_delta':delta,'event_added_cells':0 if bandwidth else len(keys) if keys else None}


def event_bands(event,by_cell):
    return set(event.details.get('bands') or [by_cell[key]['band'] for key in event.details.get('cell_ids',[])
        if key in by_cell and by_cell[key]['band']])


def relative_bearing(bearing,azimuths):
    values=[abs((bearing-float(a)+180)%360-180) for a in azimuths if a is not None and math.isfinite(float(a))]
    return min(values) if values else None


def prior_value(rows,cutoff,key):
    values=[normalize_monthly_totals(rows.get(_month_at_offset(cutoff,k),{})).get(key) for k in (-3,-2,-1)]
    observed=[v for v in values if v is not None and math.isfinite(v)]
    return (median(observed) if len(observed)==3 else None),len(observed)


def export_pair_cases(path,progress=print,analysis_unit='event'):
    """One row per event/recipient; all eligible tiers, not virtual sample expansion."""
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    working=path.with_suffix('.tmp')
    cache={};groups,by_raw=inventory(cache);by_site=_month_rows()
    latest=MAOSMonthlyKPI.objects.aggregate(value=Max('month_date'))['value']
    if latest is None:
        raise ValueError('No monthly KPI data')
    first={r['cell_id']:r['first'] for r in MAOSMonthlyKPI.objects.filter(thrp_bits_dl__gt=0)
           .values('cell_id').annotate(first=Min('month_date'))}
    cells=list(Cell.objects.values('id','cell_id','site__site_id','band','azimuth','technology'))
    by_cell={c['cell_id']:c for c in cells};site_cells=defaultdict(list)
    for cell in cells:
        site_cells[by_raw.get(cell['site__site_id'],cell['site__site_id'])].append(cell)
    events=list(RadioNetworkEvent.objects.filter(is_current=True,effective_date__lte=latest).select_related('site').order_by('effective_date','event_key'))
    if analysis_unit=='episode':
        from .analysis_episodes import as_event
        from core.models import AnalysisEpisode
        events=[as_event(e) for e in AnalysisEpisode.objects.filter(is_current=True,effective_date__lte=latest).select_related('site').order_by('effective_date','episode_key')]
    needed={(key,e.effective_date) for e in events for key in e.details.get('cell_ids',[])}
    prbs={(key,month):value for key,month,value in MAOSMonthlyKPI.objects.values_list('cell__cell_id','month_date','prb_dl_available').iterator(chunk_size=10000) if (key,month) in needed}
    count=0;event_count=0;by_type=defaultdict(int);cutoffs={};digest=hashlib.sha256()
    with working.open('w',encoding='utf-8') as stream:
        for event in events:
            cutoff=event.effective_date;origin=event.site
            cache_key=(origin.site_id,cutoff)
            if cache_key not in cutoffs:
                cutoffs[cache_key]=neighborhood(origin,cutoff,cache)
            context=cutoffs[cache_key]
            members=context['scopes']['tier1']+context['scopes']['tier2']
            virtual={m['site_id'] for m in context['vis_members']}
            bands_for_event=event_bands(event,by_cell)
            azimuths=[by_cell[key]['azimuth'] for key in event.details.get('cell_ids',[]) if key in by_cell]
            for member in members:
                key=member['site_id'];history=by_site.get(key,{})
                bands={c['band'] for c in site_cells[key] if c['band'] and c['id'] in first and first[c['id']]<cutoff}
                loads={};support={}
                for name,metric in [('recipient_pre_dl_gb','thrp_dl_gb'),('recipient_pre_active_users','active_users_avg'),
                                    ('recipient_pre_prb_util_pct','prb_util_dl_pct'),('recipient_pre_cqi','cqi_avg')]:
                    loads[name],support[name]=prior_value(history,cutoff,metric)
                outcomes={};outcome_months={}
                for metric,raw in OUTPUT_FIELDS.items():
                    baseline,n=prior_value(history,cutoff,raw)
                    outcomes[metric]={}
                    for k in range(1,7):
                        month=_month_at_offset(cutoff,k)
                        if month>latest:
                            continue
                        observed=_row_value(history.get(month),metric)
                        outcomes[metric][str(k)]=observed-baseline if observed is not None and baseline is not None else None
                        outcome_months[str(k)]=month.isoformat()
                row={'analysis_unit':analysis_unit,'action_signature':event.details.get('action_signature'),
                    'raw_event_keys':event.details.get('raw_event_keys',[event.event_key]),'event_key':event.event_key,'event_site_id':context['canonical_site_id'],
                    'recipient_site_id':key,'event_date':cutoff.isoformat(),'event_type':event.event_type,
                    'tier_scheme':context['tier_scheme'],'technology':'/'.join(sorted(event.details.get('technologies',[]))) or None,
                    'bands':sorted(bands_for_event),'tier':member['tier'],'distance_band':member['distance_band'],
                    'virtual_sample_member':key in virtual,'distance_m':member['distance_m'],
                    'bearing_deg':member['bearing_deg'],'relative_bearing_deg':relative_bearing(member['bearing_deg'],azimuths),
                    'same_band':bool(bands_for_event & bands) if bands_for_event and bands else None,
                    **loads,**event_magnitude(event,prbs),'baseline_support':support,'outcomes':outcomes,'outcome_months':outcome_months,
                    'member_recent_launch':member['member_recent_launch']}
                line=json.dumps(row,allow_nan=False,separators=(',',':'))+'\n'
                stream.write(line);digest.update(line.encode());count+=1;by_type[event.event_type]+=1
            event_count+=1
            if event_count%100==0:
                progress(f'Exported {event_count} events / {count} recipient cases')
    # Hash actual bytes, including the platform's line endings.
    digest=hashlib.sha256()
    with working.open('rb') as source:
        for chunk in iter(lambda:source.read(1024*1024),b''):
            digest.update(chunk)
    summary={'version':'pair-episodes-v1' if analysis_unit=='episode' else 'pair-cases-v2','analysis_unit':analysis_unit,'events':event_count,'pairs':count,'pairs_by_type':dict(by_type),
        'latest_complete_month':latest.isoformat(),'sha256':digest.hexdigest(),
        'baseline':'Three complete months required per input/target KPI; missing stays NULL',
        'target':'Observed recipient KPI minus three-month median, offsets +1..+6; observational, not causal',
        'selection':'All eligible physical T1/T2 members; virtual_sample_member indicates the separate one-per-bin sample',
        'same_band':'Event bands overlap recipient cell bands with positive traffic before cutoff; unknown remains NULL',
        'relative_bearing':'Minimum absolute circular angle to an affected cell plan azimuth (0..180); NULL if unknown'}
    working.replace(path)
    path.with_suffix('.manifest.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    return summary
