"""Pre-period matched controls with explicit exposure censoring and no silent relaxation."""
from datetime import date
import numpy as np
from services.models.features.neighborhood import offset
from .recipient_data import policy


def complete(values):
    return bool(values) and all(v is not None and np.isfinite(v) for v in values)


def slope(values):
    return float(np.polyfit(np.arange(len(values)),values,1)[0]) if complete(values) and len(values)>=2 else None


class MatchedControls:
    def __init__(self,data):
        self.data=data;self.rows=list(data.locations.values())
        self.lat=np.radians([r['latitude'] for r in self.rows]);self.lon=np.radians([r['longitude'] for r in self.rows])

    def distances(self,latitude,longitude):
        lat,lon=np.radians([latitude,longitude])
        a=np.sin((self.lat-lat)/2)**2+np.cos(lat)*np.cos(self.lat)*np.sin((self.lon-lon)/2)**2
        return 6371000*2*np.arcsin(np.sqrt(np.clip(a,0,1)))

    def exposed(self,start,end,radius):
        key=(start,end,radius)
        if key not in self.data.exposure_cache:
            mask=np.zeros(len(self.rows),dtype=bool)
            for event in self.data.events:
                if start<=event.effective_date<=end:
                    mask |= self.distances(event.site.latitude,event.site.longitude)<=radius
            self.data.exposure_cache[key]={r['site_id'] for r,hit in zip(self.rows,mask) if hit}
        return self.data.exposure_cache[key]

    def features(self,key,cutoff):
        cache=getattr(self.data,'control_feature_cache',None)
        if cache is not None and (key,cutoff) in cache:
            return cache[key,cutoff]
        traffic=self.data.values(key,cutoff,'downlink_traffic_gb',6)
        users=self.data.values(key,cutoff,'active_users',3)
        if not complete(traffic):
            if cache is not None:
                cache[key,cutoff]=None
            return None
        base=float(np.mean(traffic[-3:]))
        # Missing user data stays absent from the matching distance.
        result=np.array([np.log1p(base),np.log1p(np.mean(users)) if complete(users) else np.nan,
            slope(traffic)/max(abs(base),1.)],dtype=float)
        if cache is not None:
            cache[key,cutoff]=result
        return result

    def pool(self,cutoff,metric,radius):
        if not hasattr(self.data,'control_pool_cache'):
            self.data.control_pool_cache={}
        cache_key=(cutoff,metric,radius)
        if cache_key not in self.data.control_pool_cache:
            p=policy();excluded=self.exposed(offset(cutoff,-p['minimum_pretrend_months']),cutoff,radius)
            rows=[];features=[];slopes=[];baselines=[];bands=[]
            for row in self.rows:
                key=row['site_id']
                if key in excluded:
                    continue
                observed_bands=self.data.bands(key,cutoff);x=self.features(key,cutoff)
                values=self.data.values(key,cutoff,metric,p['minimum_pretrend_months'])
                if not observed_bands or x is None or not complete(values):
                    continue
                rows.append(row);features.append(x);slopes.append(slope(values));baselines.append(np.mean(values[-3:]));bands.append(observed_bands)
            self.data.control_pool_cache[cache_key]={'rows':rows,'features':np.array(features).reshape((-1,3)),
                'slopes':np.array(slopes),'baselines':np.array(baselines),'bands':bands,'band_masks':{},
                'noise':np.array([r['cluster_id']==-1 for r in rows],dtype=bool)}
        return self.data.control_pool_cache[cache_key]

    def select(self,key,cutoff,metric,radius=None):
        p=policy();radius=radius or p['control_exclusion_m']
        cache_key=(key,cutoff,metric,radius)
        if cache_key in self.data.control_cache:
            return self.data.control_cache[cache_key]
        result={'controls':[],'status':'unavailable','reason':None,'exclusion_m':radius,
            'selection_cutoff':cutoff.isoformat(),'baseline_kind':'mean of months -3..-1',
            'pretrend_months':p['minimum_pretrend_months'],'causal_claim':False}
        origin=self.data.locations[key];bands=self.data.bands(key,cutoff);features=self.features(key,cutoff)
        pre=self.data.values(key,cutoff,metric,p['minimum_pretrend_months'])
        if features is None or not complete(pre) or not bands:
            result['reason']='missing_six_month_pretrend_or_historical_LTE_band'
        else:
            pool=self.pool(cutoff,metric,radius)
            band_key=tuple(sorted(bands))
            if band_key not in pool['band_masks']:
                pool['band_masks'][band_key]=np.array([len(bands&value)/len(bands|value)>=p['control_band_overlap'] for value in pool['bands']])
            common=np.isfinite(pool['features'])&np.isfinite(features)
            delta=np.abs((pool['features']-features)/np.array(p['control_match_scales']))
            distances=np.where(common,delta,0.).sum(axis=1)/np.maximum(common.sum(axis=1),1)
            gaps=np.abs(pool['slopes']-slope(pre))/max(abs(float(np.mean(pre[-3:]))),1.)
            mask=pool['band_masks'][band_key] & (pool['noise']==(origin['cluster_id']==-1))
            mask &= (distances<=p['control_caliper']) & (gaps<=p.get('control_pretrend_caliper',.1))
            ids=[i for i in np.flatnonzero(mask) if pool['rows'][i]['site_id']!=key]
            ids.sort(key=lambda i:(distances[i],pool['rows'][i]['site_id']))
            candidates=[{'site_id':pool['rows'][i]['site_id'],'site_name':pool['rows'][i]['site_name'],
                'distance':float(distances[i]),'pretrend_gap':float(gaps[i]),'pretrend_slope':float(pool['slopes'][i]),
                'baseline':float(pool['baselines'][i]),'pre_months':p['minimum_pretrend_months']} for i in ids]
            selected=candidates[:p['control_max_members']]
            for candidate in selected:
                candidate['pre_values']=self.data.values(candidate['site_id'],cutoff,metric,p['minimum_pretrend_months'])
            result['eligible_controls']=len(candidates)
            if len(selected)>=p['minimum_controls']:
                h=max(float(np.median([r['distance'] for r in selected]))/2,1e-6)
                logs=np.array([-.5*(r['distance']/h)**2 for r in selected]);weights=np.exp(logs-logs.max());weights/=weights.sum()
                result.update(controls=[{**r,'weight':float(w)} for r,w in zip(selected,weights)],status='available',reason=None,
                    treated_pretrend_slope=slope(pre),treated_pre_values=pre,note='Matched pretrend diagnostic is not proof of parallel trends; observational adjustment only.')
            else:
                result['reason']='fewer_than_three_unexposed_matched_controls'
        self.data.control_cache[cache_key]=result
        return result

    def effect(self,key,cutoff,metric,horizon,radius=None):
        """Completed historical mean-baseline DiD, censoring later exposure."""
        cache=getattr(self.data,'control_effect_cache',None)
        cache_key=(key,cutoff,metric,horizon,radius or policy()['control_exclusion_m'])
        if cache is not None and cache_key in cache:
            return cache[cache_key]
        result=self._effect(key,cutoff,metric,horizon,radius)
        if cache is not None:
            cache[cache_key]=result
        return result

    def _effect(self,key,cutoff,metric,horizon,radius=None):
        p=policy();radius=radius or p['control_exclusion_m'];match=self.select(key,cutoff,metric,radius)
        if match['status']!='available':
            return None,match
        target_month=offset(cutoff,horizon)
        contaminated=self.exposed(offset(cutoff,1),target_month,radius)
        # A recipient newly exposed to another event is not a clean response label.
        if key in contaminated:
            return None,{**match,'reason':'recipient_exposed_to_later_event'}
        from .cbr_impact import _row_value
        treated=_row_value(self.data.history.get(key,{}).get(target_month),metric)
        pre=self.data.values(key,cutoff,metric,3)
        controls=[]
        for control in match['controls']:
            observed=_row_value(self.data.history.get(control['site_id'],{}).get(target_month),metric)
            if control['site_id'] not in contaminated and observed is not None:
                controls.append((control,observed-control['baseline']))
        if treated is None or not complete(pre) or len(controls)<p['minimum_controls']:
            return None,{**match,'reason':'incomplete_or_censored_control_outcomes','surviving_controls':len(controls)}
        total=sum(c['weight'] for c,_ in controls)
        growth=sum(c['weight']*v for c,v in controls)/total
        return float(treated-np.mean(pre)-growth),{**match,'surviving_controls':len(controls),'observed_control_change':growth}

    def forecast_growth(self,match,horizon):
        if match['status']!='available':
            return None
        # Only six pre-event months enter this extrapolation; never future controls.
        return float(sum(c['weight']*c['pretrend_slope']*(horizon+2) for c in match['controls']))
