"""Read-only independent export structure and traffic arithmetic audit; run via manage.py shell."""
from datetime import date
import hashlib
import json
from collections import Counter
from pathlib import Path
from statistics import median
from services.models.prediction.cbr_impact import _month_rows

path=Path('data/calibration/event_recipient_cases.jsonl')
manifest=json.loads(path.with_suffix('.manifest.json').read_text())
by_site=_month_rows();count=0;checked=0;digest=hashlib.sha256()
availability=Counter();bandwidth=Counter()


def month_at(current,offset):
    number=current.year*12+current.month-1+offset
    return date(number//12,number%12+1,1)


with path.open('rb') as stream:
    for line in stream:
        digest.update(line);row=json.loads(line);count+=1
        for feature in ('same_band','relative_bearing_deg','event_prb_delta','event_added_cells','recipient_pre_dl_gb','recipient_pre_active_users','recipient_pre_prb_util_pct','recipient_pre_cqi'):
            if row.get(feature) is not None:
                availability[feature]+=1
        if row['event_type'].startswith('BANDWIDTH_'):
            bandwidth['pairs']+=1
            bandwidth['with_bands']+=bool(row['bands'])
        distance=row['distance_m']
        assert distance>=50
        if row['tier_scheme']=='standard':
            assert row['tier']==('tier1' if distance<=2000 else 'tier2') and distance<=5000
        else:
            assert row['tier']==('tier1' if distance<5000 else 'tier2') and distance<10000
        assert row['relative_bearing_deg'] is None or 0<=row['relative_bearing_deg']<=180
        assert all('0' not in values for values in row['outcomes'].values())
        assert all(value is None or row['baseline_support'][key]==3 for key,value in row.items() if key.startswith('recipient_pre_'))
        if count%1000:
            continue
        cutoff=date.fromisoformat(row['event_date']);history=by_site.get(row['recipient_site_id'],{})
        bits=[history.get(month_at(cutoff,k),{}).get('traffic_bits') for k in (-3,-2,-1)]
        baseline=median(bits)/8e9 if all(v is not None for v in bits) else None
        assert baseline==row['recipient_pre_dl_gb'] or (baseline is not None and abs(baseline-row['recipient_pre_dl_gb'])<1e-8)
        for offset,value in row['outcomes']['downlink_traffic_gb'].items():
            month=month_at(cutoff,int(offset));observed=history.get(month,{}).get('traffic_bits')
            expected=observed/8e9-baseline if observed is not None and baseline is not None else None
            assert value==expected or (value is not None and expected is not None and abs(value-expected)<1e-8)
            assert row['outcome_months'][offset]==month.isoformat()
        checked+=1
assert count==manifest['pairs'] and digest.hexdigest()==manifest['sha256']
result={'rows_checked':count,'independent_traffic_cases':checked,'hash_verified':True,'mismatches':0,
        'feature_available_rows':dict(availability),'bandwidth_band_coverage':dict(bandwidth),
        'checks':['tier boundaries','strict three-month feature support','no month-zero target',
            'relative bearing bounds','independent traffic baseline and outcome arithmetic','dataset hash']}
output=Path('docs/verification/pair_cbr/export-audit.json');output.parent.mkdir(parents=True,exist_ok=True)
output.write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))
