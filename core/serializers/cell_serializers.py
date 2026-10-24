"""
Cell-related Django REST Framework serializers.
"""

from rest_framework import serializers
from core.models import Cell


class CellSerializer(serializers.ModelSerializer):
    """Serializer for Cell model."""
    
    class Meta:
        model = Cell
        fields = [
            'cell_id', 'cell_name', 'cgi', 'technology', 
            'frequency', 'band', 'bandwidth_mhz', 'azimuth', 
            'antenna_height_m'
        ]