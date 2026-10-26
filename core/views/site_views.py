"""
Site-related Django REST Framework views.
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Avg, Count, F, Q, Sum
from core.models import Cell, ClusterFeatures, MAOSMonthlyKPI, Site
from core.serializers import SiteSerializer, SiteGeoJSONSerializer, SiteWithFeaturesSerializer
from services.models.preprocessing.maos_aggregation import normalize_monthly_totals


class SiteViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for sites.
    
    Provides:
    - List all sites (GET /api/sites/)
    - Retrieve single site (GET /api/sites/{site_id}/)
    - Get clustered sites as GeoJSON (GET /api/sites/clusters/)
    - Get cluster statistics (GET /api/sites/cluster_stats/)
    - Get cluster KPI history and detected events (GET /api/sites/cluster_analysis/)
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

        site_ids = self.request.query_params.get('site_ids', '').strip()
        if site_ids:
            ids = [value.strip() for value in site_ids.split(',') if value.strip()]
            queryset = queryset.filter(site_id__in=ids)
        
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

    @action(detail=False, methods=['get'])
    def cluster_analysis(self, request):
        """Return cluster context, detected events, and monthly KPI aggregates."""
        raw_cluster_id = request.query_params.get('cluster_id')
        if raw_cluster_id is None:
            return Response({'error': 'cluster_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            cluster_id = int(raw_cluster_id)
        except (TypeError, ValueError):
            return Response({'error': 'cluster_id must be an integer'}, status=status.HTTP_400_BAD_REQUEST)
        if cluster_id == -1:
            return Response(
                {'error': 'Noise sites are independent and are not a single cluster'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cluster_sites = Site.objects.filter(cluster_id=cluster_id)
        site_count = cluster_sites.count()
        if not site_count:
            return Response({'error': f'Cluster {cluster_id} was not found'}, status=status.HTTP_404_NOT_FOUND)

        cluster_features = ClusterFeatures.objects.filter(site__cluster_id=cluster_id).aggregate(
            density=Avg('cluster_density_sites_per_km2'),
            traffic=Avg('cluster_avg_traffic_gb'),
            users=Avg('cluster_avg_users'),
            centroid_distance=Avg('dist_to_cluster_centroid_m'),
        )
        cells = Cell.objects.filter(site__cluster_id=cluster_id, is_launched=True).select_related('site').order_by(
            'launch_date', 'site__site_name', 'cell_name'
        )
        event_type_by_technology = {'4G': 'LTE_ADDED', '3G': '3G_ADDED', '2G': '2G_ADDED'}
        events = []
        for cell in cells:
            event_date = cell.site.launch_date if cell.site.is_launched and cell.site.launch_date else cell.launch_date
            if event_date is None:
                continue
            events.append({
                'event_date': event_date.isoformat(),
                'event_type': 'SITE_ADDED' if cell.site.is_launched else event_type_by_technology.get(cell.technology, 'CELL_ADDED'),
                'site_id': cell.site.site_id,
                'site_name': cell.site.site_name,
                'cell_id': cell.cell_id,
                'cell_name': cell.cell_name,
                'technology': cell.technology,
            })

        monthly_rows = MAOSMonthlyKPI.objects.filter(cell__site__cluster_id=cluster_id).values(
            'month_date'
        ).annotate(
            traffic_bits=Sum('thrp_bits_dl'),
            dl_bits=Sum('thrp_bits_dl', filter=Q(thrp_time_dl_ms__isnull=False, thrp_bits_dl_last_tti__isnull=False, thrp_bits_dl__gte=F('thrp_bits_dl_last_tti'))),
            dl_last_tti_bits=Sum('thrp_bits_dl_last_tti', filter=Q(thrp_time_dl_ms__isnull=False, thrp_bits_dl__gte=F('thrp_bits_dl_last_tti'))),
            dl_time_ms=Sum('thrp_time_dl_ms', filter=Q(thrp_time_dl_ms__isnull=False, thrp_bits_dl_last_tti__isnull=False, thrp_bits_dl__gte=F('thrp_bits_dl_last_tti'))),
            prb_used=Sum('prb_dl_used_avg', filter=Q(prb_dl_used_avg__isnull=False, prb_dl_available__gt=0)),
            prb_available=Sum('prb_dl_available', filter=Q(prb_dl_used_avg__isnull=False, prb_dl_available__gt=0)),
            delay_time_ms=Sum('dl_packet_delay_time_ms', filter=Q(dl_packet_delay_time_ms__isnull=False, dl_packet_delay_packets__gt=0)),
            delay_packets=Sum('dl_packet_delay_packets', filter=Q(dl_packet_delay_time_ms__isnull=False, dl_packet_delay_packets__gt=0)),
            unavailable_s=Sum('cell_unavail_duration_s', filter=Q(cell_unavail_duration_s__isnull=False, observation_duration_s__gt=0)),
            observation_s=Sum('observation_duration_s', filter=Q(cell_unavail_duration_s__isnull=False, observation_duration_s__gt=0)),
            cqi_weighted_total=Sum('cqi_weighted_sum', filter=Q(cqi_weighted_sum__isnull=False, cqi_sample_count__gt=0)),
            cqi_sample_count=Sum('cqi_sample_count', filter=Q(cqi_weighted_sum__isnull=False, cqi_sample_count__gt=0)),
            active_users=Sum('active_users_avg'),
            traffic_users=Sum('traffic_user_avg'),
            reporting_cells=Count('cell_id', distinct=True),
            reporting_sites=Count('cell__site_id', distinct=True),
        ).order_by('month_date')
        monthly_kpis = []
        for row in monthly_rows:
            metrics = normalize_monthly_totals(row)
            monthly_kpis.append({
                'month': row['month_date'].isoformat(),
                'downlink_traffic_gb': metrics['thrp_dl_gb'],
                'active_users_sum': metrics['active_users_avg'],
                'traffic_users_sum': metrics['traffic_user_avg'],
                'downlink_prb_avg_pct': metrics['prb_util_dl_pct'],
                'cqi_avg': metrics['cqi_avg'],
                'dl_throughput_kbps': metrics['dl_throughput_kbps'],
                'dl_packet_delay_ms': metrics['dl_packet_delay_ms'],
                'cell_availability_pct': metrics['cell_availability_pct'],
                'reporting_cells': row['reporting_cells'],
                'reporting_sites': row['reporting_sites'],
            })
        event_counts = {}
        for event in events:
            event_counts[event['event_type']] = event_counts.get(event['event_type'], 0) + 1

        return Response({
            'cluster_id': cluster_id,
            'context': {
                'site_count': site_count,
                'edge_sites': cluster_sites.filter(is_cluster_edge=True).count(),
                'interior_sites': cluster_sites.filter(is_cluster_edge=False).count(),
                'sites_with_maos': MAOSMonthlyKPI.objects.filter(
                    cell__site__cluster_id=cluster_id
                ).values('cell__site_id').distinct().count(),
                'cluster_density_sites_per_km2': cluster_features['density'] or 0,
                'cluster_avg_traffic_gb': cluster_features['traffic'] or 0,
                'cluster_avg_users': cluster_features['users'] or 0,
                'avg_dist_to_centroid_m': cluster_features['centroid_distance'] or 0,
                'event_count': len(events),
                'event_counts': event_counts,
            },
            'monthly_kpis': monthly_kpis,
            'events': events,
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
