"""Versioned reference ranges and pre-renormalisation support, never query-fitted."""
import hashlib
import json
from functools import lru_cache
from pathlib import Path
import numpy as np
from django.conf import settings
from .gower_distance import GowerDistance
from services.models.features.road_loader import ROAD_FIELDS,road_config


def policy():
    return json.loads((Path(settings.BASE_DIR)/'config/similarity_policy.json').read_text(encoding='utf-8'))


def fit_ranges(rows,fields=None):
    result={}
    for key in fields or GowerDistance.NUMERIC_FEATURES:
        values=[float(row[key]) for row in rows if isinstance(row.get(key),(float,int,np.number)) and np.isfinite(row[key])]
        if values:
            result[key]=list(map(float,np.percentile(values,[5,95])))
    return result


def freeze_reference(rows,path,metadata=None):
    payload={'policy_version':policy()['version'],'profiles':rows,'metadata':metadata or {}}
    from datetime import date
    boundaries=set()
    for row in rows:
        current=date.fromisoformat(row['feature_as_of_date'])
        boundaries.add(current.isoformat())
        boundaries.add(date(current.year+(current.month==12),current.month%12+1,1).isoformat())
    payload['ranges_before']={cutoff:fit_ranges([r for r in rows if r['feature_as_of_date']<cutoff]) for cutoff in sorted(boundaries)}
    payload['reference_id']=hashlib.sha256(json.dumps(payload,sort_keys=True,default=str).encode()).hexdigest()[:24]
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(payload,indent=2,allow_nan=False,default=str),encoding='utf-8')
    _read_reference.cache_clear()
    return payload


@lru_cache(maxsize=4)
def _read_reference(path,mtime):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def reference_ranges(query,candidates,override=None):
    if override is not None:
        return override,{'kind':'explicit_training_reference'}
    # Synthetic callers have no dated profile. Production vectors always have one.
    if not query.get('feature_as_of_date'):
        return fit_ranges(candidates),{'kind':'undated_synthetic_fixture'}
    path=Path(settings.BASE_DIR)/policy()['reference_path']
    if not path.exists():
        return {},{'kind':'unavailable','reason':'Run freeze_similarity_reference before ranking.'}
    artifact=_read_reference(str(path),path.stat().st_mtime_ns)
    cutoff=query['feature_as_of_date']
    rows=[r for r in artifact['profiles'] if r['feature_as_of_date']<cutoff]
    boundaries=[key for key in artifact.get('ranges_before',{}) if key<=cutoff]
    ranges=artifact['ranges_before'][max(boundaries)] if boundaries else {}
    # Global within the frozen reference, not conditioned on event/tech/band filters.
    return ranges,{'kind':'frozen_global_training_reference','reference_id':artifact['reference_id'],
        'training_before':cutoff,'reference_profiles':len(rows),
        'note':'Frozen reference profiles; only profiles strictly before the query cutoff contribute.'}


def available_weight_share(distance,query,candidate,selected,mode,group_weights=None,field_groups=None):
    """Budget on query-available selected fields, before pair renormalisation."""
    fields=[f for f in dict.fromkeys(selected) if f not in ('site_id','cluster_id','tier_scheme','cluster_avg_users')
            and not distance._is_missing(query.get(f))]
    group=lambda f:(field_groups or {}).get(f,distance._get_feature_group(f))
    groups={g:[f for f in fields if group(f)==g] for g in {group(f) for f in fields}}
    if mode=='equal_per_group':
        budgets={f:(group_weights or {}).get(g,1.)/len(fs) for g,fs in groups.items() for f in fs}
    else:
        budgets={f:1. for f in fields}
    roads=sum(w for f,w in budgets.items() if f in ROAD_FIELDS)
    other=sum(w for f,w in budgets.items() if f not in ROAD_FIELDS)
    if roads:
        factor=min(1.,other*road_config()['road_group_weight_cap']/(1-road_config()['road_group_weight_cap'])/roads)
        budgets={f:w*(factor if f in ROAD_FIELDS else 1.) for f,w in budgets.items()}
    total=sum(budgets.values())
    common=[f for f in fields if not distance._is_missing(candidate.get(f)) and
            (f not in ROAD_FIELDS or (query.get('road_context_signature') and query.get('road_context_signature')==candidate.get('road_context_signature')))]
    return sum(budgets[f] for f in common)/total if total else 0.
