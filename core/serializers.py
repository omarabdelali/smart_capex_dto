"""
Django REST Framework serializers for Smart CAPEX core models.
"""

from rest_framework import serializers
from core.models import Site, Cell


class CellSerializer(serializers.ModelSerializer):
    """Serializer for Cell model."""
    
    class Meta:
        model = Cell
        fields = [
            'cell_id', 'cell_name', 'cgi', 'technology', 
            'frequency', 'band', 'bandwidth_mhz', 'azimuth', 
            'antenna_height_m'
        ]


class SiteSerializer(serializers.ModelSerializer):
    """Serializer for Site model with cells."""
    
    cells = CellSerializer(many=True, read_only=True)
    
    class Meta:
        model = Site
        fields = [
            'site_id', 'site_name', 'latitude', 'longitude',
            'cluster_id', 'is_cluster_edge', 'out_of_bounds',
            'cells'
        ]


class SiteGeoJSONSerializer(serializers.ModelSerializer):
    """
    Custom GeoJSON serializer for Site model (without GDAL dependency).
    
    Outputs sites as GeoJSON FeatureCollection for Leaflet map rendering.
    Includes cluster metadata in feature properties.
    """
    
    cell_count = serializers.SerializerMethodField()
    technologies = serializers.SerializerMethodField()
    
    class Meta:
        model = Site
        fields = [
            'site_id', 'site_name', 'latitude', 'longitude',
            'cluster_id', 'is_cluster_edge', 'out_of_bounds',
            'cell_count', 'technologies'
        ]
    
    def get_cell_count(self, obj):
        """Get number of cells at this site."""
        return obj.cells.count()
    
    def get_technologies(self, obj):
        """Get list of technologies at this site."""
        return list(obj.cells.values_list('technology', flat=True).distinct())
    
    def to_representation(self, instance):
        """Convert to GeoJSON Feature format."""
        properties = super().to_representation(instance)
        
        # Extract coordinates from properties
        latitude = properties.pop('latitude')
        longitude = properties.pop('longitude')
        
        # Return GeoJSON Feature structure
        return {
            'type': 'Feature',
            'geometry': {
                'type': 'Point',
                'coordinates': [longitude, latitude]  # GeoJSON uses [lon, lat]
            },
            'properties': properties
        }
