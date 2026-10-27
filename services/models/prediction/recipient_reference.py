"""Explicitly frozen global pair-feature ranges, independent of retrieval filters."""
from functools import lru_cache
import hashlib
import json
from pathlib import Path
from django.conf import settings
from services.models.similarity.calibration import fit_ranges
from services.models.features.neighborhood import offset
from datetime import date
from .pair_cases import PAIR_NUMERIC


def freeze_pair_reference(analysis_unit='event'):
    base=Path(settings.BASE_DIR)/'data/calibration';source=base/('episode_recipient_cases.jsonl' if analysis_unit=='episode' else 'event_recipient_cases.jsonl')
    rows=[]
    with source.open(encoding='utf-8') as stream:
        for line in stream:
            row=json.loads(line)
            rows.append({'date':row['event_date'],**{f:row.get(f) for f in PAIR_NUMERIC}})
    boundaries=sorted({r['date'] for r in rows}|{offset(date.fromisoformat(r['date']),1).isoformat() for r in rows})
    manifest=json.loads(source.with_suffix('.manifest.json').read_text(encoding='utf-8'))
    payload={'dataset_sha256':manifest['sha256'],'profiles':len(rows),'ranges_before':{cutoff:fit_ranges([r for r in rows if r['date']<cutoff],PAIR_NUMERIC) for cutoff in boundaries}}
    payload['reference_id']=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()[:24]
    path=base/('recipient_episode_reference.json' if analysis_unit=='episode' else 'recipient_reference.json');temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(payload,indent=2),encoding='utf-8');temporary.replace(path)
    return {'reference_id':payload['reference_id'],'profiles':len(rows)}


@lru_cache(maxsize=2)
def _read(path,mtime):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def pair_reference(cutoff,analysis_unit='event'):
    path=Path(settings.BASE_DIR)/'data/calibration'/('recipient_episode_reference.json' if analysis_unit=='episode' else 'recipient_reference.json')
    if not path.exists():
        return {},{'status':'unavailable','reason':'missing_frozen_pair_reference'}
    artifact=_read(str(path),path.stat().st_mtime_ns)
    manifest=json.loads((path.parent/('episode_recipient_cases.manifest.json' if analysis_unit=='episode' else 'event_recipient_cases.manifest.json')).read_text(encoding='utf-8'))
    if manifest['sha256']!=artifact['dataset_sha256']:
        return {},{'status':'unavailable','reason':'pair_reference_dataset_revision_mismatch'}
    keys=[k for k in artifact['ranges_before'] if k<=cutoff]
    return artifact['ranges_before'][max(keys)] if keys else {},{'status':'available','reference_id':artifact['reference_id'],'training_before':cutoff}
