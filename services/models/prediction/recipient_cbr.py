"""Selectable live recipient CBR, matched-control adjustment and local/ramp variants."""
from datetime import date
import json
from pathlib import Path
from django.conf import settings
import numpy as np
from core.models import Site
from services.models.features.neighborhood import offset,labels
from services.models.preprocessing.network_events import primary_event
from .recipient_data import data_context,load_training,policy
from .matched_controls import MatchedControls,complete
from .pair_validation import PairRanker,DEFAULT
from .recipient_uncertainty import weighted_estimate,smooth_curve,prediction_radius
from .cbr_impact import METRICS,_row_value,_aggregate_metric
from .recipient_reference import pair_reference
from services.models.similarity.calibration import fit_ranges
from .pair_cases import PAIR_NUMERIC
from .accuracy_audit import baseline_forecasts,comparison_metrics
from .action_context import other_site_actions

METHODS={'pair_cbr':'Recipient Gaussian CBR','control_adjusted':'Matched-control adjusted CBR',
    'local_linear':'Recipient CBR + local ridge','did_local_linear':'Control-adjusted CBR + local ridge'}
SCOPES=('tier1','tier2','cluster','virtual_cluster','distance_0_2','distance_2_5','distance_5_10')


def forecast(site,event,metric='downlink_traffic_gb',scope='tier1',method='pair_cbr',ramp=False,
             data=None,training=None,bootstrap_draws=None,recipient_disjoint=False,recipient_ids=None,models_override=None,profile_settings=None,profile_metadata=None):
    data=data or data_context();p=policy();cutoff=event.effective_date
    event_details=getattr(event,'details',{})
    analysis_unit=event_details.get('analysis_unit','event')
    context,queries=data.query_pairs(site,event,scope)
    if recipient_ids is not None:
        queries=[q for q in queries if q['recipient_site_id'] in recipient_ids]
    adjusted=method in ('control_adjusted','did_local_linear');local=method in ('local_linear','did_local_linear')
    controls=MatchedControls(data)
    query_head={'analysis_unit':analysis_unit,'raw_event_keys':event_details.get('raw_event_keys',[event.event_key]),
        'action_signature':event_details.get('action_signature'),'event_key':event.event_key,'event_date':cutoff.isoformat(),'event_site_id':context['canonical_site_id'],
        'event_type':event.event_type,'tier_scheme':context['tier_scheme']}
    if models_override is not None:
        source=[]
    elif queries:
        source=training if training is not None else load_training(queries[0],metric)
    else:
        source=[]
    source=[r for r in source if r['event_date']<cutoff.isoformat() and r['event_site_id']!=query_head['event_site_id']]
    if hasattr(data,'active_event_keys'):
        source=[r for r in source if r['event_key'] in (data.active_episode_keys if analysis_unit=='episode' else data.active_event_keys)]
    if recipient_disjoint:
        held={q['recipient_site_id'] for q in queries}|{query_head['event_site_id']}
        source=[r for r in source if r['recipient_site_id'] not in held and r['event_site_id'] not in held]
    ranges,reference=({}, {'kind':'explicit_training_fold_reference'}) if models_override is not None else pair_reference(cutoff.isoformat(),analysis_unit=analysis_unit) if training is None else (fit_ranges(source,PAIR_NUMERIC),{'kind':'explicit_training_fold_reference'})
    models=models_override or training_models(source,cutoff.isoformat(),query_head['event_site_id'],metric,ranges)
    rank_config={**DEFAULT,**({'selected_features':profile_settings['prediction_features'],'weighting_mode':profile_settings['weighting_mode'],'minimum_available_weight_share':profile_settings['minimum_available_weight_share'],'allow_filter_relaxation':profile_settings['allow_filter_relaxation']} if profile_settings else {})}
    predictions=[];draw_count=bootstrap_draws or p['bootstrap_draws']
    for query in queries:
        key=query['recipient_site_id'];history=data.history.get(key,{})
        pre=data.values(key,cutoff,metric,3)
        baseline=float(np.mean(pre) if adjusted else np.median(pre)) if complete(pre) else None
        match=controls.select(key,cutoff,metric) if adjusted else None
        seed=event.event_key+':'+metric+':'+method # common event draw counts across recipients/horizons
        estimates=[];draws=[];supports=[];growths=[]
        for h,model in models.items():
            chosen=[];target=[];distances=[];coverage=[]
            reason=None
            if baseline is None:
                reason='three_complete_baseline_months_required'
            elif query['distance_m']>(10000 if context['tier_scheme']=='extended' else 5000):
                reason='recipient_outside_training_radius'
            elif adjusted and match['status']!='available':
                reason=match['reason']
            else:
                ids,distance,share=model.neighbors(query,rank_config,max_per_event=3,limit=60 if adjusted else 20)
                for index,d,s in zip(ids,distance,share):
                    row=model.rows[index]
                    if recipient_disjoint and row['recipient_site_id']==key:
                        continue
                    if adjusted:
                        value,_=controls.effect(row['recipient_site_id'],date.fromisoformat(row['event_date']),metric,h)
                    else:
                        value=row['outcomes'][metric][str(h)]
                    if value is not None:
                        chosen.append(row);target.append(value);distances.append(d);coverage.append(s)
                    if len(chosen)==20:
                        break
            if reason:
                estimate=sample=None;support={'reason':reason,'n_pairs':0,'n_events':0,'effective_event_n':None}
            else:
                estimate,sample,support=weighted_estimate(chosen,target,distances,query,seed,local,draw_count,selected_features=profile_settings['prediction_features'] if profile_settings else None)
                support['available_weight_share_min']=float(min(coverage)) if coverage else None
                support['analog_events']=sorted({r['event_key'] for r in chosen})
            estimates.append(estimate);draws.append(sample);supports.append(support)
            growths.append(controls.forecast_growth(match,h) if adjusted else 0.)
        applied=False
        if ramp:
            estimates,draws,applied=smooth_curve(estimates,draws,[r.get('effective_event_n') or 0 for r in supports])
        points=[];bounded_draws=[]
        ceiling=15 if metric=='cqi_avg' else float('inf')
        bound=lambda value:float(min(ceiling,max(0.,value)))
        for h in range(1,7):
            estimate=estimates[h-1];support=supports[h-1];growth=growths[h-1]
            value=bound(baseline+growth+estimate) if baseline is not None and estimate is not None and growth is not None else None
            sample=draws[h-1]
            levels=np.clip(baseline+growth+sample,0,ceiling) if value is not None and sample is not None else np.full(draw_count,np.nan)
            bounded_draws.append(levels)
            valid=levels[np.isfinite(levels)]
            ci=list(map(float,np.percentile(valid,[2.5,97.5]))) if len(valid)>=.8*draw_count else None
            radius,calibration=prediction_radius(query,metric,h,method,applied) if value is not None and not profile_settings and analysis_unit!='episode' else (None,{'status':'unavailable','reason':'episode_specific_calibration_required' if analysis_unit=='episode' else 'profile_specific_calibration_required' if profile_settings else support['reason']})
            pi=[bound(value-radius),bound(value+radius)] if radius is not None else None
            observed=_row_value(history.get(offset(cutoff,h)),metric)
            benchmarks=baseline_forecasts(history,cutoff,metric,h)
            points.append({'horizon':h,'month':offset(cutoff,h).isoformat(),'observed':observed,
                'last_month_forecast':benchmarks['last_month'],'baseline_forecasts':benchmarks,
                'accuracy':comparison_metrics(observed,value,benchmarks['last_month']),
                'observed_change':observed-baseline if observed is not None and baseline is not None else None,
                'baseline':baseline,'predicted':value,'predicted_change':value-baseline if value is not None else None,
                'control_adjusted_effect':estimate if adjusted else None,'forecast_control_change':growth if adjusted else None,
                'mean_interval_95':ci,'prediction_interval_95':pi,'calibration':calibration,'support':support,
                'ramp_applied':applied,'_draws':levels})
        predictions.append({'site_id':key,'site_name':query['site_name'],'distance_m':query['distance_m'],'tier':query['tier'],
            'baseline':baseline,'baseline_months':sum(v is not None for v in pre),'controls':match,'points':points})
    aggregate=[]
    denominators={'cqi_avg':'cqi_sample_count','dl_throughput_kbps':'dl_time_ms','dl_packet_delay_ms':'delay_packets'}
    aggregate_weights=[]
    for recipient in predictions:
        denominator=denominators.get(metric)
        values=[data.history.get(recipient['site_id'],{}).get(offset(cutoff,k),{}).get(denominator) for k in (-3,-2,-1)] if denominator else [1.,1.,1.]
        aggregate_weights.append(float(np.mean(values)) if complete(values) and np.mean(values)>0 else None)
    for h in range(6):
        values=[r['points'][h]['predicted'] for r in predictions]
        actuals=[r['points'][h]['observed'] for r in predictions]
        def total(values):
            if not values or any(v is None for v in values):
                return None
            if METRICS[metric]['kind']=='sum':
                return float(sum(values))
            return float(np.average(values,weights=aggregate_weights)) if all(w is not None for w in aggregate_weights) else None
        valid=bool(predictions) and all(v is not None for v in values) and (METRICS[metric]['kind']=='sum' or all(w is not None for w in aggregate_weights))
        samples=np.array([r['points'][h]['_draws'] for r in predictions]) if valid else None
        if samples is not None:
            combined=samples.sum(axis=0) if METRICS[metric]['kind']=='sum' else np.average(samples,axis=0,weights=aggregate_weights)
            finite=combined[np.isfinite(combined)]
            interval=list(map(float,np.percentile(finite,[2.5,97.5]))) if len(finite)>=.8*draw_count else None
        else:
            interval=None
        actual=_aggregate_metric([r['site_id'] for r in predictions],offset(cutoff,h+1),data.history,metric) if actuals and all(v is not None for v in actuals) else None
        prior=[r['points'][h]['last_month_forecast'] for r in predictions]
        benchmark=_aggregate_metric([r['site_id'] for r in predictions],offset(cutoff,-1),data.history,metric) if prior and all(v is not None for v in prior) else None
        scope_baseline=total([r['baseline'] for r in predictions])
        aggregate.append({'horizon':h+1,'month':offset(cutoff,h+1).isoformat(),'predicted':total(values),'observed':actual,
            'last_month_forecast':benchmark,'accuracy':comparison_metrics(actual,total(values),benchmark),
            'baseline':scope_baseline,'observed_change':actual-scope_baseline if actual is not None and scope_baseline is not None else None,
            'predicted_change':total(values)-scope_baseline if total(values) is not None and scope_baseline is not None else None,
            'mean_interval_95':interval,'prediction_interval_95':None,'prediction_interval_reason':'no_scope_total_calibration',
            'supported_recipients':sum(v is not None for v in values),'eligible_recipients':len(values)})
    for row in predictions:
        for point in row['points']:
            del point['_draws']
    manifest=Path(settings.BASE_DIR)/'data/calibration'/('episode_recipient_cases.manifest.json' if analysis_unit=='episode' else 'event_recipient_cases.manifest.json')
    snapshot=json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else None
    actions=other_site_actions([e for e in data.events if getattr(e,'event_key',None) not in event_details.get('raw_event_keys',[])],context['canonical_site_id'],event.event_key,cutoff)
    audit_path=Path(settings.BASE_DIR)/'data/calibration/recipient_accuracy.json'
    audit=json.loads(audit_path.read_text(encoding='utf-8')) if audit_path.exists() else None
    validation=[{'horizon':r['horizon'],'n_pairs':r['cbr']['n_pairs'],'cbr_mae':r['cbr']['mae'],
        'last_month_mae':r['comparison']['mae'],'skill':r['cbr_skill_mae']} for r in audit['comparisons']
        if r['metric']==metric and r['baseline']=='last_month'] if audit and snapshot and audit['dataset_sha256']==snapshot['sha256'] and audit['model_version']==p['version'] and not profile_settings and analysis_unit=='event' else []
    return {'analysis_profile':profile_metadata,'scoring_settings':rank_config,'model_version':p['version'],'reference':reference,'training_snapshot':snapshot,'query':query_head,'method':method,'method_label':METHODS[method],
        'metric':metric,'metric_definition':METRICS[metric],'scope':scope,'scope_label':labels(context['tier_scheme']).get(scope,scope),
        'other_site_actions':actions,'validation_benchmark':validation,
        'diagnostic_note':'Action context and observed errors are retrospective display diagnostics; they never change forecast inputs. Validation comparisons describe the unsmoothed Gaussian recipient model across sampled event types/schemes, not site-specific confidence.',
        'baseline_kind':'mean of three complete pre-event months' if adjusted else 'median of three complete pre-event months',
        'ramp_requested':ramp,'recipients':predictions,'scope_series':aggregate,
        'bootstrap_draws':draw_count,'interval_note':f'Mean intervals resample physical event-origin blocks, keeping all their actions and recipients together ({draw_count} Poisson bootstrap draws). They condition on selected neighbors/matches and fixed baselines. They are not prediction intervals.',
        'control_note':'Control growth at the query is extrapolated from six pre-event months; no future control outcomes enter a forecast. Historical matched effects censor subsequent exposures. Parallel trends are not established by matching alone.',
        'aggregation_note':'Traffic/users sum complete recipient predictions. Observed ratios pool source counters; forecast ratios use fixed mean pre-event denominators as exposure weights because future denominators are unknown. Incomplete totals stay NULL. Virtual scope is sampled traffic only.',
        'status':'available' if any(p['predicted'] is not None for r in predictions for p in r['points']) else 'insufficient_support'}


