"""Rank historical cases with selected-feature Gower distance and kernels."""
from services.models.similarity.gower_distance import GowerDistance
from services.models.similarity.hierarchical_filter import HierarchicalFilter
from services.models.similarity.kernel_weights import KernelWeights
from services.models.similarity.weighting import pair_weights
from services.models.features.road_loader import ROAD_FIELDS


def rank_similar_cases(query, candidates, k=10, min_pool_size=3, selected_features=None, weighting_mode='equal_per_feature'):
    """Rank cases over selected, available dimensions using equal feature weights."""
    all_features = GowerDistance.NUMERIC_FEATURES + GowerDistance.CATEGORICAL_FEATURES
    if not candidates:
        return {
            'cases': [], 'filter_level': 0,
            'filter_explanation': 'No candidate cases are available.',
            'active_features': [], 'excluded_features': {},
        }

    hierarchical = HierarchicalFilter(min_pool_size=min_pool_size)
    indices, level = hierarchical.filter_cases(query, candidates, return_filter_level=True)
    requested = list(dict.fromkeys(selected_features if selected_features is not None else [f for f in all_features if f not in ROAD_FIELDS]))
    excluded = {}
    query_available = []
    for feature in requested:
        if GowerDistance._is_missing(query.get(feature)):
            excluded[feature] = 'unavailable_for_query'
        else:
            query_available.append(feature)

    active_features = [
        feature for feature in query_available
        if any(not GowerDistance._is_missing(candidates[index].get(feature)) for index in indices)
    ]
    for feature in query_available:
        if feature not in active_features:
            excluded[feature] = 'unavailable_for_all_candidates'
    for feature in all_features:
        if feature not in requested:
            excluded[feature] = 'not_selected'
    if not active_features:
        return {
            'cases': [], 'filter_level': level,
            'filter_explanation': 'No selected features are available for comparison.',
            'active_features': [], 'excluded_features': excluded,
        }

    distance = GowerDistance()
    distance.fit_ranges([
        candidates[index] if query.get('road_context_signature') and query.get('road_context_signature') == candidates[index].get('road_context_signature')
        else {**candidates[index], **dict.fromkeys(ROAD_FIELDS)} for index in indices
    ])
    actual_weights = {index:pair_weights(distance,query,candidates[index],active_features,weighting_mode) for index in indices}
    ranked = sorted(
        (
            (index, distance.compute_distance(
                query, candidates[index], feature_weights={feature:actual_weights[index].get(feature,0.0) for feature in all_features}
            ))
            for index in indices if actual_weights[index]
        ),
        key=lambda item: item[1],
    )[:min(max(1, int(k)), len(indices))]
    weights = KernelWeights(bandwidth_method='median').compute_weights([item[1] for item in ranked]) if ranked else []
    explanation = hierarchical.explain_filtering(query, candidates, indices, level)
    if not ranked:
        explanation = 'No comparable cases. Roads require a matching source/buffer/method and at least one selected non-road feature.'
    return {
        'filter_level': level,
        'filter_explanation': explanation,
        'active_features': active_features,
        'excluded_features': excluded,
        'cases': [
            {
                'candidate_index': index,
                'distance': float(dist),
                'similarity': float(1 - dist),
                'weight': float(weights[pos]),
                'features': candidates[index],
                'used_features': [
                    feature for feature in actual_weights[index]
                ],
                'feature_weights': actual_weights[index],
                'feature_exclusions': {f:'road_context_mismatch' for f in active_features if f in ROAD_FIELDS
                                       and f not in actual_weights[index] and not distance._is_missing(candidates[index].get(f))},
            }
            for pos, (index, dist) in enumerate(ranked)
        ],
    }
