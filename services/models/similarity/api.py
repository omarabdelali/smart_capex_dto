"""Read-only endpoint for retrieving similar historical site events."""
from django.db.models import Max

from core.models import MAOSMonthlyKPI, Site
from services.models.similarity import build_site_similarity_vector, rank_similar_cases
from services.models.similarity.gower_distance import GowerDistance
from services.models.similarity.historical import month_offset
from services.models.features.road_loader import ROAD_FIELDS, ROAD_LABELS
from services.models.similarity.weighting import WEIGHTING_MODES
from services.models.features.maos_context import USER_CONTEXT_LABELS
from services.models.preprocessing.network_events import effective_event_date
from services.models.similarity.availability import feature_statuses


from .context import candidate_context
from .pca import prepare_pca, pca_options, rank_pca
from .catalog import DISPLAY_ONLY, PROFILE_FIELDS, SIMILARITY_FIELDS, OPTIONAL, CONTEXT_LABELS, POPULATION_LABELS


def result(data, status=200):
    return data, status

def _similarity_features(vector):
    return {
        field: None if GowerDistance._is_missing(vector.get(field)) else vector.get(field)
        for field in SIMILARITY_FIELDS
    }


def _profile(vector):
    return {field: vector.get(field) for field in PROFILE_FIELDS}


def search_similarity(params):
    representation = params.get('representation', 'original')
    if representation not in ('original', 'pca'):
        return result({'error': 'representation must be original or pca'}, status=400)
    site_id = params.get('site_id', '').strip()
    weighting_mode = params.get('weighting_mode', 'equal_per_feature')
    if weighting_mode not in WEIGHTING_MODES:
        return result({'error': 'weighting_mode must be equal_per_feature or equal_per_group'}, status=400)
    if not site_id:
        return result({'error': 'site_id is required'}, status=400)
    try:
        limit = int(params.get('k', 10))
    except (TypeError, ValueError):
        return result({'error': 'k must be an integer from 1 to 20'}, status=400)
    if not 1 <= limit <= 20:
        return result({'error': 'k must be an integer from 1 to 20'}, status=400)

    query_site = Site.objects.filter(site_id=site_id).prefetch_related('cells','network_events').first()
    if query_site is None:
        return result({'error': f'Site {site_id} was not found'}, status=404)

    latest_month = MAOSMonthlyKPI.objects.aggregate(month=Max('month_date'))['month']
    current_as_of = (
        month_offset(latest_month, 1)
        if latest_month else None
    )
    query_event_date = effective_event_date(query_site)
    query_vector = build_site_similarity_vector(
        query_site, as_of_date=query_event_date or current_as_of, allow_current_roads=True
    )

    requested_features = params.get('features')
    if requested_features is None:
        selected_features = [
            field for field in SIMILARITY_FIELDS
            if field not in OPTIONAL and not GowerDistance._is_missing(query_vector.get(field))
        ]
    else:
        selected_features = list(dict.fromkeys(
            field.strip() for field in requested_features.split(',') if field.strip()
        ))
        invalid_features = sorted(set(selected_features) - set(SIMILARITY_FIELDS))
        if invalid_features and representation == 'original':
            return result({
                'error': 'Unknown similarity feature(s).',
                'invalid_features': invalid_features,
            }, status=400)
        if not selected_features:
            return result(
                {'error': 'Select at least one available similarity feature.'},
                status=400,
            )

    candidates, candidate_vectors, all_candidate_count = candidate_context(query_site, query_vector, current_as_of)
    prepared = prepare_pca(query_vector, candidate_vectors) if representation == 'pca' else None
    if prepared is not None:
        if not prepared['report']['available']:
            return result({'error': prepared['report']['reason'], 'pca': prepared['report']}, status=422)
        expected_fit = params.get('pca_fit_id')
        if expected_fit and expected_fit != prepared['report']['fit_id']:
            return result({'error': 'Candidate data changed. Reload the PCA list before ranking.'}, status=409)
        allowed = {c['key'] for c in prepared['report']['components']} | (set(GowerDistance.CATEGORICAL_FEATURES) - DISPLAY_ONLY) | set(ROAD_FIELDS)
        if requested_features is None:
            selected_features = [c['key'] for c in prepared['report']['components']] + [f for f in GowerDistance.CATEGORICAL_FEATURES if f not in OPTIONAL and not GowerDistance._is_missing(query_vector.get(f))]
        invalid = set(selected_features) - allowed
        if invalid:
            return result({'error': 'Unknown PCA dimension(s).', 'invalid_features': sorted(invalid)}, status=400)
    ranking = (rank_pca(query_vector, candidate_vectors, prepared, selected_features, k=limit, weighting_mode=weighting_mode)
        if prepared is not None else rank_similar_cases(
        query_vector, candidate_vectors, k=limit, selected_features=selected_features, weighting_mode=weighting_mode))
    candidate_by_id = {site.site_id: site for site in candidates}

    cases = []
    for item in ranking['cases']:
        vector = item['features']
        site = candidate_by_id.get(vector.get('site_id'))
        if site is None:
            continue
        cases.append({
            'tier_scheme': vector.get('tier_scheme'),
            'neighborhood': vector.get('virtual_cluster_context'),
            'site_id': site.site_id,
            'site_name': site.site_name,
            'event_date': effective_event_date(site),
            'event_type': vector.get('event_type'),
            'technology': vector.get('tech_added') or None,
            'cluster_id': site.cluster_id,
            'distance': item['distance'],
            'similarity': item['similarity'],
            'weight': item['weight'],
            'profile_months_available': vector.get('pre_profile_months_available', 0),
            'profile_completeness': vector.get('pre_profile_completeness', 0),
            'profile': _profile(vector),
            'similarity_features': _similarity_features(vector),
            'feature_statuses': feature_statuses(site, vector),
            'cluster_prelaunch_support': vector.get('cluster_prelaunch_support'),
            'post_event_configuration_support': vector.get('post_event_configuration_support'),
            'dimension_values': item.get('dimension_values', _similarity_features(vector)),
            'feature_exclusions': item.get('feature_exclusions', {}),
            'used_features': item['used_features'],
            'feature_weights': item['feature_weights'],
            'road_context_note': vector.get('road_context_note'),
            'feature_timing_note': vector.get('feature_timing_note'),
            'population_quality': vector.get('population_quality'),
        })

    return result({
        'query': {
            'dimension_values': {**_similarity_features(query_vector), **(prepared['query_scores'] if prepared else {})},
            'tier_scheme': query_vector.get('tier_scheme'),
            'neighborhood': query_vector.get('virtual_cluster_context'),
            'site_id': query_site.site_id,
            'site_name': query_site.site_name,
            'event_date': query_event_date,
            'event_type': query_vector.get('event_type'),
            'technology': query_vector.get('tech_added') or None,
            'as_of_date': query_vector.get('feature_as_of_date'),
            'road_context_note': query_vector.get('road_context_note'),
            'feature_timing_note': query_vector.get('feature_timing_note'),
            'population_quality': query_vector.get('population_quality'),
            'profile_months_available': query_vector.get('pre_profile_months_available', 0),
            'profile_completeness': query_vector.get('pre_profile_completeness', 0),
            'profile': _profile(query_vector),
            'similarity_features': _similarity_features(query_vector),
            'feature_statuses': feature_statuses(query_site, query_vector, include_current=True),
            'cluster_prelaunch_support': query_vector.get('cluster_prelaunch_support'),
            'post_event_configuration_support': query_vector.get('post_event_configuration_support'),
        },
        'candidate_pool_size': prepared['report']['fit_rows'] if prepared else len(candidates),
        'filtered_candidate_pool_size': len(candidates),
        'total_detected_event_sites': all_candidate_count,
        'returned_count': len(cases),
        'filter_level': ranking['filter_level'],
        'filter_explanation': ranking['filter_explanation'],
        'selected_features': selected_features,
        'active_features': ranking['active_features'],
        'excluded_features': ranking['excluded_features'],
        'weighting_method': weighting_mode,
        'cases': cases,
        'mode': 'retrieval_only',
        'representation': representation,
        'pca': prepared['report'] if prepared else None,
    })


