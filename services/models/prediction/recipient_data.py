"""Shared historical network inputs and bounded event-pair loading."""
from collections import defaultdict
from functools import lru_cache
import json
from pathlib import Path
from django.conf import settings
from django.db.models import Min
from core.models import RadioNetworkEvent,Cell,MAOSMonthlyKPI
from services.models.features.neighborhood import inventory,neighborhood,offset
from services.models.similarity.profile_cache import profile_revision
from .cbr_impact import _month_rows,_row_value,OUTPUT_FIELDS
from .pair_cases import prior_value,relative_bearing,event_magnitude,event_bands


@lru_cache(maxsize=1)
def policy():
    return json.loads((Path(settings.BASE_DIR)/'config/recipient_cbr.json').read_text(encoding='utf-8'))


class RecipientData:
    def __init__(self):
        self.cache={};self.locations,self.by_raw=inventory(self.cache)
        self.history=_month_rows();self.cells=defaultdict(list);self.by_cell={}
        self.first={r['cell_id']:r['first'] for r in MAOSMonthlyKPI.objects.filter(thrp_bits_dl__gt=0)
            .values('cell_id').annotate(first=Min('month_date'))}
        for cell in Cell.objects.values('id','cell_id','site__site_id','band','azimuth','technology'):
            key=self.by_raw.get(cell['site__site_id'],cell['site__site_id'])
            self.cells[key].append(cell);self.by_cell[cell['cell_id']]=cell
        self.events=list(RadioNetworkEvent.objects.filter(is_current=True).select_related('site').order_by('effective_date','event_key'))
        self.active_event_keys={e.event_key for e in self.events}
        from core.models import AnalysisEpisode
        self.active_episode_keys=set(AnalysisEpisode.objects.filter(is_current=True).values_list('episode_key',flat=True))
        self.control_cache={};self.exposure_cache={}
        self._band_cache={};self._value_cache={};self.control_feature_cache={}
        self.control_effect_cache={}
        self._query_pair_cache={}

    def bands(self,key,cutoff):
        if (key,cutoff) not in self._band_cache:
            self._band_cache[key,cutoff]={c['band'] for c in self.cells[key] if c['band'] and c['technology']=='4G'
                and c['id'] in self.first and self.first[c['id']]<cutoff}
        return self._band_cache[key,cutoff]

    def values(self,key,cutoff,metric,n=3):
        cache_key=(key,cutoff,metric,n)
        if cache_key not in self._value_cache:
            rows=self.history.get(key,{})
            self._value_cache[cache_key]=[_row_value(rows.get(offset(cutoff,k)),metric) for k in range(-n,0)]
        return self._value_cache[cache_key]

    def query_pairs(self,site,event,scope):
        cache_key=(site.site_id,event.event_key,scope)
        if cache_key in self._query_pair_cache:
            return self._query_pair_cache[cache_key]
        cutoff=event.effective_date;context=neighborhood(site,cutoff,self.cache)
        azimuths=[self.by_cell[k]['azimuth'] for k in event.details.get('cell_ids',[]) if k in self.by_cell]
        bands=event_bands(event,self.by_cell);rows=[]
        prbs={(key,month):value for key,month,value in MAOSMonthlyKPI.objects.filter(
            cell__cell_id__in=event.details.get('cell_ids',[]),month_date=cutoff).values_list('cell__cell_id','month_date','prb_dl_available')}
        origin=context['canonical_site_id']
        origin_member={'site_id':origin,'site_name':self.locations[origin]['site_name'],'distance_m':0.,'bearing_deg':None,'tier':'origin'}
        if scope=='origin':
            members=[origin_member]
        elif scope in ('network','cluster_total'):
            surrounding=context['scopes']['cluster'] if scope=='cluster_total' else context['scopes']['tier1']+context['scopes']['tier2']
            members=[origin_member]+surrounding
        else:
            members=context['scopes'][scope]
        for member in members:
            key=member['site_id'];observed_bands=self.bands(key,cutoff)
            features={name:prior_value(self.history.get(key,{}),cutoff,raw)[0] for name,raw in
                [('recipient_pre_dl_gb','thrp_dl_gb'),('recipient_pre_active_users','active_users_avg'),
                 ('recipient_pre_prb_util_pct','prb_util_dl_pct'),('recipient_pre_cqi','cqi_avg')]}
            rows.append({'recipient_role':'origin' if member['tier']=='origin' else 'neighbor','analysis_unit':event.details.get('analysis_unit','event'),'action_signature':event.details.get('action_signature'),
                'event_key':event.event_key,'event_site_id':context['canonical_site_id'],'recipient_site_id':key,
                'event_type':event.event_type,'event_date':cutoff.isoformat(),'tier_scheme':context['tier_scheme'],
                'technology':'/'.join(sorted(event.details.get('technologies',[]))) or None,'bands':sorted(bands),
                'distance_m':member['distance_m'],'relative_bearing_deg':relative_bearing(member['bearing_deg'],azimuths),
                'same_band':bool(bands&observed_bands) if bands and observed_bands else None,
                'site_name':member['site_name'],'tier':member['tier'],**features,**event_magnitude(event,prbs)})
        self._query_pair_cache[cache_key]=context,rows
        return context,rows


@lru_cache(maxsize=1)
def _cached_data(revision):
    return RecipientData()


def data_context():
    revision=profile_revision()
    return _cached_data(revision) if revision else RecipientData()


def load_training(query,metric,horizon=None,path=None,recipient_disjoint=False):
    """No post-cutoff target or same-origin event may enter retrieval."""
    source=Path(path or Path(settings.BASE_DIR)/('data/calibration/episode_recipient_cases.jsonl' if query.get('analysis_unit')=='episode' else 'data/calibration/event_recipient_cases.jsonl'))
    if not source.exists():
        return []
    cutoff=query['event_date'];rows=[]
    with source.open(encoding='utf-8') as stream:
        for line in stream:
            row=json.loads(line)
            if row.get('analysis_unit','event')!=query.get('analysis_unit','event') or row.get('action_signature')!=query.get('action_signature'):
                continue
            if row['event_date']>=cutoff or row['event_site_id']==query['event_site_id'] or row['event_key']==query['event_key']:
                continue
            if row['event_type']!=query['event_type'] or row['tier_scheme']!=query['tier_scheme']:
                continue
            if recipient_disjoint and row['recipient_site_id']==query['recipient_site_id']:
                continue
            targets=row.get('outcomes',{}).get(metric,{}) if metric is not None else {
                h:v for values in row.get('outcomes',{}).values() for h,v in values.items() if v is not None}
            horizons=[str(horizon)] if horizon is not None else list(targets)
            if any(row.get('outcome_months',{}).get(h,'9999')<cutoff and
                   targets.get(h) is not None for h in horizons):
                rows.append(row)
    return rows
