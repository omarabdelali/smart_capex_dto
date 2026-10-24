"""
Visualization services for Smart CAPEX.

This module provides services for generating map visualizations and processing
geographic data for display.

Services:
- DEMProcessor: Digital Elevation Model processing for terrain visualization
"""

from services.visualization.dem_processor import DEMProcessor, get_dem_processor

__all__ = ['DEMProcessor', 'get_dem_processor']