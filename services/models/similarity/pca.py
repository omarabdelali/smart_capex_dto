"""Candidate-only PCA for exploratory retrieval. Missing observations are never filled."""
from collections import Counter
import hashlib
import json
import math

import numpy as np
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

from .gower_distance import GowerDistance
from .hierarchical_filter import HierarchicalFilter
from .kernel_weights import KernelWeights
from .catalog import DISPLAY_ONLY, OPTIONAL
from services.models.features.road_loader import ROAD_FIELDS, road_config

POLICY = {'version': 'pca-v1', 'variance_target': .90, 'minimum_feature_coverage': .95,
          'minimum_complete_fraction': .50, 'minimum_rows': 3}
ANGLES = {'terrain_aspect_deg', 'dominant_sector_deg'}


def finite(value):
    return isinstance(value, (int, float, np.number)) and math.isfinite(float(value))


def prepare_pca(query, candidates, min_pool_size=3):
    """Fit using candidates only; query availability chooses the usable source mask.

    Retain >=95%-observed columns and complete rows. If their intersection keeps
    <50% of the pool, remove the column whose removal restores the most rows.
    Thresholds are explicit priors. No imputation, whitening or categorical coding.
    """
    hierarchy = HierarchicalFilter(min_pool_size=min_pool_size)
    indices, level = hierarchy.filter_cases(query, candidates, return_filter_level=True)
    pool = [candidates[i] for i in indices]
    excluded, sources = {}, []
    for key in GowerDistance.NUMERIC_FEATURES:
        reason = None
        if key in DISPLAY_ONLY or key in ROAD_FIELDS:
            reason = 'display_only' if key in DISPLAY_ONLY else 'road_budget_kept_separate'
        elif not finite(query.get(key)):
            reason = 'unavailable_for_query'
        elif not pool or sum(finite(row.get(key)) for row in pool) / len(pool) < POLICY['minimum_feature_coverage']:
            reason = 'candidate_coverage_below_95_percent'
        else:
            observed = [row[key] for row in pool if finite(row.get(key))]
            if np.ptp(observed) <= 1e-12:
                reason = 'constant_in_candidate_pool'
        if reason:
            excluded[key] = reason
        else:
            sources.append(key)

    def complete(fields):
        return [i for i in indices if all(finite(candidates[i].get(f)) for f in fields)]

    required = max(POLICY['minimum_rows'], math.ceil(len(pool) * POLICY['minimum_complete_fraction']))
    while len(sources) > 1 and len(complete(sources)) < required:
        drop = max(sources, key=lambda f: (len(complete([s for s in sources if s != f])),
                                          sum(not finite(r.get(f)) for r in pool), f))
        sources.remove(drop)
        excluded[drop] = 'removed_to_preserve_complete_row_coverage'
    kept = complete(sources) if sources else []
    report = {'policy': POLICY, 'source_features': sources, 'excluded_features': excluded,
              'candidate_pool_size': len(pool), 'fit_rows': len(kept),
              'excluded_candidate_count': len(pool) - len(kept),
              'excluded_candidate_site_ids': [candidates[i].get('site_id') for i in indices if i not in kept],
              'fit_site_ids': [candidates[i].get('site_id') for i in kept],
              'missing_policy': 'Complete rows only; no imputation. Sparse/constant fields are reported separately.',
              'fit_scope': 'Filtered candidate event profiles only; query values never fit scaling or PCA. Retrieval only, not CBR prediction.',
              'components': [], 'available': False}
    result = {'report': report, 'indices': kept, 'level': level, 'query_scores': {}, 'candidate_scores': {},
              'explanation': hierarchy.explain_filtering(query, candidates, indices, level)}
    if len(sources) < 2 or len(kept) < required:
        report['reason'] = 'PCA needs at least two varying numeric features and three complete candidates (at least 50% of the pool). Use Original features.'
        return result
    columns = [name for f in sources for name in ([f + '__sin', f + '__cos'] if f in ANGLES else [f])]

    def encode(row):
        values = []
        for f in sources:
            if f in ANGLES:
                angle = math.radians(row[f] % 360)
                values.extend([math.sin(angle), math.cos(angle)])
            else:
                values.append(float(row[f]))
        return values

    matrix = np.asarray([encode(candidates[i]) for i in kept])
    # Constant encoded columns (e.g. identical bearings modulo 360) carry no signal.
    varying = np.ptp(matrix, axis=0) > 1e-12
    if varying.sum() < 2:
        report['reason'] = 'Fewer than two varying encoded inputs remain. Use Original features.'
        return result
    matrix = matrix[:, varying]
    columns = [name for name, keep in zip(columns, varying) if keep]
    scaler = StandardScaler()
    standardized = scaler.fit_transform(matrix)
    model = PCA(svd_solver='full').fit(standardized)
    # Fix arbitrary component signs for reproducible labels and fingerprints.
    for component in model.components_:
        if component[np.argmax(np.abs(component))] < 0:
            component *= -1
    scores = model.transform(standardized)
    query_scores = model.transform(scaler.transform(np.asarray([encode(query)])[:, varying]))[0]
    cumulative = np.cumsum(model.explained_variance_ratio_)
    count = min(len(cumulative), int(np.searchsorted(cumulative, POLICY['variance_target']) + 1))
    report.update(available=True, encoded_features=columns, input_dimension=len(columns),
                  retained_dimension=count, retained_variance=float(cumulative[count - 1]),
                  scaler_mean=dict(zip(columns, scaler.mean_.tolist())),
                  scaler_scale=dict(zip(columns, scaler.scale_.tolist())))
    for j in range(count):
        key = f'PC{j + 1}'
        loadings = dict(zip(columns, model.components_[j].tolist()))
        low, high = np.percentile(scores[:, j], [5, 95])
        report['components'].append({'key': key, 'label': f'PC{j + 1}',
            'explained_variance_ratio': float(model.explained_variance_ratio_[j]),
            'cumulative_variance_ratio': float(cumulative[j]), 'loadings': loadings,
            'top_loadings': sorted(loadings.items(), key=lambda item: abs(item[1]), reverse=True)[:5],
            'range': [float(low), float(high)]})
        result['query_scores'][key] = float(query_scores[j])
    for position, index in enumerate(kept):
        result['candidate_scores'][index] = {f'PC{j + 1}': float(scores[position, j]) for j in range(count)}
    fingerprint = json.dumps({'policy': POLICY, 'columns': columns, 'ids': report['fit_site_ids'],
                              'matrix': matrix.tolist()}, sort_keys=True).encode()
    report['fit_id'] = hashlib.sha256(fingerprint).hexdigest()[:20]
    return result