def feature_availability(params):
    representation = params.get('representation', 'original')
    if representation not in ('original', 'pca'):
        return result({'error': 'representation must be original or pca'}, status=400)
    site_id = params.get('site_id', '').strip()
    if not site_id:
        return result({'error': 'site_id is required'}, status=400)
    query_site = Site.objects.filter(site_id=site_id).prefetch_related('cells','network_events').first()
    if query_site is None:
        return result({'error': f'Site {site_id} was not found'}, status=404)

    latest_month = MAOSMonthlyKPI.objects.aggregate(month=Max('month_date'))['month']
    current_as_of = (
        month_offset(latest_month, 1)
        if latest_month else None
    )
    event_date = effective_event_date(query_site)
    vector = build_site_similarity_vector(query_site, as_of_date=event_date or current_as_of, allow_current_roads=True)
    statuses = feature_statuses(query_site, vector, include_current=True)
    distance = GowerDistance()
    features = [
        {
            'key': field,
            'group': distance._get_feature_group(field),
            'label': CONTEXT_LABELS.get(field,USER_CONTEXT_LABELS.get(field, ROAD_LABELS.get(field, POPULATION_LABELS.get(field, (field.replace('_', ' '), '')))))[0],
            'unit': CONTEXT_LABELS.get(field,USER_CONTEXT_LABELS.get(field, ROAD_LABELS.get(field, POPULATION_LABELS.get(field, ('', '')))))[1],
            'default_selected': field not in OPTIONAL,
            'value': None if GowerDistance._is_missing(vector.get(field)) else vector.get(field),
            'available': not GowerDistance._is_missing(vector.get(field)),
            **statuses[field],
        }
        for field in SIMILARITY_FIELDS
    ]
    if vector.get('tier_scheme')=='extended':
        for feature in features:
            feature['label']=feature['label'].replace('0-2 km','<5 km').replace('2-5 km','5-<10 km').replace('0–2 km','<5 km').replace('2–5 km','5-<10 km')
            if feature['key']=='population_tier1':
                feature['label']='Tier 1 population (<5 km)'
            elif feature['key']=='population_tier2':
                feature['label']='Tier 2 population (5-<10 km)'
    prepared = None
    if representation == 'pca':
        _, vectors, _ = candidate_context(query_site, vector, current_as_of)
        prepared = prepare_pca(vector, vectors)
        features = pca_options(vector, prepared, features) if prepared['report']['available'] else []
    return result({
        'representation': representation,
        'pca': prepared['report'] if prepared else None,
        'site_id': query_site.site_id,
        'site_name': query_site.site_name,
        'tier_scheme': vector.get('tier_scheme'),
        'neighborhood': vector.get('virtual_cluster_context'),
        'features': features,
        'as_of_date': vector.get('feature_as_of_date'),
        'event_date': event_date,
        'cluster_prelaunch_support': vector.get('cluster_prelaunch_support'),
        'post_event_configuration_support': vector.get('post_event_configuration_support'),
        'feature_timing_note': vector.get('feature_timing_note'),
        'population_quality': vector.get('population_quality'),
    })
