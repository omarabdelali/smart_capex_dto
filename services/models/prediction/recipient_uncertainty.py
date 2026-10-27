"""Event-correlated bootstrap and explicitly gated rolling prediction intervals."""
from collections import Counter
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import numpy as np
from django.conf import settings
from .recipient_data import policy
from .pair_validation import FIELDS


@lru_cache(maxsize=2)
def _artifact(path,mtime):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def event_multipliers(event_keys,seed,draws):
    """Poisson event bootstrap: an event's recipients share the same draw count."""
    result={}
    for key in set(event_keys):
        value=int(hashlib.sha256((str(seed)+':'+key).encode()).hexdigest()[:16],16)
        result[key]=np.random.default_rng(value).poisson(1,size=draws)
    return np.array([result[key] for key in event_keys],dtype=float).T


def weighted_estimate(rows,values,distances,query,seed,local=False,draws=None,selected_features=None):
    p=policy();draws=draws or p['bootstrap_draws']
    keys=[r['event_key'] for r in rows];counts=Counter(keys)
    sites=[r.get('event_site_id',r['event_key']) for r in rows]
    report={'n_pairs':len(rows),'n_events':len(counts),'n_event_sites':len(set(sites)),'effective_event_n':None,'bootstrap_draws':draws,
        'interval_kind':'conditional event-bootstrap mean interval, not an individual prediction interval'}
    if len(set(sites))<p['minimum_events']:
        return None,None,{**report,'reason':'fewer_than_three_independent_event_origins'}
    h=max(float(np.median(distances))*.5,1e-6)
    log=-.5*(np.asarray(distances)/h)**2;w=np.exp(log-log.max())
    w=np.array([v/counts[key] for v,key in zip(w,keys)]);w/=w.sum()
    ew=[sum(v for v,k in zip(w,sites) if k==key) for key in set(sites)]
    report['effective_event_n']=float(1/np.sum(np.square(ew)))
    if report['effective_event_n']<2:
        return None,None,{**report,'reason':'effective_event_support_below_two'}
    y=np.array(values,dtype=float);estimate=float(w@y)
    multipliers=event_multipliers(sites,seed,draws);weights=multipliers*w
    total=weights.sum(axis=1);valid=total>0
    samples=np.full(draws,np.nan);samples[valid]=(weights[valid]@y)/total[valid]
    if local:
        fields=[f for f in (selected_features if selected_features is not None else FIELDS) if query.get(f) is not None and np.isfinite(query[f])]
        complete=np.array([all(r.get(f) is not None and np.isfinite(r[f]) for f in fields) for r in rows])
        selected=[r for r,ok in zip(rows,complete) if ok]
        if complete.sum()<p['local_minimum_pairs'] or len({r.get('event_site_id',r['event_key']) for r in selected})<p['local_minimum_events']:
            return None,None,{**report,'reason':'insufficient_complete_local_linear_support'}
        x=np.array([[r[f] for f in fields] for r in selected],dtype=float)
        center=x.mean(axis=0);scale=x.std(axis=0);scale[scale==0]=1
        design=np.column_stack([np.ones(len(x)),(x-center)/scale])
        q=np.r_[1.,(np.array([query[f] for f in fields])-center)/scale]
        penalty=np.eye(design.shape[1])*p['local_ridge_alpha'];penalty[0,0]=0
        def ridge(weights):
            sums=weights.sum(axis=1);ok=sums>0
            norm=np.zeros_like(weights);norm[ok]=weights[ok]/sums[ok,None]
            matrix=np.einsum('ni,bn,nj->bij',design,norm,design)+penalty
            # Singular all-zero bootstrap samples have no estimate.
            matrix[~ok]+=np.eye(matrix.shape[1])
            rhs=np.einsum('ni,bn,n->bi',design,norm,y[complete])
            answer=np.linalg.solve(matrix,rhs[...,None])[...,0]@q;answer[~ok]=np.nan
            return answer
        local_point=ridge(w[complete][None,:])[0]
        local_samples=ridge(weights[:,complete]);blend=p['local_blend']
        estimate=(1-blend)*estimate+blend*local_point
        samples=(1-blend)*samples+blend*local_samples
        report['local_features']=fields
    report.update(kernel_width=h,reason=None,valid_bootstrap_draws=int(np.isfinite(samples).sum()))
    return estimate,samples,report


