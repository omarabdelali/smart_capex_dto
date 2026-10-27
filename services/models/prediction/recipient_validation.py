"""Rolling event-origin validation, recipient-disjoint sensitivity and control audit."""
from collections import defaultdict,Counter
import json
from pathlib import Path
import sys
from django.conf import settings
from services.models.features.neighborhood import offset
from services.models.similarity.calibration import fit_ranges
from .pair_cases import PAIR_NUMERIC
from .pair_validation import sample_cases,errors
from .recipient_cbr import forecast,training_models
from .recipient_data import data_context,policy
from .matched_controls import MatchedControls


def metric_pool(path,metric):
    fields=PAIR_NUMERIC+('same_band','event_key','event_site_id','recipient_site_id','event_date','event_type','tier_scheme','technology','bands','outcome_months')
    pools=defaultdict(list)
    with Path(path).open(encoding='utf-8') as source:
        for line in source:
            original=json.loads(line)
            row={f:original.get(f) for f in fields}
            for f in ('event_key','event_site_id','recipient_site_id','event_date','event_type','tier_scheme'):
                row[f]=sys.intern(row[f])
            row['outcomes']={metric:{str(h):original.get('outcomes',{}).get(metric,{}).get(str(h)) for h in range(1,7)}}
            pools[row['event_type'],row['tier_scheme']].append(row)
    return pools


