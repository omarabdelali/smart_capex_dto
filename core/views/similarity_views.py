"""Read-only endpoint for retrieving similar historical site events."""
from django.db.models import Max, Min, Q
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import Cell, MAOSMonthlyKPI, Site
from services.models.similarity import build_site_similarity_vector, rank_similar_cases
from services.models.similarity.gower_distance import GowerDistance
from services.models.similarity.historical import month_offset
from services.models.features.road_loader import ROAD_FIELDS, ROAD_LABELS
from services.models.similarity.weighting import WEIGHTING_MODES


PROFILE_FIELDS = (
    'pre_dl_traffic_gb_day', 'pre_active_users', 'pre_traffic_users',
    'pre_prb_util_dl_pct', 'pre_cqi_avg', 'pre_dl_throughput_kbps',
    'pre_dl_packet_delay_ms', 'pre_cell_availability_pct',
    'pre_traffic_trend_3m_pct', 'pre_prb_trend_3m_pct',
)
SIMILARITY_FIELDS = GowerDistance.NUMERIC_FEATURES + GowerDistance.CATEGORICAL_FEATURES
POPULATION_LABELS = {
    'population_density_1km_per_km2': ('Population density (1 km)', 'people/km²'),
    'population_tier1': ('Tier 1 population (0–2 km)', 'people'),
    'population_tier2': ('Tier 2 population (2–5 km)', 'people'),
}


def _similarity_features(vector):
    return {
        field: None if GowerDistance._is_missing(vector.get(field)) else vector.get(field)
        for field in SIMILARITY_FIELDS
    }


def _profile(vector):
    return {field: vector.get(field) for field in PROFILE_FIELDS}


