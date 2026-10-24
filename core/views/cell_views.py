"""
Cell-related Django REST Framework views.
"""

from rest_framework import viewsets
from core.models import Cell
from core.serializers import CellSerializer


class CellViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for cells.
    
    Provides:
    - List all cells (GET /api/cells/)
    - Retrieve single cell (GET /api/cells/{cell_id}/)
    - Filter by technology, site, etc.
    """
    
    queryset = Cell.objects.all()
    serializer_class = CellSerializer
    lookup_field = 'cell_id'
    
    def get_queryset(self):
        """
        Filter queryset based on query parameters.
        
        Supported filters:
        - site_id: Filter by site
        - technology: Filter by technology (2G, 3G, 4G)
        - frequency: Filter by frequency
        """
        queryset = Cell.objects.all().select_related('site')
        
        # Filter by site_id
        site_id = self.request.query_params.get('site_id')
        if site_id:
            queryset = queryset.filter(site__site_id=site_id)
        
        # Filter by technology
        technology = self.request.query_params.get('technology')
        if technology:
            queryset = queryset.filter(technology=technology.upper())
        
        # Filter by frequency range
        min_freq = self.request.query_params.get('min_frequency')
        max_freq = self.request.query_params.get('max_frequency')
        if min_freq:
            queryset = queryset.filter(frequency__gte=float(min_freq))
        if max_freq:
            queryset = queryset.filter(frequency__lte=float(max_freq))
        
        return queryset