def validate_recipients(output,events_per_type=24,recipients_per_event=1,progress=print):
    p=policy();base=Path(settings.BASE_DIR)/'data/calibration';source=base/'event_recipient_cases.jsonl'
    sampled=sample_cases(source,events_per_type,recipients_per_event);data=data_context();controls=MatchedControls(data)
    by_event=defaultdict(set)
    for row in sampled:
        by_event[row['event_key']].add(row['recipient_site_id'])
    events={e.event_key:e for e in data.events};scores=defaultdict(list);eligible=Counter();calibration=[];sensitivity=[]
    specs=[('pair_cbr',False,False),('pair_cbr',True,False),('control_adjusted',False,False),
        ('control_adjusted',True,False),('local_linear',False,False),('did_local_linear',False,False),('pair_cbr',False,True)]
    metrics=('downlink_traffic_gb','active_users','cqi_avg','dl_throughput_kbps','dl_packet_delay_ms')
    held_origins=defaultdict(set);held_recipients=defaultdict(set)
    for key,recipients in by_event.items():
        e=events[key];month=e.effective_date.isoformat()
        held_origins[month].add(e.site.canonical_site_id or e.site.site_id)
        held_recipients[month].update(recipients)
    for metric in metrics:
        pools=metric_pool(source,metric);range_cache={};model_cache={}
        for number,(event_key,recipients) in enumerate(by_event.items(),1):
            event=events[event_key];site=event.site;cutoff=event.effective_date.isoformat()
            scheme='extended' if site.cluster_id==-1 else 'standard'
            def fold(disjoint=False):
                cache_key=(cutoff,event.event_type,scheme,disjoint)
                if cache_key not in model_cache:
                    held=held_origins[cutoff]|(held_recipients[cutoff] if disjoint else set())
                    prior=lambda r:r['event_date']<cutoff and r['event_site_id'] not in held and (not disjoint or r['recipient_site_id'] not in held)
                    if (cutoff,disjoint) not in range_cache:
                        reference=[r for values in pools.values() for r in values if prior(r)]
                        range_cache[cutoff,disjoint]=fit_ranges(reference,PAIR_NUMERIC)
                    pool=[r for r in pools[event.event_type,scheme] if prior(r)]
                    active=training_models(pool,cutoff,site.canonical_site_id or site.site_id,metric,range_cache[cutoff,disjoint])
                    model_cache[cache_key]=(pool,active)
                    # Bound retained training matrices while keeping the current
                    # month's fold ranges reusable across all held-out events.
                    if len(model_cache)>3:
                        del model_cache[next(iter(model_cache))]
                return model_cache[cache_key]
            pool,models=fold()
            # Split sampled recipients into the actual two tier scopes.
            queries=data.query_pairs(site,event,'tier1')[1]+data.query_pairs(site,event,'tier2')[1]
            for current_scope in ('tier1','tier2'):
                selected={q['recipient_site_id'] for q in queries if q['tier']==current_scope and q['recipient_site_id'] in recipients}
                if not selected:
                    continue
                for method,ramp,disjoint in specs:
                    clean,active_models=fold(disjoint)
                    result=forecast(site,event,metric,current_scope,method,ramp,data=data,training=clean,
                        recipient_ids=selected,recipient_disjoint=disjoint,models_override=active_models)
                    for recipient in result['recipients']:
                        for point in recipient['points']:
                            if point['observed'] is None:
                                continue
                            key=(metric,method,ramp,disjoint,point['horizon']);eligible[key]+=1
                            if point['predicted'] is not None:
                                record={'event_key':event_key,'event_site_id':site.canonical_site_id or site.site_id,
                                    'recipient_site_id':recipient['site_id'],'event_type':event.event_type,'tier_scheme':scheme,
                                    'metric':metric,'horizon':point['horizon'],'method':method,'ramp':point['ramp_applied'],
                                    'requested_ramp':ramp,
                                    'available_month':point['month'],'actual':point['observed'],'predicted':point['predicted'],
                                    'error':point['observed']-point['predicted'],'mean_interval_95':point['mean_interval_95']}
                                scores[key].append(record)
                                if not disjoint:
                                    calibration.append(record)
                for key in selected:
                    for radius in p['control_sensitivity_m']:
                        match=controls.select(key,event.effective_date,metric,radius)
                        sensitivity.append({'event_key':event_key,'recipient_site_id':key,'metric':metric,'radius_m':radius,
                            'status':match['status'],'controls':len(match['controls']),'reason':match['reason']})
            if number%10==0:
                progress(f'Validated {metric}: {number}/{len(by_event)} events')
        del pools
    summary=[]
    for key,n in eligible.items():
        records=scores[key];metric,method,ramp,disjoint,horizon=key
        intervals=[r for r in records if r['mean_interval_95'] is not None]
        summary.append({'metric':metric,'method':method,'ramp':ramp,'recipient_disjoint':disjoint,'horizon':horizon,
            **errors(records),'eligible_pairs':n,'prediction_availability':len(records)/n if n else 0.,
            'mean_interval_coverage':float(sum(r['mean_interval_95'][0]<=r['actual']<=r['mean_interval_95'][1] for r in intervals)/len(intervals)) if intervals else None,
            'mean_interval_note':'Coverage diagnostic only; a mean interval is not a prediction interval.'})
    paired=[]
    for key,records in scores.items():
        metric,method,ramp,disjoint,horizon=key
        baseline=scores[metric,'pair_cbr',False,False,horizon]
        lookup={(r['event_key'],r['recipient_site_id']):r for r in baseline}
        selected=[r for r in records if (r['event_key'],r['recipient_site_id']) in lookup]
        matching=[lookup[r['event_key'],r['recipient_site_id']] for r in selected]
        paired.append({'metric':metric,'method':method,'ramp':ramp,'recipient_disjoint':disjoint,'horizon':horizon,
            'baseline_common_support':errors(matching),'method_common_support':errors(selected)})
    manifest=json.loads(source.with_suffix('.manifest.json').read_text(encoding='utf-8'))
    artifact={'model_version':p['version'],'dataset_sha256':manifest['sha256'],'records':calibration}
    destination=Path(settings.BASE_DIR)/p['calibration_path'];destination.parent.mkdir(parents=True,exist_ok=True)
    temporary=destination.with_suffix('.tmp');temporary.write_text(json.dumps(artifact,allow_nan=False),encoding='utf-8');temporary.replace(destination)
    report={'version':p['version'],'sample_events':len(by_event),'sample_pairs':len(sampled),'events_per_type':events_per_type,
        'dataset':manifest,'validation':'Rolling event cutoffs; same event origin excluded. Separate recipient-disjoint baseline purges held sites from both event-origin and recipient roles and range fitting.',
        'bootstrap_draws':p['bootstrap_draws'],'results':summary,'paired_comparisons':paired,'control_sensitivity':sensitivity,
        'limitations':'Sampled events/recipients; exposure washout is six months. Matching is diagnostic, not proof of parallel trends. No causal or future coverage guarantee.',
        'promotion':'Gaussian recipient baseline selectable live; local/ramp/control methods remain explicitly labelled alternatives, no automatic substitution.'}
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    return report
