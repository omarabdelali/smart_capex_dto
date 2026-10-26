"""Run through manage.py shell; real candidate availability and PCA diagnostics."""
import json
from datetime import date
from pathlib import Path
import numpy as np
from django.db.models import Q, Max
from core.models import Site, MAOSMonthlyKPI
from services.models.similarity.feature_vector import build_site_similarity_vector
from services.models.similarity.historical import month_offset
from services.models.similarity.gower_distance import GowerDistance
from services.models.similarity.pca import prepare_pca, rank_pca
from services.models.preprocessing.network_events import effective_event_date


def run():
    directory = Path('docs/verification/similarity_pca')
    directory.mkdir(parents=True, exist_ok=True)
    sites = Site.objects.filter(Q(is_launched=True, launch_date__isnull=False) | Q(cells__is_launched=True, cells__launch_date__isnull=False)).distinct().select_related(
        'config_features','geometric_features','clutter_features','spatial_features','anp_features','cluster_features','prelaunch_kpi','road_features','user_context_features').prefetch_related('cells','network_events').order_by('site_id')
    cutoff = month_offset(MAOSMonthlyKPI.objects.aggregate(value=Max('month_date'))['value'], 1)
    vectors, cache = [], {}
    for index, site in enumerate(sites, 1):
        vectors.append(build_site_similarity_vector(site, as_of_date=effective_event_date(site) or cutoff, snapshot_cache=cache, allow_current_roads=True))
        if index % 50 == 0:
            print(f'Profiles reviewed: {index}', flush=True)
    fields = GowerDistance.NUMERIC_FEATURES + GowerDistance.CATEGORICAL_FEATURES
    availability = {}
    for field in fields:
        values = [row[field] for row in vectors if not GowerDistance._is_missing(row.get(field))]
        availability[field] = {'available': len(values), 'missing': len(vectors) - len(values), 'distinct': len(set(values))}
    correlations = []
    numeric = GowerDistance.NUMERIC_FEATURES
    for i, left in enumerate(numeric):
        for right in numeric[i+1:]:
            pairs = [[r[left], r[right]] for r in vectors if not GowerDistance._is_missing(r.get(left)) and not GowerDistance._is_missing(r.get(right))]
            if len(pairs) < 20:
                continue
            matrix = np.asarray(pairs)
            if (np.ptp(matrix, axis=0) <= 1e-12).any():
                continue
            correlation = float(np.corrcoef(matrix.T)[0, 1])
            if abs(correlation) >= .95:
                correlations.append({'left': left, 'right': right, 'pearson_r': correlation, 'paired_rows': len(pairs)})
    query = next(row for row in vectors if row['site_id'] == '6306')
    candidates = [row for row in vectors if row['site_id'] != '6306']
    prepared = prepare_pca(query, candidates)
    selected = [c['key'] for c in prepared['report']['components']] + ['event_type', 'dominant_clutter']
    ranked = rank_pca(query, candidates, prepared, selected)
    report = {'date': str(date.today()), 'profiles': len(vectors), 'declared_fields': len(fields), 'availability': availability,
              'high_correlations': correlations, 'pca_example_site': '6306', 'pca': prepared['report'],
              'top_cases': [{k: v for k,v in r.items() if k != 'features'} for r in ranked['cases']]}
    (directory/'review.json').write_text(json.dumps(report, indent=2, default=str), encoding='utf-8')
    (directory/'vectors.json').write_text(json.dumps(vectors, default=str), encoding='utf-8')
    print(json.dumps({'profiles': len(vectors), 'all_missing': [f for f,v in availability.items() if not v['available']],
        'constant_observed': [f for f,v in availability.items() if v['distinct']==1], 'high_correlations':len(correlations),
        'pca': {k:v for k,v in prepared['report'].items() if k in ('available','reason','input_dimension','retained_dimension','retained_variance','fit_rows','candidate_pool_size','fit_id')}}, indent=2))


run()
