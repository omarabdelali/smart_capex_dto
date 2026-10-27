"""Rank historical cases with selected-feature Gower distance and kernels."""
from services.models.similarity.gower_distance import GowerDistance
from services.models.similarity.hierarchical_filter import HierarchicalFilter
from services.models.similarity.kernel_weights import KernelWeights
from services.models.similarity.weighting import pair_weights
from .calibration import policy,reference_ranges,available_weight_share
from services.models.features.road_loader import ROAD_FIELDS


def rank_similar_cases(query, candidates, k=10, min_pool_size=3, selected_features=None, weighting_mode='equal_per_feature', minimum_available_weight_share=None, feature_ranges=None, strict_selection=False):
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
    if not indices:
        return {'cases':[],'filter_level':level,'active_features':[],'excluded_features':{},
            'filter_explanation':'No cases match the mandatory event type and tier scheme, with the requested technology/band policy.',
            'minimum_available_weight_share':policy()['minimum_available_weight_share'] if minimum_available_weight_share is None else minimum_available_weight_share,
            'rejected_cases':[],'reference':reference_ranges(query,[] ,feature_ranges)[1]}
    requested = [f for f in dict.fromkeys(selected_features if selected_features is not None else [f for f in all_features if f not in ROAD_FIELDS]) if f not in ('site_id','cluster_id','cluster_avg_users','tier_scheme')]
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

    threshold=policy()['minimum_available_weight_share'] if minimum_available_weight_share is None else float(minimum_available_weight_share)
    if not 0 <= threshold <= 1:
        raise ValueError('minimum_available_weight_share must be between 0 and 1')
    ranges,reference=reference_ranges(query,[candidates[i] for i in indices],feature_ranges)
    distance = GowerDistance(feature_ranges=ranges)
    if query.get('feature_as_of_date') or feature_ranges is not None:
        unsupported=[f for f in active_features if f in distance.NUMERIC_FEATURES and f not in ranges]
        active_features=[f for f in active_features if f not in unsupported]
        for f in unsupported:
            excluded[f]='unavailable_in_frozen_reference'
    masked={f:None for f in distance.NUMERIC_FEATURES if f not in ranges} if query.get('feature_as_of_date') or feature_ranges is not None else {}
    shares={i:available_weight_share(distance,query,{**candidates[i],**masked},query_available,weighting_mode) for i in indices}
    rejected=[{'site_id':candidates[i].get('site_id'),'available_weight_share':shares[i],
        'reason':'available_weight_share_below_threshold'} for i in indices if shares[i]+1e-12 < threshold]
    indices=[i for i in indices if shares[i]+1e-12 >= threshold]
    actual_weights = {index:pair_weights(distance,query,candidates[index],active_features,weighting_mode,strict_selection=strict_selection) for index in indices}
    if query.get('feature_as_of_date') or feature_ranges is not None:
        for i,weights in actual_weights.items():
            weights={f:w for f,w in weights.items() if f not in distance.NUMERIC_FEATURES or f in ranges}
            total=sum(weights.values())
            actual_weights[i]={f:w/total for f,w in weights.items()} if total else {}
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
        explanation = (hierarchical.explain_filtering(query,candidates,indices,level)+
            ' No cases satisfy the selected dimensions, frozen-reference support and minimum available-weight share.')
    return {
        'filter_level': level,
        'filter_explanation': explanation,
        'reference': reference, 'minimum_available_weight_share':threshold,'rejected_cases':rejected,
        'active_features': active_features,
        'excluded_features': excluded,
        'cases': [
            {
                'candidate_index': index,
                'available_weight_share':shares[index],
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
