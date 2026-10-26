"""
Site-related Django REST Framework serializers.
"""

from rest_framework import serializers
from core.models import Site
from .cell_serializers import CellSerializer


# Kept as an import alias for existing callers; all event logic is in services.
from services.models.preprocessing.network_events import site_event_data as get_site_addition_data


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
    added_cell_count = serializers.SerializerMethodField()
    addition_events = serializers.SerializerMethodField()
    network_events = serializers.SerializerMethodField()
    matched_cells = serializers.SerializerMethodField()
    is_launched = serializers.SerializerMethodField()
    launch_date = serializers.SerializerMethodField()
    
    class Meta:
        model = Site
        fields = [
            'site_id', 'site_name', 'latitude', 'longitude',
            'cluster_id', 'is_cluster_edge', 'out_of_bounds',
            'cell_count', 'technologies', 'is_launched', 'launch_date',
            'added_cell_count', 'addition_events', 'network_events', 'matched_cells'
        ]
    
    def get_cell_count(self, obj):
        """Get number of cells at this site."""
        return sum(1 for _ in obj.cells.all())
    
    def get_technologies(self, obj):
        """Get list of technologies at this site."""
        return sorted({cell.technology for cell in obj.cells.all()})

    def get_added_cell_count(self, obj):
        return len(get_site_addition_data(obj)['added_cells'])

    def get_addition_events(self, obj):
        return get_site_addition_data(obj)['events']

    def get_network_events(self, obj):
        return get_site_addition_data(obj)['network_events']

    def get_is_launched(self, obj):
        return bool(get_site_addition_data(obj)['events'])

    def get_launch_date(self, obj):
        events = get_site_addition_data(obj)['events']
        return min((event['launch_date'] for event in events), default=None)

    def get_matched_cells(self, obj):
        term = (self.context.get('search_term') or '').casefold()
        if not term:
            return []
        return [
            {'cell_name': cell.cell_name, 'technology': cell.technology}
            for cell in obj.cells.all()
            if term in cell.cell_name.casefold()
        ]
    
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
