"""
Site-related Django REST Framework serializers.
"""

from rest_framework import serializers
from core.models import MAOSMonthlyKPI, Site
from .cell_serializers import CellSerializer


TECH_EVENT_TYPES = {'2G': '2G_ADDED', '3G': '3G_ADDED', '4G': 'LTE_ADDED'}
_MAOS_START_DATE = None


def get_site_addition_data(site):
    """Format persisted cell activations as technology/site addition events."""
    cached = getattr(site, '_site_addition_display_data', None)
    if cached is not None:
        return cached

    cells = list(site.cells.all())
    detected_cells = [cell for cell in cells if cell.is_launched and cell.launch_date]
    launch_by_technology = {}
    for cell in detected_cells:
        launch_by_technology[cell.technology] = min(
            launch_by_technology.get(cell.technology, cell.launch_date), cell.launch_date
        )

    global _MAOS_START_DATE
    if _MAOS_START_DATE is None:
        _MAOS_START_DATE = MAOSMonthlyKPI.objects.order_by('month_date').values_list('month_date', flat=True).first()
    valid_launches = {}
    for technology, launch_date in launch_by_technology.items():
        if _MAOS_START_DATE and launch_date > _MAOS_START_DATE:
            valid_launches[technology] = launch_date
    launch_by_technology = valid_launches
    detected_cells = [cell for cell in detected_cells if cell.technology in launch_by_technology]

    current_technologies = {cell.technology for cell in cells}
    site_added = bool(
        site.is_launched
        and site.launch_date
        and _MAOS_START_DATE
        and site.launch_date > _MAOS_START_DATE
        and set(launch_by_technology) == current_technologies
        and len(set(launch_by_technology.values())) == 1
        and next(iter(launch_by_technology.values()), None) == site.launch_date
    )
    if site_added:
        event_date = site.launch_date
        events = [{'event_type': 'SITE_ADDED', 'launch_date': event_date.isoformat()}]
    else:
        events = [
            {'event_type': TECH_EVENT_TYPES[technology], 'launch_date': event_date.isoformat()}
            for technology, event_date in launch_by_technology.items()
            if technology in TECH_EVENT_TYPES
        ]

    added_cells = []
    for cell in detected_cells:
        event_type = 'SITE_ADDED' if site_added else TECH_EVENT_TYPES.get(cell.technology)
        if event_type:
            added_cells.append({
                'cell_id': cell.cell_id,
                'cell_name': cell.cell_name,
                'technology': cell.technology,
                'event_type': event_type,
                'launch_date': cell.launch_date.isoformat(),
            })

    result = {
        'events': sorted(events, key=lambda event: (event['launch_date'], event['event_type'])),
        'added_cells': sorted(added_cells, key=lambda item: (item['launch_date'], item['cell_name'])),
    }
    site._site_addition_display_data = result
    return result


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
    matched_cells = serializers.SerializerMethodField()
    is_launched = serializers.SerializerMethodField()
    launch_date = serializers.SerializerMethodField()
    
    class Meta:
        model = Site
        fields = [
            'site_id', 'site_name', 'latitude', 'longitude',
            'cluster_id', 'is_cluster_edge', 'out_of_bounds',
            'cell_count', 'technologies', 'is_launched', 'launch_date',
            'added_cell_count', 'addition_events', 'matched_cells'
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
