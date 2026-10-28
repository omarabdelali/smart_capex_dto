"""Shared template resolution and mixed-feature case ranking.

Callers prepare their own explicitly time-valid cases and retain the matching
event metadata. This service never invents observations or outcomes.
"""
from services.models.features.road_loader import ROAD_FIELDS
from .catalog import SIMILARITY_FIELDS, DISPLAY_ONLY, OPTIONAL
from .engine import rank_similar_cases
from .gower_distance import GowerDistance
from .pca import prepare_pca, rank_pca


class CaseSelectionError(ValueError):
    def __init__(self, payload, status=400):
        super().__init__(payload.get('error','Case selection failed.'))
        self.payload=payload
        self.status=status


def eligible_events(events,cutoff,excluded_physical_id=None):
    """Return unique physical-site/month/type cases strictly before cutoff.

    Outcome availability is a separate check for prediction. This filter alone
    does not assert that an event has a completed outcome at a given horizon.
    """
    unique={}
    for event in events:
        when=event.effective_date
        physical=event.site.canonical_site_id or event.site.site_id
        if not event.is_current or when is None or when>=cutoff or physical==excluded_physical_id:
            continue
        unique.setdefault((physical,when,event.event_type),event)
    return list(unique.values())


def resolve_template(actor,params,query):
    """Resolve the same similarity template for every ranking consumer."""
    from services.analysis_profiles import resolve_profile
    settings,metadata,error=resolve_profile(actor,'similarity',params,{
        'event_type':query.get('event_type'),'tier_scheme':query.get('tier_scheme'),
        'technology':query.get('_event_technologies') or query.get('tech_added')})
    if error:
        raise CaseSelectionError(error[0],error[1])
    return settings,metadata


def rank_cases(query,candidates,*,selected_features=None,profile_settings=None,
               representation='original',weighting_mode='equal_per_feature',
               minimum_available_weight_share=.6,allow_filter_relaxation=True,
               limit=10,strict_selection=False,expected_fit_id=None):
    """Rank already prepared cases with identical template semantics.

    PCA is fitted only on the supplied eligible candidates. Candidate indices in
    the result refer to the input list; callers own event dates and cutoff checks.
    """
    if representation not in ('original','pca'):
        raise CaseSelectionError({'error':'representation must be original or pca'})
    query={**query,'_allow_filter_relaxation':bool(allow_filter_relaxation)}
    requested=None if selected_features is None else list(dict.fromkeys(selected_features))
    if requested is not None and not requested:
        raise CaseSelectionError({'error':'Select at least one available similarity feature.'})
    if requested is not None and representation=='original':
        invalid=sorted(set(requested)-set(SIMILARITY_FIELDS))
        if invalid:
            raise CaseSelectionError({'error':'Unknown similarity feature(s).','invalid_features':invalid})
    selected=requested if requested is not None else [f for f in SIMILARITY_FIELDS
        if f not in OPTIONAL and not GowerDistance._is_missing(query.get(f))]
    prepared=None
    if representation=='pca':
        prepared=prepare_pca(query,candidates,
            source_features=profile_settings['similarity_features'] if profile_settings else None,
            variance_target=profile_settings['pca_variance_target'] if profile_settings else None)
        if not prepared['report']['available']:
            raise CaseSelectionError({'error':prepared['report']['reason'],'pca':prepared['report']},422)
        if expected_fit_id and expected_fit_id!=prepared['report']['fit_id']:
            raise CaseSelectionError({'error':'Candidate data changed. Reload the PCA list before ranking.'},409)
        allowed={c['key'] for c in prepared['report']['components']} | (set(GowerDistance.CATEGORICAL_FEATURES)-DISPLAY_ONLY) | set(ROAD_FIELDS)
        if requested is None:
            selected=[c['key'] for c in prepared['report']['components']] + [f for f in GowerDistance.CATEGORICAL_FEATURES
                if f not in DISPLAY_ONLY and (f in profile_settings['similarity_features'] if profile_settings else f not in OPTIONAL)
                and not GowerDistance._is_missing(query.get(f))]
            if profile_settings:
                selected += [f for f in ROAD_FIELDS if f in profile_settings['similarity_features'] and f not in selected
                    and not GowerDistance._is_missing(query.get(f))]
        invalid=sorted(set(selected)-allowed)
        if invalid:
            raise CaseSelectionError({'error':'Unknown PCA dimension(s).','invalid_features':invalid})
        ranking=rank_pca(query,candidates,prepared,selected,k=limit,weighting_mode=weighting_mode,
            minimum_available_weight_share=minimum_available_weight_share)
    else:
        ranking=rank_similar_cases(query,candidates,k=limit,selected_features=selected,weighting_mode=weighting_mode,
            minimum_available_weight_share=minimum_available_weight_share,strict_selection=strict_selection)
    return {'query':query,'ranking':ranking,'selected_features':selected,'prepared':prepared}