def pca_options(query, prepared, original_options):
    options = []
    for component in prepared['report']['components']:
        top = ', '.join(f'{key}: {weight:+.3f}' for key, weight in component['top_loadings'])
        options.append({'key': component['key'], 'label': f"{component['key']} · {100 * component['explained_variance_ratio']:.1f}% variance",
            'group': 'pca', 'unit': 'component score', 'available': True, 'selectable': True,
            'default_selected': True, 'value': prepared['query_scores'][component['key']],
            'reason': f'Largest loadings: {top}'})
    for option in original_options:
        if option['key'] in ROAD_FIELDS or (option['key'] in GowerDistance.CATEGORICAL_FEATURES and option['key'] not in DISPLAY_ONLY):
            options.append(option)
    return options


def rank_pca(query, candidates, prepared, selected, k=10, weighting_mode='equal_per_feature'):
    """Gower-style robust score distance; categorical values stay categorical.

    PCA dimensions share one group in equal_per_group. Roads remain outside PCA,
    require matching provenance and non-road support, and consume <=5% weight.
    Only explicitly selected dimensions score in this new representation.
    """
    distance = GowerDistance()
    distance.fit_ranges([candidates[i] for i in prepared['indices']])
    components = {c['key']: c for c in prepared['report']['components']}
    query_values = {**query, **prepared['query_scores']}
    ranked = []
    for i in prepared['indices']:
        values = {**candidates[i], **prepared['candidate_scores'].get(i, {})}
        common = [f for f in selected if not distance._is_missing(query_values.get(f)) and not distance._is_missing(values.get(f))]
        compatible = query.get('road_context_signature') and query.get('road_context_signature') == values.get('road_context_signature')
        common = [f for f in common if f not in ROAD_FIELDS or compatible]
        if not any(f not in ROAD_FIELDS for f in common):
            continue
        groups = Counter('pca' if f in components else distance._get_feature_group(f) for f in common)
        weights = {f: 1 / groups['pca' if f in components else distance._get_feature_group(f)]
                   if weighting_mode == 'equal_per_group' else 1.0 for f in common}
        road = sum(w for f, w in weights.items() if f in ROAD_FIELDS)
        other = sum(w for f, w in weights.items() if f not in ROAD_FIELDS)
        cap = road_config()['road_group_weight_cap']
        factor = min(1., other * cap / (1 - cap) / road) if road else 1.
        weights = {f: w * (factor if f in ROAD_FIELDS else 1.) for f, w in weights.items()}
        total = sum(weights.values())
        weights = {f: w / total for f, w in weights.items()}
        deltas = {}
        for f in common:
            if f in components:
                low, high = components[f]['range']
                deltas[f] = min(1., abs(query_values[f] - values[f]) / (high - low)) if high > low else 0.
            else:
                deltas[f] = distance._compute_feature_distance(f, query_values[f], values[f])
        score = sum(weights[f] * deltas[f] for f in common)
        ranked.append({'candidate_index': i, 'features': candidates[i], 'distance': score,
                       'similarity': 1 - score, 'used_features': common, 'feature_weights': weights,
                       'feature_exclusions': {f: 'road_context_mismatch' for f in selected if f in ROAD_FIELDS and not compatible},
                       'dimension_values': {f: values.get(f) for f in selected}})
    ranked.sort(key=lambda item: (item['distance'], str(item['features'].get('site_id'))))
    ranked = ranked[:k]
    weights = KernelWeights(bandwidth_method='median').compute_weights([r['distance'] for r in ranked]) if ranked else []
    for item, weight in zip(ranked, weights):
        item['weight'] = float(weight)
    active = [f for f in selected if any(f in item['used_features'] for item in ranked)]
    return {'cases': ranked, 'active_features': active,
            'excluded_features': {f: 'unavailable_for_all_candidates' for f in selected if f not in active},
            'filter_level': prepared['level'], 'filter_explanation': prepared['explanation']}
