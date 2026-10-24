"""
URL configuration for Smart CAPEX core API endpoints.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from core.views import SiteViewSet, CellViewSet

# Create router for REST API
router = DefaultRouter()
router.register(r'sites', SiteViewSet, basename='site')
router.register(r'cells', CellViewSet, basename='cell')

urlpatterns = [
    path('api/', include(router.urls)),
]