def smooth_curve(values,samples,support):
    """Smooth supported horizons and each correlated bootstrap curve; never fill gaps."""
    ids=[i for i,v in enumerate(values) if v is not None]
    if len(ids)<3:
        return values,samples,False
    h=(np.array(ids,dtype=float)+1)/6
    design=np.column_stack([np.ones(len(h)),h,h*h]);w=np.array([support[i] for i in ids])
    penalty=np.diag([0.,policy()['ramp_ridge_alpha'],policy()['ramp_ridge_alpha']])
    smoother=design@np.linalg.solve(design.T@(w[:,None]*design)+penalty,design.T*w)
    fitted=smoother@np.array([values[i] for i in ids]);matrix=np.column_stack([samples[i] for i in ids])
    bootstrap=matrix@smoother.T
    output=list(values);draws=list(samples)
    for j,i in enumerate(ids):
        output[i]=float(fitted[j]);draws[i]=bootstrap[:,j]
    return output,draws,True


def prediction_radius(query,metric,horizon,method,ramp):
    p=policy();path=Path(settings.BASE_DIR)/p['calibration_path']
    if not path.exists():
        return None,{'status':'unavailable','reason':'no_rolling_prediction_calibration'}
    artifact=_artifact(str(path),path.stat().st_mtime_ns)
    if artifact.get('model_version')!=p['version']:
        return None,{'status':'unavailable','reason':'calibration_model_version_mismatch'}
    manifest=Path(settings.BASE_DIR)/'data/calibration/event_recipient_cases.manifest.json'
    if not manifest.exists() or artifact.get('dataset_sha256')!=json.loads(manifest.read_text(encoding='utf-8')).get('sha256'):
        return None,{'status':'unavailable','reason':'calibration_dataset_revision_mismatch'}
    records=[r for r in artifact['records'] if r['metric']==metric and r['horizon']==horizon and r['method']==method
        and r['ramp']==ramp and r['event_type']==query['event_type'] and r['tier_scheme']==query['tier_scheme']
        and r['available_month']<query['event_date'] and r['event_site_id']!=query['event_site_id']]
    # Event maxima preserve within-event recipient dependence.
    groups={};dates={}
    for row in records:
        key=row['event_site_id']
        groups[key]=max(groups.get(key,0),abs(row['error']))
        dates[key]=max(dates.get(key,''),row['available_month'])
    if len(groups)<p['minimum_calibration_events']:
        return None,{'status':'unavailable','reason':'fewer_than_twenty_prior_calibration_events','n_events':len(groups)}
    # Check interval coverage on subsequent, already-observed event blocks.
    covered=[]
    for key,score in groups.items():
        past=sorted(v for event,v in groups.items() if dates[event]<dates[key])
        rank=int(np.ceil((len(past)+1)*.95))
        if len(past)>=p['minimum_calibration_events'] and rank<=len(past):
            covered.append(score<=past[rank-1])
    if len(covered)<10 or np.mean(covered)<p['minimum_calibration_coverage']:
        return None,{'status':'unavailable','reason':'rolling_interval_coverage_gate_not_met',
            'validation_events':len(covered),'empirical_coverage':float(np.mean(covered)) if covered else None}
    scores=sorted(groups.values());rank=int(np.ceil((len(scores)+1)*.95))
    if rank>len(scores):
        return None,{'status':'unavailable','reason':'insufficient_95pct_quantile_support'}
    return float(scores[rank-1]),{'status':'available','n_events':len(scores),'nominal_coverage':.95,
        'kind':'rolling event-max residual interval','note':'Empirical time-ordered calibration; temporal drift can affect future coverage.'}