class SimilaritySearchView(APIView):
    """Find launched or detected-addition sites closest to the requested site."""

    def get(self, request):
        site_id = request.query_params.get('site_id', '').strip()
        weighting_mode = request.query_params.get('weighting_mode', 'equal_per_feature')
        if weighting_mode not in WEIGHTING_MODES:
            return Response({'error': 'weighting_mode must be equal_per_feature or equal_per_group'}, status=400)
        if not site_id:
            return Response({'error': 'site_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            limit = int(request.query_params.get('k', 10))
        except (TypeError, ValueError):
            return Response({'error': 'k must be an integer from 1 to 20'}, status=status.HTTP_400_BAD_REQUEST)
        if not 1 <= limit <= 20:
            return Response({'error': 'k must be an integer from 1 to 20'}, status=status.HTTP_400_BAD_REQUEST)

        query_site = Site.objects.filter(site_id=site_id).first()
        if query_site is None:
            return Response({'error': f'Site {site_id} was not found'}, status=status.HTTP_404_NOT_FOUND)

        event_dates = dict(
            Cell.objects.filter(is_launched=True, launch_date__isnull=False)
            .values('site_id').annotate(event_date=Min('launch_date'))
            .values_list('site_id', 'event_date')
        )
        latest_month = MAOSMonthlyKPI.objects.aggregate(month=Max('month_date'))['month']
        current_as_of = (
            month_offset(latest_month, 1)
            if latest_month else None
        )
        query_event_date = query_site.launch_date or event_dates.get(query_site.pk)
        query_vector = build_site_similarity_vector(
            query_site, as_of_date=query_event_date or current_as_of, allow_current_roads=True
        )

        requested_features = request.query_params.get('features')
        if requested_features is None:
            selected_features = [
                field for field in SIMILARITY_FIELDS
                if field not in ROAD_FIELDS and not GowerDistance._is_missing(query_vector.get(field))
            ]
        else:
            selected_features = list(dict.fromkeys(
                field.strip() for field in requested_features.split(',') if field.strip()
            ))
            invalid_features = sorted(set(selected_features) - set(SIMILARITY_FIELDS))
            if invalid_features:
                return Response({
                    'error': 'Unknown similarity feature(s).',
                    'invalid_features': invalid_features,
                }, status=status.HTTP_400_BAD_REQUEST)
            if not selected_features:
                return Response(
                    {'error': 'Select at least one available similarity feature.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        candidate_queryset = Site.objects.filter(
                Q(is_launched=True, launch_date__isnull=False)
                | Q(cells__is_launched=True, cells__launch_date__isnull=False)
            ).exclude(pk=query_site.pk).distinct()
        all_candidate_count = candidate_queryset.count()

        # Hierarchical filtering must use reconstructed vectors, never current
        # persisted configuration before the historical vectors are built.
        if query_vector.get('event_type') == 'NEW_SITE':
            launches = candidate_queryset.filter(is_launched=True, launch_date__isnull=False)
            if launches.count() >= 3:
                candidate_queryset = launches

        candidates = list(candidate_queryset.select_related(
            'config_features', 'geometric_features', 'clutter_features',
            'spatial_features', 'anp_features', 'cluster_features', 'prelaunch_kpi', 'road_features',
        ).order_by('site_id'))
        snapshot_cache = {}
        candidate_vectors = [
            build_site_similarity_vector(
                site, as_of_date=site.launch_date or event_dates.get(site.pk) or current_as_of,
                snapshot_cache=snapshot_cache,
                allow_current_roads=True,
            )
            for site in candidates
        ]
        ranking = rank_similar_cases(
            query_vector, candidate_vectors, k=limit, selected_features=selected_features, weighting_mode=weighting_mode
        )
        candidate_by_id = {site.site_id: site for site in candidates}

        cases = []
        for item in ranking['cases']:
            vector = item['features']
            site = candidate_by_id.get(vector.get('site_id'))
            if site is None:
                continue
            cases.append({
                'site_id': site.site_id,
                'site_name': site.site_name,
                'event_date': site.launch_date or event_dates.get(site.pk),
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
                'used_features': item['used_features'],
                'feature_weights': item['feature_weights'],
                'road_context_note': vector.get('road_context_note'),
                'feature_timing_note': vector.get('feature_timing_note'),
                'population_quality': vector.get('population_quality'),
            })

        return Response({
            'query': {
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
            },
            'candidate_pool_size': len(candidates),
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
        })


class SimilarityFeatureAvailabilityView(APIView):
    """Expose query-site feature values and availability for the feature picker."""

    def get(self, request):
        site_id = request.query_params.get('site_id', '').strip()
        if not site_id:
            return Response({'error': 'site_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        query_site = Site.objects.filter(site_id=site_id).first()
        if query_site is None:
            return Response({'error': f'Site {site_id} was not found'}, status=status.HTTP_404_NOT_FOUND)

        event_dates = dict(
            Cell.objects.filter(site=query_site, is_launched=True, launch_date__isnull=False)
            .values('site_id').annotate(event_date=Min('launch_date'))
            .values_list('site_id', 'event_date')
        )
        latest_month = MAOSMonthlyKPI.objects.aggregate(month=Max('month_date'))['month']
        current_as_of = (
            month_offset(latest_month, 1)
            if latest_month else None
        )
        event_date = query_site.launch_date or event_dates.get(query_site.pk)
        vector = build_site_similarity_vector(query_site, as_of_date=event_date or current_as_of, allow_current_roads=True)
        distance = GowerDistance()
        features = [
            {
                'key': field,
                'group': distance._get_feature_group(field),
                'label': ROAD_LABELS.get(field, POPULATION_LABELS.get(field, (field.replace('_', ' '), '')))[0],
                'unit': ROAD_LABELS.get(field, POPULATION_LABELS.get(field, ('', '')))[1],
                'default_selected': field not in ROAD_FIELDS,
                'value': None if GowerDistance._is_missing(vector.get(field)) else vector.get(field),
                'available': not GowerDistance._is_missing(vector.get(field)),
            }
            for field in SIMILARITY_FIELDS
        ]
        return Response({
            'site_id': query_site.site_id,
            'site_name': query_site.site_name,
            'features': features,
            'feature_timing_note': vector.get('feature_timing_note'),
            'population_quality': vector.get('population_quality'),
        })
