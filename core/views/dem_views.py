"""
DEM Visualization API Views

Django REST endpoints for DEM data visualization and querying.

Endpoints:
- GET /api/dem/elevation/ - Query elevation at specific coordinates
- GET /api/dem/hillshade/{z}/{x}/{y}.png - Serve hillshade tiles
- GET /api/dem/elevation_tile/{z}/{x}/{y}.png - Serve elevation-colored tiles

MVC: View layer (API endpoints only)
"""

from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.http import HttpResponse
import logging
import math

from services.visualization.dem_processor import get_dem_processor

logger = logging.getLogger(__name__)


def tile_to_bbox(z: int, x: int, y: int) -> tuple:
    """
    Convert tile coordinates (z/x/y) to bounding box (Web Mercator to WGS84).
    
    Args:
        z: Zoom level
        x: Tile X coordinate
        y: Tile Y coordinate
        
    Returns:
        Tuple (minx, miny, maxx, maxy) in WGS84 degrees
    """
    n = 2.0 ** z
    lon_min = x / n * 360.0 - 180.0
    lat_min_rad = math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n)))
    lat_min = math.degrees(lat_min_rad)
    
    lon_max = (x + 1) / n * 360.0 - 180.0
    lat_max_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
    lat_max = math.degrees(lat_max_rad)
    
    return (lon_min, lat_min, lon_max, lat_max)


@api_view(['GET'])
def get_elevation(request):
    """
    Get elevation at specific coordinates.
    
    Query Parameters:
        lat: Latitude (WGS84)
        lon: Longitude (WGS84)
        
    Returns:
        JSON: {
            "latitude": float,
            "longitude": float,
            "elevation_m": float or null,
            "success": bool
        }
    """
    try:
        lat = float(request.GET.get('lat'))
        lon = float(request.GET.get('lon'))
    except (TypeError, ValueError):
        return Response(
            {"error": "Invalid lat/lon parameters. Both must be numeric."},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Validate coordinates
    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        return Response(
            {"error": "Coordinates out of valid range"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Get DEM processor
    dem_proc = get_dem_processor()
    
    # Query elevation
    elevation = dem_proc.get_elevation(lat, lon)
    
    return Response({
        "latitude": lat,
        "longitude": lon,
        "elevation_m": elevation,
        "success": elevation is not None
    })


@api_view(['GET'])
def get_elevation_stats(request):
    """
    Get elevation statistics within buffer around point.
    
    Query Parameters:
        lat: Latitude (WGS84)
        lon: Longitude (WGS84)
        buffer_m: Buffer radius in meters (default: 1000)
        
    Returns:
        JSON: {
            "latitude": float,
            "longitude": float,
            "buffer_m": float,
            "elevation_stats": {
                "mean": float,
                "min": float,
                "max": float,
                "std": float
            },
            "success": bool
        }
    """
    try:
        lat = float(request.GET.get('lat'))
        lon = float(request.GET.get('lon'))
        buffer_m = float(request.GET.get('buffer_m', 1000))
    except (TypeError, ValueError):
        return Response(
            {"error": "Invalid parameters"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Get DEM processor
    dem_proc = get_dem_processor()
    
    # Query elevation stats
    stats = dem_proc.get_elevation_stats(lat, lon, buffer_m)
    
    return Response({
        "latitude": lat,
        "longitude": lon,
        "buffer_m": buffer_m,
        "elevation_stats": stats,
        "success": stats.get('mean') is not None
    })


@api_view(['GET'])
def get_terrain_features(request):
    """
    Get terrain features (slope, aspect, roughness) for a point.
    
    Query Parameters:
        lat: Latitude (WGS84)
        lon: Longitude (WGS84)
        
    Returns:
        JSON: {
            "latitude": float,
            "longitude": float,
            "elevation_m": float,
            "slope_deg": float,
            "aspect_deg": float,
            "roughness_m": float,
            "success": bool
        }
    """
    try:
        lat = float(request.GET.get('lat'))
        lon = float(request.GET.get('lon'))
    except (TypeError, ValueError):
        return Response(
            {"error": "Invalid lat/lon parameters"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Get DEM processor
    dem_proc = get_dem_processor()
    
    # Query terrain features
    elevation = dem_proc.get_elevation(lat, lon)
    slope = dem_proc.compute_slope(lat, lon, buffer_m=200)
    aspect = dem_proc.compute_aspect(lat, lon, buffer_m=200)
    roughness = dem_proc.compute_roughness(lat, lon, buffer_m=1000)
    
    return Response({
        "latitude": lat,
        "longitude": lon,
        "elevation_m": elevation,
        "slope_deg": slope,
        "aspect_deg": aspect,
        "roughness_m": roughness,
        "success": all(v is not None for v in [elevation, slope, aspect, roughness])
    })


def serve_hillshade_tile(request, z: int, x: int, y: int):
    """
    Serve hillshade tile as PNG image.
    
    URL Pattern: /api/dem/hillshade/{z}/{x}/{y}.png
    
    Args:
        z: Zoom level (0-18)
        x: Tile X coordinate
        y: Tile Y coordinate
        
    Returns:
        PNG image (HttpResponse)
    """
    try:
        # Convert tile coords to bbox
        bbox = tile_to_bbox(z, x, y)
        
        # Get DEM processor
        dem_proc = get_dem_processor()
        
        # Generate hillshade tile
        tile_bytes = dem_proc.generate_hillshade(bbox, width=256, height=256)
        
        if tile_bytes is None:
            return HttpResponse(status=404)
        
        # Return as PNG image
        response = HttpResponse(tile_bytes, content_type='image/png')
        response['Cache-Control'] = 'public, max-age=86400'  # Cache for 24 hours
        return response
        
    except Exception as e:
        logger.error(f"Error serving hillshade tile {z}/{x}/{y}: {e}")
        return HttpResponse(status=500)


def serve_elevation_tile(request, z: int, x: int, y: int):
    """
    Serve elevation-colored tile as PNG image.
    
    URL Pattern: /api/dem/elevation_tile/{z}/{x}/{y}.png
    
    Args:
        z: Zoom level (0-18)
        x: Tile X coordinate
        y: Tile Y coordinate
        
    Returns:
        PNG image (HttpResponse)
    """
    try:
        # Convert tile coords to bbox
        bbox = tile_to_bbox(z, x, y)
        
        # Get colormap from query params (default: terrain)
        colormap = request.GET.get('colormap', 'terrain')
        
        # Get DEM processor
        dem_proc = get_dem_processor()
        
        # Generate elevation tile
        tile_bytes = dem_proc.generate_elevation_tile(
            bbox,
            width=256,
            height=256,
            colormap=colormap
        )
        
        if tile_bytes is None:
            return HttpResponse(status=404)
        
        # Return as PNG image
        response = HttpResponse(tile_bytes, content_type='image/png')
        response['Cache-Control'] = 'public, max-age=86400'  # Cache for 24 hours
        return response
        
    except Exception as e:
        logger.error(f"Error serving elevation tile {z}/{x}/{y}: {e}")
        return HttpResponse(status=500)