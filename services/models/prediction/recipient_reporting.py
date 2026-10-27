"""Readable evidence from saved validation; no refitting or model promotion."""
from collections import defaultdict,Counter
from datetime import date
import json
from pathlib import Path
from django.conf import settings
from services.models.features.neighborhood import offset
from .pair_validation import errors
from .recipient_uncertainty import prediction_radius
from .recipient_data import policy


def write_recipient_report(path):
    path=Path(path);report=json.loads(path.read_text(encoding='utf-8'));base=path.parent
    artifact=Path(settings.BASE_DIR)/policy()['calibration_path']
    records=json.loads(artifact.read_text(encoding='utf-8'))['records']
    groups=defaultdict(list);recent={}
    for row in records:
        key=(row['metric'],row['horizon'],row['event_type'],row['tier_scheme'],row['method'],row.get('requested_ramp',row['ramp']))
        groups[key].append(row)
        event_date=offset(date.fromisoformat(row['available_month']),-row['horizon']).isoformat()
        identity=(row['event_type'],row['tier_scheme'])
        if identity not in recent or recent[identity]['event_date']<event_date:
            recent[identity]={'event_type':row['event_type'],'tier_scheme':row['tier_scheme'],
                'event_date':event_date,'event_site_id':row['event_site_id']}
    stratified=[];readiness=[]
    for key,values in groups.items():
        metric,horizon,event_type,scheme,method,ramp=key
        baseline=groups[metric,horizon,event_type,scheme,'pair_cbr',False]
        lookup={(r['event_key'],r['recipient_site_id']):r for r in baseline}
        common=[r for r in values if (r['event_key'],r['recipient_site_id']) in lookup]
        stratified.append({'metric':metric,'horizon':horizon,'event_type':event_type,'tier_scheme':scheme,'method':method,'ramp':ramp,
            'baseline_common_support':errors([lookup[r['event_key'],r['recipient_site_id']] for r in common]),'method_common_support':errors(common)})
        query=recent[event_type,scheme]
        radius,status=prediction_radius(query,metric,horizon,method,ramp)
        readiness.append({'query':query,'metric':metric,'horizon':horizon,'method':method,'ramp':ramp,
            'radius':radius,**status})
    (base/'stratified-comparisons.json').write_text(json.dumps(stratified,indent=2),encoding='utf-8')
    (base/'interval-readiness.json').write_text(json.dumps({'scope':'Latest sampled recorded event per type/scheme; real event cutoffs and origin exclusion',
        'ready':sum(r['status']=='available' for r in readiness),'checked':len(readiness),'records':readiness},indent=2),encoding='utf-8')
    def value(v):
        return 'Unavailable' if v is None else f'{v:,.3f}'
    text='''# Recipient CBR implementation and validation - 2026-10-27

The CBR impact page now exposes a recipient engine (Gaussian CBR, matched-control adjustment, local ridge and optional supported-horizon ramp) and a separate legacy site-launch benchmark. API: `/api/cbr/recipients/`. All domain logic is in services; no migration is required.

Raw CBR uses the median of three complete pre-event months. Control-adjusted CBR uses an explicitly separate three-month mean baseline. Historical targets begin at +1. Query control growth is extrapolated from six pre-event months; future control outcomes never enter a forecast. Controls require matched LTE bands/scheme/load/trend, a six-month exposure washout, a 10 km exclusion and at least three controls; later exposure censors controls/recipients. Matching does not establish parallel trends or causality.

Intervals distinguish a conditional mean interval from an individual prediction interval. The mean uses 500 correlated physical-origin Poisson bootstrap draws: all actions and recipients of an origin share their draw across recipients/horizons. Prediction bands require prior dated residuals, matching dataset/model versions, at least 20 independent origins and a rolling coverage gate with at least 10 subsequent prior-origin checks. Missing bands remain unavailable. Aggregate prediction bands are not claimed.

## Data and actual checks

Rebuilt 143,103 pair cases / 3,737 events. All 82,986 bandwidth pairs now have bands derived from affected cells when event metadata omits them. All rows have geometry/band/event-magnitude inputs; incomplete load baselines stay NULL. Frozen global pair-range reference: `da75efb861e531f03920fca7`, independent of retrieval filters and selected strictly before query month. Export structure/hash checks cover every row; 143 traffic cases were independently checked, zero mismatches.

The rolling study sampled 260 events and one recipient per event (48 per event type where available; all 20 site-addition events). This is not validation of all 143,103 recipients. Same-month held event origins are purged from training and range fitting; the separate recipient-disjoint baseline also purges held recipient sites in both roles. Targets must be observed strictly before the held cutoff. Five KPIs, six horizons, 500 bootstrap draws, 5/10/15 km control sensitivity. The study evaluates factual forecast error, not the accuracy of an unobserved causal effect. It does not establish superiority over the legacy 95-field engine.

## Month +1, matched-case comparisons

Each row compares methods on exactly the same recipients. Lower MAE is better. Units: traffic GB/month, users, CQI, throughput kbit/s, latency ms.

| KPI | Alternative | Common pairs | Raw CBR MAE | Alternative MAE |
|---|---|---:|---:|---:|
'''
    for row in report['paired_comparisons']:
        if row['horizon']==1 and row['method']!='pair_cbr' and not row['ramp'] and not row['recipient_disjoint']:
            b=row['baseline_common_support'];a=row['method_common_support']
            text+=f"| {row['metric']} | {row['method']} | {a['n_pairs']} | {value(b['mae'])} | {value(a['mae'])} |\n"
    text+='''
## Month +1 availability and error on each method's own supported subset

Do not compare these MAEs directly when availability differs; use the matched-case table above.

| KPI | Method | Ramp | Recipient-disjoint | Supported / eligible | Availability | MAE |
|---|---|---|---|---:|---:|---:|
'''
    for row in report['results']:
        if row['horizon']==1:
            text+=f"| {row['metric']} | {row['method']} | {row['ramp']} | {row['recipient_disjoint']} | {row['n_pairs']} / {row['eligible_pairs']} | {row['prediction_availability']:.1%} | {value(row['mae'])} |\n"
    counts=Counter((r['radius_m'],r['status']) for r in report['control_sensitivity'])
    text+='\n## Control feasibility\n\n| Exclusion | Available query matches | Audited KPI/recipient combinations |\n|---|---:|---:|\n'
    for radius in (5000,10000,15000):
        available=counts[radius,'available'];total=available+counts[radius,'unavailable']
        text+=f'| {radius/1000:g} km | {available} | {total} |\n'
    text+='''
Control matching availability is distinct from forecast availability: a forecast additionally needs clean completed analog responses and independent-origin support. Reducing the exclusion radius cannot repair missing histories or later-event contamination. Retain the 10 km primary rule; do not automatically promote control/local/ramp methods. The matched-case results are mixed and do not demonstrate consistent improvement across KPIs.

## Operational limits

- Recorded events are supported; an undated planned scenario is not invented.
- Training covers standard recipients within 5 km and extended recipients within 10 km. Real-cluster members beyond that range are explicitly unsupported; incomplete cluster totals stay NULL.
- Traffic/users sum complete recipient forecasts. Observed ratio KPIs pool counters; predicted ratio summaries use fixed pre-event denominator weights because future exposures are unknown.
- Controls/matching and mean intervals are conditional on observed data and selected matches. Six-month washout, repeated/overlapping actions, unobserved changes and seasonal drift limit causal interpretation and future interval coverage.
- Pair-model features are separate from the 95-field site-similarity picker. This initial stratified sample is not a national accuracy guarantee.

## Reproduce

- `python manage.py build_pair_cases` (also freezes the recipient range reference)
- `python manage.py validate_recipient_cbr --events-per-type 48`
- `python manage.py summarize_recipient_cbr`
- `python manage.py shell -c "import runpy; runpy.run_path('scripts/audit_pair_cases.py')"`
- `python scripts/verify_recipient_cbr_browser.py` with backend 8000/frontend 3000.

Evidence: validation.json (all horizons and paired comparisons); stratified-comparisons.json (event type/scheme/horizon common-support scores); interval-readiness.json (actual historical cutoffs and gate reasons); browser.json and matched-control-ui.png; ../pair_cbr/export-audit.json. The interval calibration artifact is versioned by model and dataset hash. Policy/priors: config/recipient_cbr.json. Full formulas: feature_eng.md.
'''
    (base/'README.md').write_text(text,encoding='utf-8')
    return {'stratified_comparisons':len(stratified),'interval_strata_checked':len(readiness),
        'interval_strata_ready':sum(r['status']=='available' for r in readiness)}
