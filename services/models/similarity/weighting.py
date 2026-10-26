"""Pair-specific, auditable feature weights with an optional road budget."""
from collections import Counter
from services.models.features.road_loader import ROAD_FIELDS, road_config

WEIGHTING_MODES = ('equal_per_feature', 'equal_per_group')


def pair_weights(distance, query, candidate, selected, mode):
    if mode not in WEIGHTING_MODES:
        raise ValueError('Unknown weighting mode')
    common = [f for f in distance.NUMERIC_FEATURES+distance.CATEGORICAL_FEATURES
              if f not in ('site_id','cluster_id','cluster_avg_users')
              and not distance._is_missing(query.get(f)) and not distance._is_missing(candidate.get(f))]
    roads_compatible = bool(query.get('road_context_signature')) and query.get('road_context_signature') == candidate.get('road_context_signature')
    common = [f for f in common if f not in ROAD_FIELDS or (f in selected and roads_compatible)]
    common = [f for f in common if distance._get_feature_group(f) != 'user_context' or f in selected]
    common = [f for f in common if f != 'terrain_relief_class' or f in selected]
    if mode == 'equal_per_group':
        common = [f for f in common if f in selected]
        groups = Counter(distance._get_feature_group(f) for f in common)
        weights = {f:1/groups[distance._get_feature_group(f)] for f in common}
    else:
        # Preserve the existing non-road fallback behavior until production.
        custom = {f:1.0 for f in selected}
        weights = {f:distance._get_feature_weight(f,custom) for f in common}
    road_weight = sum(w for f,w in weights.items() if f in ROAD_FIELDS)
    other_weight = sum(w for f,w in weights.items() if f not in ROAD_FIELDS)
    if road_weight:
        if not other_weight or not any(f in selected and f not in ROAD_FIELDS for f in common):
            return {}  # Roads alone must not become 100% of the distance.
        cap = road_config()['road_group_weight_cap']
        allowed = other_weight*cap/(1-cap)
        if road_weight > allowed:
            weights = {f:(w*allowed/road_weight if f in ROAD_FIELDS else w) for f,w in weights.items()}
    total = sum(weights.values())
    return {f:w/total for f,w in weights.items() if w > 0} if total else {}
