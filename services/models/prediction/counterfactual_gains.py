"""Episode-level, matched-control counterfactual scenarios and signed gains.

No future query/control observations are forecasting inputs. These are modelled
observational scenarios, not identified causal effects or calibrated intervals.
"""
from pathlib import Path
from collections import Counter
import json
import numpy as np
from django.conf import settings
from core.models import Site
from services.analysis_profiles import resolve_profile,validate_settings
from .analysis_episodes import as_event,site_episodes
from .recipient_data import data_context,load_training
from .recipient_reference import pair_reference
from .recipient_cbr import forecast

VERSION='counterfactual-gain-v1'
SCOPES={'origin':'Event site only','tier1':'Tier 1 neighbors','tier2':'Tier 2 neighbors',
    'network':'Event site + Tier 1 + Tier 2','cluster_total':'Real DBSCAN cluster including event site',
    'virtual_cluster':'Virtual cluster sampled neighbors','distance_0_2':'Neighbors 0-2 km',
    'distance_2_5':'Neighbors 2-5 km','distance_5_10':'Neighbors 5-10 km'}
METRICS=('downlink_traffic_gb','active_users')


def artifacts():
    base=Path(settings.BASE_DIR)/'data/calibration'
    return base/'gain_recipient_cases.jsonl',base/'gain_reference.json'


def mean_interval(draws):
    valid=np.asarray(draws)[np.isfinite(draws)]
    return list(map(float,np.percentile(valid,[2.5,97.5]))) if len(valid)>=.8*len(draws) and len(draws) else None


def add_gain_series(points,draws,backgrounds,horizon):
    """Never fill a missing month or sum independent confidence bounds."""
    cumulative=0.;cumulative_draws=None;complete=True
    for i,point in enumerate(points):
        background=backgrounds[i]
        with_event=point.get('predicted')
        gain=with_event-background if with_event is not None and background is not None else None
        sample=np.asarray(draws[i],dtype=float)-background if background is not None else np.full(len(draws[i]),np.nan)
        if gain is None:
            complete=False
        if complete:
            cumulative+=gain
            cumulative_draws=sample.copy() if cumulative_draws is None else cumulative_draws+sample
        point.update(no_event_forecast=background,with_event_forecast=with_event,monthly_gain=gain,
            gain_mean_interval_95=mean_interval(sample) if gain is not None else None,
            cumulative_gain=cumulative if complete else None,
            cumulative_gain_mean_interval_95=mean_interval(cumulative_draws) if complete else None,
            observed_difference_from_no_event=point['observed']-background if point.get('observed') is not None and background is not None else None)
    selected=points[:horizon]
    last=selected[-1] if selected else {}
    return {'horizon_months':horizon,'supported_months':sum(p['monthly_gain'] is not None for p in selected),
        'gain':last.get('cumulative_gain'),'mean_interval_95':last.get('cumulative_gain_mean_interval_95'),
        'status':'available' if len(selected)==horizon and all(p['monthly_gain'] is not None for p in selected) else 'incomplete_monthly_support'}


