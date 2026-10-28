"""Offline nested, chronological, event/site-grouped calibration of recipient CBR.

RF proximity and local ridge are experiments only. No model is promoted here.
"""
from collections import Counter,defaultdict
import hashlib
import itertools
import json
from pathlib import Path
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from .pair_cases import PAIR_NUMERIC,PAIR_CATEGORICAL,PAIR_GROUPS
from services.models.similarity.calibration import fit_ranges

FIELDS=PAIR_NUMERIC+PAIR_CATEGORICAL
GRID=[{'groups':{'geometry':g,'recipient_load':1.,'configuration':1.},'kernel_factor':h}
      for g,h in itertools.product((.5,1.,2.),(.25,.5,1.))]
DEFAULT={'groups':{'geometry':1.,'recipient_load':1.,'configuration':1.},'kernel_factor':.5}


def sample_cases(path,events_per_type=60,recipients_per_event=3):
    """Deterministic hash sample by event type then recipient; avoids nearest-only bias."""
    selected=defaultdict(dict)
    with Path(path).open(encoding='utf-8') as source:
        for line in source:
            row=json.loads(line);event=row['event_key'];kind=row['event_type']
            score=hashlib.sha256(event.encode()).hexdigest()
            pool=selected[kind]
            if event not in pool:
                if len(pool)>=events_per_type:
                    worst=max(pool,key=lambda k:pool[k][0])
                    if score>=pool[worst][0]:
                        continue
                    del pool[worst]
                pool[event]=(score,[])
            members=pool[event][1]
            rank=hashlib.sha256((event+':'+row['recipient_site_id']).encode()).hexdigest()
            members.append((rank,row));members.sort(key=lambda r:r[0]);del members[recipients_per_event:]
    return sorted([r for pool in selected.values() for _,members in pool.values() for _,r in members],
                  key=lambda r:(r['event_date'],r['event_key'],r['recipient_site_id']))


def target(row,metric,horizon):
    return row.get('outcomes',{}).get(metric,{}).get(str(horizon))


def split_at(rows,validation_dates,metric,horizon):
    cutoff=min(validation_dates)
    validation=[r for r in rows if r['event_date'] in validation_dates and target(r,metric,horizon) is not None]
    # Purge the physical origin and all its events across train/test. Recipients
    # may recur in older training periods; record this explicitly in the report.
    origins={r['event_site_id'] for r in validation}
    events={r['event_key'] for r in validation}
    training=[r for r in rows if r['event_date']<cutoff and r['event_site_id'] not in origins and r['event_key'] not in events
              and r.get('outcome_months',{}).get(str(horizon),'9999')<cutoff and target(r,metric,horizon) is not None]
    return training,validation


