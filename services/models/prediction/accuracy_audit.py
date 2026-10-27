"""Matched-case CBR skill audit against pre-event-only forecasting baselines."""
from collections import defaultdict
from datetime import date
import json
from pathlib import Path
import numpy as np
from django.conf import settings
from services.models.features.neighborhood import offset
from .cbr_impact import _month_rows,_row_value
from .matched_controls import complete
from .pair_validation import errors


def comparison_metrics(actual,predicted,benchmark):
    error=abs(predicted-actual) if actual is not None and predicted is not None else None
    baseline_error=abs(benchmark-actual) if actual is not None and benchmark is not None else None
    return {'absolute_error':error,'absolute_percentage_error':error/abs(actual)*100 if error is not None and actual!=0 else None,
        'benchmark_absolute_error':baseline_error,
        'beats_last_month':error<baseline_error if error is not None and baseline_error is not None else None}


def baseline_forecasts(history,cutoff,metric,horizon):
    pre=[_row_value(history.get(offset(cutoff,k)),metric) for k in (-3,-2,-1)]
    result={'median_3m':float(np.median(pre)) if complete(pre) else None,
        'last_month':pre[-1]}
    six=[_row_value(history.get(offset(cutoff,k)),metric) for k in range(-6,0)]
    if complete(six):
        coef=np.polyfit(np.arange(-6,0),six,1)
        result['linear_trend_6m']=float(np.polyval(coef,horizon))
    else:
        result['linear_trend_6m']=None
    seasonal=offset(cutoff,horizon-12)
    result['seasonal_last_year']=_row_value(history.get(seasonal),metric) if seasonal<cutoff else None
    ceiling=15 if metric=='cqi_avg' else float('inf')
    return {k:float(min(ceiling,max(0.,v))) if v is not None else None for k,v in result.items()}


def audit_accuracy(output='docs/verification/recipient_cbr/accuracy-audit.json'):
    root=Path(settings.BASE_DIR)
    artifact=json.loads((root/'data/calibration/recipient_intervals.json').read_text(encoding='utf-8'))
    history=_month_rows();records=[];seen=set()
    for row in artifact['records']:
        if row['method']!='pair_cbr' or row.get('requested_ramp',row['ramp']):
            continue
        key=(row['event_key'],row['recipient_site_id'],row['metric'],row['horizon'])
        if key in seen:
            continue
        seen.add(key)
        cutoff=offset(date.fromisoformat(row['available_month']),-row['horizon'])
        baselines=baseline_forecasts(history.get(row['recipient_site_id'],{}),cutoff,row['metric'],row['horizon'])
        median=baselines['median_3m']
        records.append({**row,'event_date':cutoff.isoformat(),'baselines':baselines,
            'observed_change':row['actual']-median if median is not None else None,
            'predicted_change':row['predicted']-median if median is not None else None})
    groups=defaultdict(list)
    for row in records:
        groups[row['metric'],row['horizon']].append(row)
    summary=[];largest=[]
    for (metric,horizon),values in sorted(groups.items()):
        for name in ('median_3m','last_month','linear_trend_6m','seasonal_last_year'):
            common=[r for r in values if r['baselines'][name] is not None]
            analog=errors(common)
            baseline=errors([{**r,'predicted':r['baselines'][name]} for r in common])
            denominator=sum(abs(r['actual']) for r in common)
            summary.append({'metric':metric,'horizon':horizon,'baseline':name,
                'cbr':analog,'comparison':baseline,
                'cbr_skill_mae':1-analog['mae']/baseline['mae'] if baseline['mae'] else None,
                'cbr_wape':sum(abs(r['error']) for r in common)/denominator if denominator else None,
                'baseline_wape':sum(abs(r['baselines'][name]-r['actual']) for r in common)/denominator if denominator else None,
                'cbr_bias':float(np.mean([r['predicted']-r['actual'] for r in common])) if common else None})
        largest.extend(sorted(values,key=lambda r:abs(r['error']),reverse=True)[:10])
    report={'model_version':artifact['model_version'],'dataset_sha256':artifact['dataset_sha256'],
        'source':'Saved rolling out-of-sample forecasts; no refitting or future inputs in baseline construction',
        'interpretation':'Positive skill beats the baseline; negative skill is worse. Actual minus baseline is observed change, not causal impact.',
        'comparisons':summary,'largest_misses_by_kpi_horizon':largest}
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    calibration=root/'data/calibration/recipient_accuracy.json'
    calibration.parent.mkdir(parents=True,exist_ok=True)
    calibration.write_text(json.dumps({k:report[k] for k in ('model_version','dataset_sha256','source','comparisons')},indent=2),encoding='utf-8')
    text='# CBR accuracy audit - 2026-10-27\n\nMatched out-of-sample cases; positive MAE skill means CBR beats the comparator. Baselines use pre-event data only. This audit does not establish causal impact.\n\n| KPI | Horizon | Comparator | Cases | CBR MAE | Comparator MAE | CBR skill |\n|---|---:|---|---:|---:|---:|---:|\n'
    for row in summary:
        if row['baseline'] in ('median_3m','last_month'):
            a,b=row['cbr'],row['comparison'];skill=row['cbr_skill_mae']
            if a['mae'] is not None and b['mae'] is not None:
                text+=f"| {row['metric']} | +{row['horizon']} | {row['baseline']} | {a['n_pairs']} | {a['mae']:.3f} | {b['mae']:.3f} | {skill:.1%} |\n" if skill is not None else ''
    text+='\nFull trend/seasonal comparisons, bias, WAPE and largest misses: accuracy-audit.json. No production model or weights were changed by this audit.\n'
    output.with_suffix('.md').write_text(text,encoding='utf-8')
    return report
