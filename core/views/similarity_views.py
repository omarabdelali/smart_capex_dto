"""Transport adapters; similarity preparation and calculations live in services."""
from rest_framework.response import Response
from rest_framework.views import APIView
from services.analysis_profiles import browser_actor
from services.models.similarity.api import search_similarity, feature_availability


class SimilaritySearchView(APIView):
    def get(self, request):
        payload, status = search_similarity(request.query_params,browser_actor(request))
        return Response(payload, status=status)


class SimilarityFeatureAvailabilityView(APIView):
    def get(self, request):
        payload, status = feature_availability(request.query_params,browser_actor(request))
        return Response(payload, status=status)
