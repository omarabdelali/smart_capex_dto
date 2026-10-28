"""
URL configuration for Smart CAPEX core API endpoints.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from core.views import SiteViewSet, CellViewSet
from core.views import dem_views
from core.views import population_views
from core.views.feature_sync_views import FeatureSyncView
from core.views.similarity_views import SimilarityFeatureAvailabilityView, SimilaritySearchView
from core.views.cbr_views import CBRImpactPredictionView,RecipientCBRView,CounterfactualGainView
from core.views.data_explorer_views import DataExplorerView, DataExplorerMetadataView
from core.views.analysis_profile_views import AnalysisProfilesView,AnalysisProfileView,AnalysisProfileDefaultsView
from core.views.candidate_scenarios import CandidateScenariosView,CandidateScenarioView

# Create router for REST API
router = DefaultRouter()
router.register(r'sites', SiteViewSet, basename='site')
router.register(r'cells', CellViewSet, basename='cell')

urlpatterns = [
    path('api/candidates/',CandidateScenariosView.as_view()),
    path('api/candidates/<uuid:scenario_id>/',CandidateScenarioView.as_view()),
    path('api/analysis/profiles/',AnalysisProfilesView.as_view()),
    path('api/analysis/profiles/<uuid:profile_id>/',AnalysisProfileView.as_view()),
    path('api/analysis/defaults/',AnalysisProfileDefaultsView.as_view()),
    path('api/analysis/defaults/<int:default_id>/',AnalysisProfileDefaultsView.as_view()),
    path('api/explore/', DataExplorerView.as_view(), name='data-explorer'),
    path('api/explore/metadata/', DataExplorerMetadataView.as_view(), name='data-explorer-metadata'),
    path('api/population/tiles/<int:z>/<int:x>/<int:y>.png', population_views.tile, name='population-tile'),
    path('api/', include(router.urls)),
    path('api/features/sync/', FeatureSyncView.as_view(), name='feature-sync'),
    path('api/similarity/search/', SimilaritySearchView.as_view(), name='similarity-search'),
    path('api/similarity/features/', SimilarityFeatureAvailabilityView.as_view(), name='similarity-feature-availability'),
    path('api/cbr/impact/', CBRImpactPredictionView.as_view(), name='cbr-impact-prediction'),
    path('api/cbr/recipients/', RecipientCBRView.as_view(), name='recipient-cbr'),
    path('api/cbr/gains/',CounterfactualGainView.as_view(),name='counterfactual-gains'),
    
    # DEM endpoints
    path('api/dem/elevation/', dem_views.get_elevation, name='dem-elevation'),
    path('api/dem/elevation_stats/', dem_views.get_elevation_stats, name='dem-elevation-stats'),
    path('api/dem/terrain_features/', dem_views.get_terrain_features, name='dem-terrain-features'),
    path('api/dem/hillshade/<int:z>/<int:x>/<int:y>.png', dem_views.serve_hillshade_tile, name='dem-hillshade-tile'),
    path('api/dem/elevation_tile/<int:z>/<int:x>/<int:y>.png', dem_views.serve_elevation_tile, name='dem-elevation-tile'),
]
