"""Small chronological, origin/recipient-purged pilot; no causal ground truth."""
from collections import defaultdict
import json
from pathlib import Path
import numpy as np
from core.models import AnalysisEpisode
from services.analysis_profiles import defaults
from services.models.features.neighborhood import offset
from .analysis_episodes import as_event
from .counterfactual_gains import gain_forecast,VERSION
from .matched_controls import MatchedControls
from .recipient_data import data_context


def validate_gains(output,events_per_type=1,progress=print):
    """Evaluate one nearest fixed recipient and the origin for each pilot episode."""
    data=data_context();groups=defaultdict(list)
    latest=max(month for history in data.history.values() for month in history)
    for episode in AnalysisEpisode.objects.filter(is_current=True,effective_date__lte=offset(latest,-3)).select_related('site'):
        groups[episode.event_type].append(episode)
    selected=[]
    for kind,episodes in sorted(groups.items()):
        # Recent episodes have mature training history; deterministic selection
        # is explicit, and this small diagnostic must not be called full validation.
        pool=sorted(episodes,key=lambda e:(e.effective_date,e.episode_key),reverse=True)
        selected+=pool[:events_per_type]
    records=[];controls=MatchedControls(data);choices=defaults()
    for episode in sorted(selected,key=lambda e:(e.effective_date,e.episode_key)):
        event=as_event(episode)
        for scope in ('tier1','origin'):
            _,queries=data.query_pairs(episode.site,event,scope)
            if not queries:
                continue
            key=min(queries,key=lambda q:(q['distance_m'],q['recipient_site_id']))['recipient_site_id']
            result=gain_forecast(episode.site,event,scope=scope,data=data,horizon=3,profile_settings=choices,
                recipient_ids=[key],recipient_disjoint=True)
            for recipient in result['recipients']:
                for point in recipient['points']:
                    h=point['horizon']
                    if h not in (1,3):
                        continue
                    # Post-cutoff information is used only for held-out scoring.
                    effect,diagnostic=controls.effect(key,event.effective_date,'downlink_traffic_gb',h)
                    eligible=effect is not None and point['observed'] is not None
                    records.append({'episode_key':episode.episode_key,'event_type':event.event_type,
                        'event_date':event.effective_date.isoformat(),'role':recipient['recipient_role'],
                        'recipient':key,'horizon':h,'predicted_with_event':point['with_event_forecast'],
                        'observed_with_event':point['observed'] if eligible else None,
                        'persistence':point['last_month_forecast'],'predicted_gain':point['monthly_gain'],
                        'heldout_did_proxy':effect,'score_eligible':eligible,
                        'reason':diagnostic.get('reason') or point['support'].get('reason')})
        progress(f'Gain pilot {episode.episode_key[:10]} {event.effective_date} {event.event_type}')
    scores=[]
    for role in ('origin','neighbor'):
        for h in (1,3):
            rows=[r for r in records if r['role']==role and r['horizon']==h]
            common=[r for r in rows if r['score_eligible'] and all(r.get(f) is not None for f in ('predicted_with_event','observed_with_event','persistence'))]
            mae=lambda field:float(np.mean([abs(r[field]-r['observed_with_event']) for r in common])) if common else None
            scores.append({'role':role,'horizon':h,'attempted':len(rows),'common_cases':len(common),
                'with_event_mae':mae('predicted_with_event'),'persistence_mae':mae('persistence'),
                'gain_vs_heldout_did_proxy_mae':float(np.mean([abs(r['predicted_gain']-r['heldout_did_proxy']) for r in common])) if common else None})
    report={'version':VERSION,'study':'Small deterministic recent-episode pilot, not full validation or tuning',
        'sampling':{'events_per_type':events_per_type,'episodes':len(selected),'recipients':'nearest eligible T1 recipient and origin'},
        'validation':'Only earlier episodes/completed labels; query origin and recipient purged from training. Later exposure censors held-out scoring.',
        'interpretation':'Observed post-event levels assess predictive accuracy. Held-out DiD is an observational proxy, not causal gain ground truth. No calibration/default promotion.',
        'scores':scores,'records':records}
    path=Path(output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    return {k:v for k,v in report.items() if k!='records'}