def gain_forecast(site,event,scope='tier1',metric='downlink_traffic_gb',horizon=6,ramp=False,
                  profile_settings=None,profile_metadata=None,data=None,training=None,reference=None,bootstrap_draws=None,
                  recipient_ids=None,recipient_disjoint=False):
    data=data or data_context()
    source_path,reference_path=artifacts()
    context,queries=data.query_pairs(site,event,scope)
    if training is None:
        training=load_training(queries[0],metric,path=source_path) if queries else []
    if reference is None:
        reference=pair_reference(event.effective_date.isoformat(),'episode',source_path=source_path,reference_path=reference_path)
    choices=validate_settings(profile_settings or {})
    method='did_local_linear' if choices['prediction_method'] in ('local_linear','did_local_linear') else 'control_adjusted'
    result=forecast(site,event,metric,scope,method,ramp,data=data,training=training,bootstrap_draws=bootstrap_draws,
        profile_settings=choices,profile_metadata=profile_metadata,training_reference=reference,retain_draws=True,
        recipient_ids=recipient_ids,recipient_disjoint=recipient_disjoint)
    result.update(model_version=VERSION,scope_label=SCOPES[scope],analysis_profile=profile_metadata,
        estimator='Matched-control adjusted episode CBR; origin and neighbor cases never match each other',
        no_event_definition='Recipient mean of three complete pre-event months plus the matched controls\' pre-event-only six-month linear growth extrapolation. No future query/control values enter this forecast.',
        gain_definition='With-event forecast minus no-event forecast after bounding both levels at zero; losses stay negative.',
        attribution_note='Modelled observational scenarios. Matching does not establish parallel trends or causality. Later actions can contaminate displayed observations; gains are not measured causal effects.',
        uncertainty_note='Conditional mean intervals from shared physical-origin bootstrap draws across recipients and months, with matches and background fixed. Background/model-selection uncertainty is not included; no individual prediction intervals.',
        cumulative_unit='GB' if metric=='downlink_traffic_gb' else 'active-user-months (summed monthly average counts, not unique users)',
        scope_note='Fixed event-cutoff physical-site cohort, summed once per site. Origin is included only in Event site, Local network and Real cluster total scopes. Virtual neighborhoods remain sampled neighbors and cluster_id=-1.',
        interval_note='Gain intervals describe conditional analog-mean uncertainty, not calibrated prediction coverage.',validation_benchmark=[])
    background_by_site=[];gain_draws_by_site=[]
    for recipient in result['recipients']:
        backgrounds=[];draws=[]
        for point in recipient['points']:
            growth=point.get('forecast_control_change');base=point.get('baseline')
            background=max(0.,base+growth) if base is not None and growth is not None else None
            backgrounds.append(background)
            samples=point.pop('_draws')
            draws.append(samples)
            point['prediction_interval_95']=None
            point['calibration']={'status':'unavailable','reason':'counterfactual_gain_requires_separate_calibration'}
        recipient['recipient_role']='origin' if recipient['site_id']==context['canonical_site_id'] else 'neighbor'
        recipient['cumulative']=add_gain_series(recipient['points'],draws,backgrounds,horizon)
        background_by_site.append(backgrounds)
        gain_draws_by_site.append(draws)
    scope_backgrounds=[];scope_draws=[]
    draw_count=result['bootstrap_draws']
    for i in range(6):
        levels=[v[i] for v in background_by_site]
        scope_backgrounds.append(float(sum(levels)) if levels and all(v is not None for v in levels) else None)
        scope_draws.append(np.sum([d[i] for d in gain_draws_by_site],axis=0) if gain_draws_by_site else np.full(draw_count,np.nan))
    result['cumulative']=add_gain_series(result['scope_series'],scope_draws,scope_backgrounds,horizon)
    for i,point in enumerate(result['scope_series']):
        point['prediction_interval_95']=None
        missing=Counter(r['points'][i]['support'].get('reason') or 'missing_background_or_prediction'
            for r in result['recipients'] if r['points'][i]['monthly_gain'] is None)
        point['missing_member_reasons']=dict(missing)
        if missing:
            point['support']={'reason':'; '.join(f'{reason} ({count} member(s))' for reason,count in sorted(missing.items()))}
        point['confounding_actions']=[a for a in result['other_site_actions'] if a['date']<=point['month']]
    result['status']='available' if any(p['monthly_gain'] is not None for p in result['scope_series']) else 'insufficient_complete_scope_support'
    manifest=source_path.with_suffix('.manifest.json')
    result['training_snapshot']=json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else None
    return result


def gain_request(params,actor=None):
    site=Site.objects.filter(site_id=params.get('site_id','')).prefetch_related('network_events').first()
    if site is None:
        return {'error':'Select an existing event site.'},404
    episodes=list(site_episodes(site))
    if params.get('metadata')=='true':
        return {'events':[{'event_key':e.episode_key,'date':e.effective_date.isoformat(),'label':e.details['label'],
            'analysis_profile':resolve_profile(actor,'prediction',params,{'event_type':e.event_type,
                'tier_scheme':'extended' if site.cluster_id==-1 else 'standard',
                'technology':'/'.join(e.details.get('technologies',[]))})[1]} for e in episodes],
            'default_event_key':episodes[0].episode_key if episodes else None,'scopes':SCOPES,'cluster_id':site.cluster_id},200
    key=params.get('event_key')
    episode=next((e for e in episodes if key==e.episode_key or key in e.details['raw_event_keys']),None) if key else next(iter(episodes),None)
    if episode is None:
        return {'error':'Select a current episode belonging to this physical site.'},422
    event=as_event(episode)
    choices,metadata,error=resolve_profile(actor,'prediction',params,{'event_type':event.event_type,
        'tier_scheme':'extended' if site.cluster_id==-1 else 'standard','technology':'/'.join(event.details.get('technologies',[]))})
    if error:
        return error
    changes=dict(choices or {})
    if 'features' in params:
        changes['prediction_features']=params['features'].split(',')
    if 'weighting_mode' in params:
        changes['weighting_mode']=params['weighting_mode']
    try:
        choices=validate_settings(changes)
        horizon=int(params.get('horizon',6))
        if not 1<=horizon<=6:
            raise ValueError('Horizon must be 1 to 6 complete months after the event.')
    except (ValueError,TypeError) as error:
        return {'error':str(error)},400
    scope=params.get('scope',choices['scope']);scope='cluster_total' if scope=='cluster' else scope
    metric=params.get('metric','downlink_traffic_gb');ramp=params.get('ramp',str(choices['ramp']).lower())
    if scope not in SCOPES or metric not in METRICS or ramp not in ('true','false'):
        return {'error':'Choose a supported scope, additive traffic/users metric, and ramp=true or false.'},400
    if scope=='cluster_total' and site.cluster_id==-1 or scope=='virtual_cluster' and (site.cluster_id!=-1 or metric!='downlink_traffic_gb'):
        return {'error':'Noise sites have no real cluster; virtual samples support traffic only.'},400
    source,reference=artifacts()
    if not source.exists() or not reference.exists():
        return {'error':'Gain cases/reference are unavailable. Run build_gain_cases.'},503
    return gain_forecast(episode.site,event,scope,metric,horizon,ramp=='true',choices,metadata),200
