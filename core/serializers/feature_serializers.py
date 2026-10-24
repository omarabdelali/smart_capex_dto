"""
Feature-related Django REST Framework serializers.
"""

from rest_framework import serializers
from core.models import (
    GeometricFeatures,
    ClutterFeatures,
    SpatialFeatures,
    ANPFeatures,
    Site
)


class GeometricFeaturesSerializer(serializers.ModelSerializer):
    """Serializer for geometric (DEM-based) features."""
    
    class Meta:
        model = GeometricFeatures
        fields = [
            'z_antenna_m',
            'terrain_slope_deg',
            'terrain_aspect_deg',
            'terrain_roughness_m'
        ]


class ClutterFeaturesSerializer(serializers.ModelSerializer):
    """Serializer for clutter (land cover) features."""
    
    class Meta:
        model = ClutterFeatures
        fields = [
            'dominant_clutter',
            'clutter_entropy_2km',
            'pct_building_area_1km',
            'avg_building_height_m'
        ]


class SpatialFeaturesSerializer(serializers.ModelSerializer):
    """Serializer for spatial (neighbor-based) features."""
    
    class Meta:
        model = SpatialFeatures
        fields = [
            'dist_nearest_site_m',
            'n_sites_1km',
            'n_sites_2km',
            'n_sites_3km',
            'n_2g_sites_2km',
            'n_3g_sites_2km',
            'n_4g_sites_2km',
            'neighbor_avg_antenna_height_m'
        ]


class ANPFeaturesSerializer(serializers.ModelSerializer):
    """Serializer for Angular Neighborhood Profile features."""
    
    # Angular bins for polar chart visualization
    angular_bins = serializers.SerializerMethodField()
    
    class Meta:
        model = ANPFeatures
        fields = [
            'n_neighbors_0_30',
            'n_neighbors_30_60',
            'n_neighbors_60_90',
            'n_neighbors_90_120',
            'n_neighbors_120_150',
            'n_neighbors_150_180',
            'n_neighbors_180_210',
            'n_neighbors_210_240',
            'n_neighbors_240_270',
            'n_neighbors_270_300',
            'n_neighbors_300_330',
            'n_neighbors_330_360',
            'max_empty_arc_deg',
            'angular_imbalance',
            'edge_score',
            'angular_bins'  # Formatted for Chart.js
        ]
    
    def get_angular_bins(self, obj):
        """
        Format angular distribution for Chart.js polar chart.
        
        Returns:
            List of 12 values (neighbor counts per 30° bin)
        """
        return [
            obj.n_neighbors_0_30,
            obj.n_neighbors_30_60,
            obj.n_neighbors_60_90,
            obj.n_neighbors_90_120,
            obj.n_neighbors_120_150,
            obj.n_neighbors_150_180,
            obj.n_neighbors_180_210,
            obj.n_neighbors_210_240,
            obj.n_neighbors_240_270,
            obj.n_neighbors_270_300,
            obj.n_neighbors_300_330,
            obj.n_neighbors_330_360
        ]


class SiteWithFeaturesSerializer(serializers.ModelSerializer):
    """
    Comprehensive serializer for Site with all extracted features.
    
    Used for detailed site feature display in frontend popups.
    """
    
    # Nested feature serializers
    geometric = GeometricFeaturesSerializer(source='geometric_features', read_only=True)
    clutter = ClutterFeaturesSerializer(source='clutter_features', read_only=True)
    spatial = SpatialFeaturesSerializer(source='spatial_features', read_only=True)
    anp = ANPFeaturesSerializer(source='anp_features', read_only=True)
    
    # Cell info
    cell_count = serializers.SerializerMethodField()
    technologies = serializers.SerializerMethodField()
    
    # Neighbor coordinates for link visualization
    neighbor_coords = serializers.SerializerMethodField()
    
    class Meta:
        model = Site
        fields = [
            'site_id',
            'site_name',
            'latitude',
            'longitude',
            'cluster_id',
            'is_cluster_edge',
            'out_of_bounds',
            'cell_count',
            'technologies',
            'geometric',
            'clutter',
            'spatial',
            'anp',
            'neighbor_coords'
        ]
    
    def get_cell_count(self, obj):
        """Get number of cells at this site."""
        return obj.cells.count()
    
    def get_technologies(self, obj):
        """Get list of technologies at this site."""
        return list(obj.cells.values_list('technology', flat=True).distinct())
    
    def get_neighbor_coords(self, obj):
        """
        Get coordinates of neighboring sites for link visualization.
        
        Returns list of neighbor sites within the clustering radius (typically 2-3km).
        Each neighbor: {site_id, site_name, latitude, longitude, distance_m}
        """
        from django.contrib.gis.geos import Point
        from django.contrib.gis.measure import D
        from django.contrib.gis.db.models.functions import Distance
        
        # Get site location as Point
        site_point = Point(obj.longitude, obj.latitude, srid=4326)
        
        # Find neighbors within 3km radius (typical for ANP computation)
        neighbors = Site.objects.filter(
            cluster_id=obj.cluster_id  # Same cluster
        ).exclude(
            site_id=obj.site_id  # Exclude self
        ).annotate(
            distance=Distance('location', site_point)
        ).filter(
            distance__lte=D(km=3)
        ).order_by('distance')[:30]  # Limit to 30 nearest to avoid clutter
        
        # Format neighbor data
        neighbor_data = []
        for neighbor in neighbors:
            neighbor_data.append({
                'site_id': neighbor.site_id,
                'site_name': neighbor.site_name,
                'latitude': neighbor.latitude,
                'longitude': neighbor.longitude,
                'distance_m': round(neighbor.distance.m, 1) if hasattr(neighbor, 'distance') else None
            })
        
        return neighbor_data