def recipient_request(params,actor=None):
    site_id=params.get('site_id','').strip();metric=params.get('metric','downlink_traffic_gb')
    method=params.get('method','pair_cbr');scope=params.get('scope','tier1');ramp=params.get('ramp','false')
    if not site_id or metric not in METRICS or not METRICS.get(metric,{}).get('available') or method not in METHODS or scope not in SCOPES or ramp not in ('true','false'):
        return {'error':'Provide site_id, supported metric/method/scope, and ramp=true or false.'},400
    if scope=='virtual_cluster' and metric!='downlink_traffic_gb':
        return {'error':'Virtual-cluster predictions expose sampled traffic only.'},400
    site=Site.objects.filter(site_id=site_id).prefetch_related('network_events').first()
    if site is None:
        return {'error':'Site not found.'},404
    unit=params.get('analysis_unit','event')
    if unit not in ('event','episode'):
        return {'error':'analysis_unit must be event or episode.'},400
    if unit=='episode':
        from .analysis_episodes import as_event,site_episodes
        available_events=[as_event(e) for e in site_episodes(site)]
    else:
        available_events=[e for e in site.network_events.all() if e.is_current]
    if params.get('metadata')=='true':
        raw=primary_event(site)
        chosen=next((e for e in available_events if raw and (raw.event_key==e.event_key or raw.event_key in e.details.get('raw_event_keys',[]))),None)
        return {'events':[{'event_key':e.event_key,'date':e.effective_date.isoformat(),'label':e.details.get('label',e.event_type),'analysis_profile':event_profile(actor,params,site,e)[1],
            'raw_event_keys':e.details.get('raw_event_keys',[e.event_key]),'actions':e.details.get('actions',[])}
            for e in available_events],
            'analysis_unit':unit,
            'default_event_key':chosen.event_key if chosen else None,'cluster_id':site.cluster_id,
            'scope_labels':labels('extended' if site.cluster_id==-1 else 'standard')},200
    event_key=params.get('event_key');event=next((e for e in available_events if e.event_key==event_key or event_key in e.details.get('raw_event_keys',[])),None) if event_key else min(available_events,key=lambda e:(e.effective_date,e.event_key),default=None)
    if event is None:
        return {'error':'Select a recorded event belonging to this site; an undated scenario has no event-recipient profile.'},422
    from services.analysis_profiles import resolve_profile
    profile_settings,profile_metadata,error=resolve_profile(actor,'prediction',params,{
        'event_type':event.event_type,'tier_scheme':'extended' if site.cluster_id==-1 else 'standard',
        'technology':'/'.join(event.details.get('technologies',[]))})
    if error:
        return error
    if params.get('features') is not None or params.get('weighting_mode') is not None:
        from services.analysis_profiles import defaults,validate_settings
        changed={**(profile_settings or defaults())}
        if 'features' in params:
            changed['prediction_features']=params['features'].split(',')
        if 'weighting_mode' in params:
            changed['weighting_mode']=params['weighting_mode']
        try:
            profile_settings=validate_settings(changed)
        except ValueError as error:
            return {'error':str(error)},400
    if profile_settings:
        method=params.get('method',profile_settings['prediction_method'])
        scope=params.get('scope',profile_settings['scope'])
        ramp=params.get('ramp',str(profile_settings['ramp']).lower())
    if scope=='virtual_cluster' and metric!='downlink_traffic_gb':
        return {'error':'Virtual-cluster predictions expose sampled traffic only.'},400
    if scope=='cluster' and site.cluster_id==-1 or scope=='virtual_cluster' and site.cluster_id!=-1:
        return {'error':'This scope is unavailable for the selected tier scheme.'},400
    return forecast(site,event,metric,scope,method,ramp=='true',profile_settings=profile_settings,profile_metadata=profile_metadata),200


def training_models(source,cutoff,origin,metric,ranges):
    return {h:PairRanker([r for r in source if r['event_date']<cutoff and r['event_site_id']!=origin
        and r.get('outcome_months',{}).get(str(h),'9999')<cutoff
        and r.get('outcomes',{}).get(metric,{}).get(str(h)) is not None],metric,h,feature_ranges=ranges)
        for h in range(1,7)}


def event_profile(actor,params,site,event):
    from services.analysis_profiles import resolve_profile
    return resolve_profile(actor,'prediction',params,{'event_type':event.event_type,
        'tier_scheme':'extended' if site.cluster_id==-1 else 'standard',
        'technology':'/'.join(event.details.get('technologies',[]))})