def date_folds(rows,count=3):
    dates=sorted({r['event_date'] for r in rows})
    if len(dates)<4:
        return []
    start=max(2,len(dates)//2)
    return [list(part) for part in np.array_split(dates[start:],count) if len(part)]


class PairRanker:
    def __init__(self,rows,metric,horizon,feature_ranges=None):
        self.rows=rows;self.y=np.array([target(r,metric,horizon) for r in rows],dtype=float)
        self.ranges=fit_ranges(rows,PAIR_NUMERIC) if feature_ranges is None else feature_ranges
        self.values=np.array([[r.get(f) if r.get(f) is not None else np.nan for f in FIELDS] for r in rows],dtype=float).reshape((-1,len(FIELDS)))
        self.forest=None
        self._eligible_cache={}
        self._event_keys=np.array([r['event_key'] for r in rows])
        self._recipient_keys=np.array([r['recipient_site_id'] for r in rows])

    def eligible(self,query,allow_relaxation=True):
        cache_key=(query['event_type'],query['tier_scheme'],query['event_site_id'],query['event_key'],query.get('technology'),tuple(query['bands']),allow_relaxation,query.get('analysis_unit','event'),query.get('action_signature'),query.get('recipient_role','neighbor'))
        if cache_key in self._eligible_cache:
            return self._eligible_cache[cache_key]
        indices=[i for i,r in enumerate(self.rows) if r['event_type']==query['event_type'] and r['tier_scheme']==query['tier_scheme']
                 and r['event_site_id']!=query['event_site_id'] and r['event_key']!=query['event_key']
                 and r.get('analysis_unit','event')==query.get('analysis_unit','event') and r.get('action_signature')==query.get('action_signature')
                 and r.get('recipient_role','neighbor')==query.get('recipient_role','neighbor')]
        tech=[i for i in indices if self.rows[i].get('technology')==query.get('technology')]
        bands=[i for i in tech if (not query['bands'] and not self.rows[i]['bands']) or
               len(set(query['bands'])&set(self.rows[i]['bands']))/max(1,len(set(query['bands'])|set(self.rows[i]['bands'])))>=.5]
        result=bands if not allow_relaxation or len(bands)>=3 else tech if len(tech)>=3 else indices
        self._eligible_cache[cache_key]=result
        return result

    def neighbors(self,query,config,max_per_event=None,limit=20):
        ids=self.eligible(query,config.get('allow_filter_relaxation',True))
        if not ids:
            return [],[],[]
        q=np.array([query.get(f) if query.get(f) is not None else np.nan for f in FIELDS],dtype=float)
        available=np.isfinite(q)&np.array([f in config.get('selected_features',FIELDS) for f in FIELDS])
        counts=Counter(PAIR_GROUPS[f] for j,f in enumerate(FIELDS) if available[j])
        budget=np.array([config['groups'].get(PAIR_GROUPS[f],1.)/(counts[PAIR_GROUPS[f]] if config.get('weighting_mode','equal_per_group')=='equal_per_group' else 1) if available[j] else 0. for j,f in enumerate(FIELDS)])
        common=np.isfinite(self.values[ids])&available
        for j,f in enumerate(FIELDS):
            if f in PAIR_NUMERIC and f not in self.ranges:
                common[:,j]=False
        supported=(common*budget).sum(axis=1)
        coverage=supported/budget.sum() if budget.sum()>0 else np.zeros(len(ids))
        delta=np.zeros((len(ids),len(FIELDS)))
        for j,f in enumerate(FIELDS):
            if f in PAIR_CATEGORICAL:
                delta[:,j]=(self.values[ids,j]!=q[j]).astype(float)
            elif f in self.ranges:
                low,high=self.ranges[f]
                delta[:,j]=np.minimum(1.,np.abs(self.values[ids,j]-q[j])/(high-low)) if high>low else 0.
        distance_budget=np.broadcast_to(budget,common.shape).copy()
        if config.get('weighting_mode')=='equal_per_group':
            # Coverage uses the query's prior budget above; distance balances
            # each surviving group across the pair's actual common dimensions.
            for group in set(PAIR_GROUPS.values()):
                columns=[j for j,f in enumerate(FIELDS) if PAIR_GROUPS[f]==group]
                counts_common=common[:,columns].sum(axis=1)
                distance_budget[:,columns]=config['groups'].get(group,1.)/np.maximum(counts_common[:,None],1)
        distance_budget=np.where(common,distance_budget,0.)
        distances=(np.where(common,delta,0)*distance_budget).sum(axis=1)/np.maximum(distance_budget.sum(axis=1),1e-12)
        valid=np.flatnonzero((supported>0)&(coverage+1e-12>=config.get('minimum_available_weight_share',.6)))
        members=np.asarray(ids)[valid]
        ordered=valid[np.lexsort((self._recipient_keys[members],self._event_keys[members],distances[valid]))]
        order=[];events=Counter()
        for j in ordered:
            event=self.rows[ids[j]]['event_key']
            if max_per_event is not None and events[event]>=max_per_event:
                continue
            order.append(j);events[event]+=1
            if len(order)==limit:
                break
        return [ids[j] for j in order],distances[order],coverage[order]

    def predict(self,query,config,method='gower'):
        ids,distance,coverage=self.neighbors(query,config)
        if len({self.rows[i]['event_key'] for i in ids})<2:
            return None
        h=max(float(np.median(distance))*config['kernel_factor'],1e-6)
        log=-.5*(distance/h)**2;weights=np.exp(log-np.max(log))
        counts=Counter(self.rows[i]['event_key'] for i in ids)
        weights=np.array([w/counts[self.rows[i]['event_key']] for w,i in zip(weights,ids)])
        if method=='rf_proximity':
            complete=np.isfinite(self.values).all(axis=1)
            q=np.array([query.get(f) if query.get(f) is not None else np.nan for f in FIELDS])
            if not complete.any() or not np.isfinite(q).all():
                return None
            if self.forest is None:
                self.forest=RandomForestRegressor(n_estimators=48,min_samples_leaf=5,max_depth=8,random_state=41,n_jobs=1)
                event_counts=Counter(r['event_key'] for r in self.rows)
                self.forest.fit(self.values[complete],self.y[complete],sample_weight=np.array([1/event_counts[r['event_key']] for r in self.rows])[complete])
            ids=[i for i in ids if complete[i]]
            if len({self.rows[i]['event_key'] for i in ids})<2:
                return None
            leaves=self.forest.apply(self.values[ids]);leaf=self.forest.apply(q.reshape(1,-1))[0]
            weights=(leaves==leaf).mean(axis=1)
            counts=Counter(self.rows[i]['event_key'] for i in ids)
            weights=np.array([w/counts[self.rows[i]['event_key']] for w,i in zip(weights,ids)])
        if weights.sum()<=0:
            return None
        weights=weights/weights.sum();estimate=float(weights@self.y[ids])
        if method=='local_linear_hybrid':
            q=np.array([query.get(f) if query.get(f) is not None else np.nan for f in FIELDS])
            # Complete local observations only, never impute; require enough
            # independent event support before fitting this optional adjustment.
            if not np.isfinite(q).all() or not np.isfinite(self.values[ids]).all() or len(ids)<10 or len({self.rows[i]['event_key'] for i in ids})<3:
                return None
            x=self.values[ids];scale=np.std(x,axis=0);scale[scale==0]=1
            center=np.mean(x,axis=0)
            model=Ridge(alpha=1.).fit((x-center)/scale,self.y[ids],sample_weight=weights)
            estimate=.5*estimate+.5*float(model.predict(((q-center)/scale).reshape(1,-1))[0])
        return estimate


def errors(records):
    if not records:
        return {'n_pairs':0,'n_events':0,'mae':None,'rmse':None,'event_macro_mae':None}
    delta=np.array([r['predicted']-r['actual'] for r in records]);groups=defaultdict(list)
    for row,error in zip(records,np.abs(delta)):
        groups[row['event_key']].append(float(error))
    return {'n_pairs':len(records),'n_events':len(groups),'mae':float(np.abs(delta).mean()),
            'rmse':float(np.sqrt(np.mean(delta**2))),'event_macro_mae':float(np.mean([np.mean(v) for v in groups.values()]))}


def tune(rows,metric,horizon):
    folds=[]
    for dates in date_folds(rows,2):
        train,valid=split_at(rows,dates,metric,horizon)
        if train and valid:
            folds.append((PairRanker(train,metric,horizon),valid))
    trials=[]
    for config in GRID:
        records=[]
        for model,valid in folds:
            for row in valid:
                predicted=model.predict(row,config)
                if predicted is not None:
                    records.append({'event_key':row['event_key'],'recipient_site_id':row['recipient_site_id'],
                        'actual':target(row,metric,horizon),'predicted':predicted})
        trials.append((config,records))
    common=set.intersection(*[{(r['event_key'],r.get('recipient_site_id')) for r in records} for _,records in trials]) if trials else set()
    choices=[]
    for config,records in trials:
        report=errors([r for r in records if (r['event_key'],r.get('recipient_site_id')) in common])
        if report['n_events']>=3:
            choices.append((report['event_macro_mae'],config,{**report,'comparison':'common support across all configurations'}))
    return min(choices,key=lambda x:x[0])[1:] if choices else (DEFAULT,{'reason':'insufficient inner validation support'})


def validate_pairs(path,output,events_per_type=60,recipients_per_event=3,horizons=(1,3,6),progress=print):
    rows=sample_cases(path,events_per_type,recipients_per_event)
    metrics=('downlink_traffic_gb','cqi_avg','active_users','dl_throughput_kbps','dl_packet_delay_ms')
    report={'version':'pair-nested-validation-v1','sample_pairs':len(rows),'sample_events':len({r['event_key'] for r in rows}),
        'sampling':{'events_per_type':events_per_type,'recipients_per_event':recipients_per_event,'method':'deterministic SHA256'},
        'validation':'3 outer / 2 inner chronological blocks; whole events and physical event-origin sites purged; targets observed strictly before each cutoff',
        'recipient_reuse':'Recipients may recur in earlier training events. Scores are event-macro averaged; no claim of independent recipient/site generalisation.',
        'promotion':'offline experiments only; no production weights or estimator changed','results':[]}
    manifest=Path(path).with_suffix('.manifest.json')
    if manifest.exists():
        report['dataset']=json.loads(manifest.read_text(encoding='utf-8'))
    for metric,horizon in itertools.product(metrics,horizons):
        predictions=defaultdict(list);folds=[];eligible_count=0
        for dates in date_folds(rows):
            train,valid=split_at(rows,dates,metric,horizon);eligible_count+=len(valid)
            if not train or not valid:
                continue
            config,inner=tune(train,metric,horizon);model=PairRanker(train,metric,horizon)
            folds.append({'cutoff':min(dates),'train_pairs':len(train),'validation_pairs':len(valid),
                'selected_config':config,'inner':inner,'frozen_ranges':model.ranges})
            for row in valid:
                for method in ('baseline_gower','tuned_gower','rf_proximity','local_linear_hybrid'):
                    predicted=model.predict(row,DEFAULT if method=='baseline_gower' else config,
                        method if method in ('rf_proximity','local_linear_hybrid') else 'gower')
                    if predicted is not None:
                        predictions[method].append({'event_key':row['event_key'],'recipient_site_id':row['recipient_site_id'],
                            'actual':target(row,metric,horizon),'predicted':predicted})
        scores={name:{**errors(predictions[name]),'eligible_pairs':eligible_count,
            'coverage':len(predictions[name])/eligible_count if eligible_count else 0.}
            for name in ('baseline_gower','tuned_gower','rf_proximity','local_linear_hybrid')}
        common=set.intersection(*[{(r['event_key'],r['recipient_site_id']) for r in predictions[name]} for name in scores])
        common_scores={name:errors([r for r in predictions[name] if (r['event_key'],r['recipient_site_id']) in common]) for name in scores}
        report['results'].append({'metric':metric,'horizon':horizon,'scores':scores,'common_support_scores':common_scores,'folds':folds})
        progress(f'Validated {metric} +{horizon}: '+str(scores))
    destination=Path(output);destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    return report
