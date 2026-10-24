"""
URL configuration for Smart CAPEX core API endpoints.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from core.views import SiteViewSet, CellViewSet
from core.views import dem_views

# Create router for REST API
router = DefaultRouter()
router.register(r'sites', SiteViewSet, basename='site')
router.register(r'cells', CellViewSet, basename='cell')

urlpatterns = [
    path('api/', include(router.urls)),
    
    # DEM endpoints
    path('api/dem/elevation/', dem_views.get_elevation, name='dem-elevation'),
    path('api/dem/elevation_stats/', dem_views.get_elevation_stats, name='dem-elevation-stats'),
    path('api/dem/terrain_features/', dem_views.get_terrain_features, name='dem-terrain-features'),
    path('api/dem/hillshade/<int:z>/<int:x>/<int:y>.png', dem_views.serve_hillshade_tile, name='dem-hillshade-tile'),
    path('api/dem/elevation_tile/<int:z>/<int:x>/<int:y>.png', dem_views.serve_elevation_tile, name='dem-elevation-tile'),
]
