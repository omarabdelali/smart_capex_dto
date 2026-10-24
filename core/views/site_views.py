"""
Site-related Django REST Framework views.
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Count, Q
from core.models import Site
from core.serializers import SiteSerializer, SiteGeoJSONSerializer, SiteWithFeaturesSerializer


class SiteViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for sites.
    
    Provides:
    - List all sites (GET /api/sites/)
    - Retrieve single site (GET /api/sites/{site_id}/)
    - Get clustered sites as GeoJSON (GET /api/sites/clusters/)
    - Get cluster statistics (GET /api/sites/cluster_stats/)
    """
    
    queryset = Site.objects.all()
    serializer_class = SiteSerializer
    lookup_field = 'site_id'
    
    def get_queryset(self):
        """
        Filter queryset based on query parameters.
        
        Supported filters:
        - cluster_id: Filter by cluster ID
        - is_edge: Filter edge sites (true/false)
        - out_of_bounds: Filter out-of-bounds sites (true/false)
        - technology: Filter by cell technology (2G, 3G, 4G)
        """
        queryset = Site.objects.all().prefetch_related('cells')
        
        # Filter by cluster_id
        cluster_id = self.request.query_params.get('cluster_id')
        if cluster_id is not None:
            queryset = queryset.filter(cluster_id=int(cluster_id))
        
        # Filter by edge status
        is_edge = self.request.query_params.get('is_edge')
        if is_edge is not None:
            queryset = queryset.filter(is_cluster_edge=(is_edge.lower() == 'true'))
        
        # Filter by out-of-bounds status
        out_of_bounds = self.request.query_params.get('out_of_bounds')
        if out_of_bounds is not None:
            queryset = queryset.filter(out_of_bounds=(out_of_bounds.lower() == 'true'))
        
        # Filter by technology
        technology = self.request.query_params.get('technology')
        if technology:
            queryset = queryset.filter(cells__technology=technology.upper()).distinct()

        search_term = self.request.query_params.get('search', '').strip()
        if search_term:
            queryset = queryset.filter(
                Q(site_id__icontains=search_term)
                | Q(site_name__icontains=search_term)
                | Q(cells__cell_name__icontains=search_term)
            ).distinct()
        
        return queryset
    
    @action(detail=False, methods=['get'])
    def clusters(self, request):
        """
        Return all sites as GeoJSON FeatureCollection with cluster metadata.
        
        GET /api/sites/clusters/
        
        Query parameters:
        - cluster_id: Filter by specific cluster
        - format: 'geojson' (default) or 'json'
        
        Returns:
            GeoJSON FeatureCollection with site features
        """
        queryset = self.get_queryset()
        search_term = request.query_params.get('search', '').strip()
        if search_term:
            queryset = queryset.order_by('site_name')[:100]
        
        # Use GeoJSON serializer
        serializer = SiteGeoJSONSerializer(queryset, many=True, context={'search_term': search_term})
        
        # Wrap in FeatureCollection for proper GeoJSON format
        geojson = {
            'type': 'FeatureCollection',
            'features': serializer.data
        }
        
        return Response(geojson)
    
    @action(detail=False, methods=['get'])
    def cluster_stats(self, request):
        """
        Return cluster statistics.
        
        GET /api/sites/cluster_stats/
        
        Returns:
            {
                "total_sites": N,
                "total_clusters": M,
                "noise_sites": K,
                "out_of_bounds_sites": L,
                "edge_sites": P,
                "interior_sites": Q,
                "clusters": [
                    {
                        "cluster_id": 0,
                        "site_count": 15,
                        "edge_count": 5,
                        "interior_count": 10
                    },
                    ...
                ]
            }
        """
        total_sites = Site.objects.count()
        
        # Count unique clusters (excluding noise points -1)
        cluster_ids = Site.objects.exclude(cluster_id=-1).values_list('cluster_id', flat=True).distinct()
        total_clusters = len(cluster_ids)
        
        # Count noise sites (cluster_id = -1)
        noise_sites = Site.objects.filter(cluster_id=-1).count()
        
        # Count out-of-bounds sites
        out_of_bounds_sites = Site.objects.filter(out_of_bounds=True).count()
        
        # Count edge vs interior sites
        edge_sites = Site.objects.filter(is_cluster_edge=True).count()
        interior_sites = Site.objects.filter(is_cluster_edge=False).count()
        
        # Get per-cluster statistics
        clusters = []
        for cluster_id in sorted(cluster_ids):
            cluster_sites = Site.objects.filter(cluster_id=cluster_id)
            site_count = cluster_sites.count()
            edge_count = cluster_sites.filter(is_cluster_edge=True).count()
            interior_count = cluster_sites.filter(is_cluster_edge=False).count()
            
            clusters.append({
                'cluster_id': cluster_id,
                'site_count': site_count,
                'edge_count': edge_count,
                'interior_count': interior_count,
            })
        
        return Response({
            'total_sites': total_sites,
            'total_clusters': total_clusters,
            'noise_sites': noise_sites,
            'out_of_bounds_sites': out_of_bounds_sites,
            'edge_sites': edge_sites,
            'interior_sites': interior_sites,
            'clusters': clusters,
        })
    
    @action(detail=True, methods=['get'])
    def features(self, request, site_id=None):
        """
        Return detailed features for a specific site.
        
        GET /api/sites/{site_id}/features/
        
        Returns:
            {
                "site_id": ...,
                "site_name": ...,
                "latitude": ...,
                "longitude": ...,
                "cluster_id": ...,
                "is_cluster_edge": ...,
                "geometric": {
                    "z_antenna_m": ...,
                    "terrain_slope_deg": ...,
                    ...
                },
                "clutter": {
                    "dominant_clutter": ...,
                    "clutter_entropy_2km": ...,
                    ...
                },
                "spatial": {
                    "dist_nearest_site_m": ...,
                    "n_sites_1km": ...,
                    ...
                },
                "anp": {
                    "n_neighbors_0_30": ...,
                    "edge_score": ...,
                    "angular_bins": [0, 2, 3, ...],
                    ...
                },
                "neighbor_coords": [
                    {"site_id": ..., "latitude": ..., "longitude": ..., "distance_m": ...},
                    ...
                ]
            }
        """
        try:
            site = Site.objects.select_related(
                'geometric_features',
                'clutter_features',
                'spatial_features',
                'anp_features',
                'kpi_features',
                'config_features',
                'cluster_features'
            ).prefetch_related('cells').get(site_id=site_id)
        except Site.DoesNotExist:
            return Response(
                {'error': f'Site {site_id} not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = SiteWithFeaturesSerializer(
            site, context={'search_term': request.query_params.get('search', '').strip()}
        )
        return Response(serializer.data)
