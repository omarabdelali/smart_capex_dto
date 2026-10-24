"""
Geographic utility functions for Smart CAPEX.
Haversine distance, bearing calculations, DEM sampling, etc.
"""

import math
import numpy as np
from typing import Tuple, Optional


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great circle distance between two points on Earth.
    
    Args:
        lat1, lon1: First point coordinates (decimal degrees)
        lat2, lon2: Second point coordinates (decimal degrees)
    
    Returns:
        Distance in meters
    """
    # Convert to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    
    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    
    # Earth radius in meters
    r = 6371000
    
    return r * c


def compute_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the bearing from point 1 to point 2.
    
    Args:
        lat1, lon1: Starting point coordinates (decimal degrees)
        lat2, lon2: Ending point coordinates (decimal degrees)
    
    Returns:
        Bearing in degrees (0-360), where 0 is North, 90 is East
    """
    # Convert to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    
    dlon = lon2 - lon1
    
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    
    initial_bearing = math.atan2(x, y)
    
    # Convert to degrees and normalize to 0-360
    bearing = (math.degrees(initial_bearing) + 360) % 360
    
    return bearing


def sample_dem(lon: float, lat: float, dem_path: str) -> Optional[float]:
    """
    Sample DEM elevation at a given point.
    
    Args:
        lon, lat: Point coordinates (decimal degrees, WGS84)
        dem_path: Path to DEM raster (VRT or GeoTIFF)
    
    Returns:
        Elevation in meters, or None if no data
    """
    try:
        import rasterio
        from rasterio.transform import rowcol
        
        with rasterio.open(dem_path) as src:
            # Get row, col from lon, lat
            row, col = rowcol(src.transform, lon, lat)
            
            # Check if within bounds
            if 0 <= row < src.height and 0 <= col < src.width:
                # Read single pixel
                window = ((row, row + 1), (col, col + 1))
                data = src.read(1, window=window)
                elevation = float(data[0, 0])
                
                # Check for nodata
                if src.nodata is not None and elevation == src.nodata:
                    return None
                
                return elevation
            else:
                return None
                
    except Exception as e:
        print(f"Error sampling DEM at ({lon}, {lat}): {e}")
        return None


def sample_dem_buffer(lon: float, lat: float, dem_path: str, radius_m: float = 1000) -> Optional[np.ndarray]:
    """
    Sample DEM values in a circular buffer around a point.
    
    Args:
        lon, lat: Center point coordinates (decimal degrees, WGS84)
        dem_path: Path to DEM raster
        radius_m: Buffer radius in meters
    
    Returns:
        numpy array of elevation values, or None if error
    """
    try:
        import rasterio
        from rasterio.windows import from_bounds
        
        with rasterio.open(dem_path) as src:
            # Convert radius to degrees (approximate)
            # 1 degree ≈ 111,000 meters at equator
            radius_deg = radius_m / 111000
            
            # Define bounding box
            bounds = (lon - radius_deg, lat - radius_deg, 
                     lon + radius_deg, lat + radius_deg)
            
            # Read window
            window = from_bounds(*bounds, transform=src.transform)
            data = src.read(1, window=window)
            
            # Mask nodata values
            if src.nodata is not None:
                data = np.where(data == src.nodata, np.nan, data)
            
            # Filter to circular buffer
            height, width = data.shape
            y, x = np.ogrid[:height, :width]
            center_y, center_x = height / 2, width / 2
            
            # Pixel distance from center
            dist = np.sqrt((x - center_x)**2 + (y - center_y)**2)
            
            # Mask values outside radius
            # Approximate: pixels per meter
            pixels_per_meter = 1 / (src.res[0] * 111000)
            radius_pixels = radius_m * pixels_per_meter
            
            data = np.where(dist <= radius_pixels, data, np.nan)
            
            # Return flattened array without NaN
            valid_data = data[~np.isnan(data)]
            
            return valid_data if len(valid_data) > 0 else None
            
    except Exception as e:
        print(f"Error sampling DEM buffer at ({lon}, {lat}): {e}")
        return None


def compute_terrain_slope(dem_data: np.ndarray, pixel_size_m: float = 30) -> float:
    """
    Compute median terrain slope from DEM data.
    
    Args:
        dem_data: 2D array of elevation values
        pixel_size_m: DEM pixel size in meters
    
    Returns:
        Median slope in degrees
    """
    # Compute gradients
    gradient_y, gradient_x = np.gradient(dem_data, pixel_size_m)
    
    # Compute slope magnitude
    slope_rad = np.arctan(np.sqrt(gradient_x**2 + gradient_y**2))
    slope_deg = np.degrees(slope_rad)
    
    # Return median
    return float(np.median(slope_deg))


def compute_terrain_aspect(dem_data: np.ndarray) -> float:
    """
    Compute terrain aspect (direction of slope).
    
    Args:
        dem_data: 2D array of elevation values
    
    Returns:
        Aspect in degrees (0-360, 0=North)
    """
    # Compute gradients
    gradient_y, gradient_x = np.gradient(dem_data)
    
    # Compute aspect
    aspect_rad = np.arctan2(-gradient_y, gradient_x)
    aspect_deg = (np.degrees(aspect_rad) + 360) % 360
    
    # Return median
    return float(np.median(aspect_deg))


def sample_worldcover(lon: float, lat: float, worldcover_path: str) -> Optional[int]:
    """
    Sample ESA WorldCover land use classification at a point.
    
    Args:
        lon, lat: Point coordinates (decimal degrees, WGS84)
        worldcover_path: Path to WorldCover raster
    
    Returns:
        Land use class code, or None if no data
    """
    try:
        import rasterio
        from rasterio.transform import rowcol
        
        with rasterio.open(worldcover_path) as src:
            row, col = rowcol(src.transform, lon, lat)
            
            if 0 <= row < src.height and 0 <= col < src.width:
                window = ((row, row + 1), (col, col + 1))
                data = src.read(1, window=window)
                value = int(data[0, 0])
                
                if src.nodata is not None and value == src.nodata:
                    return None
                
                return value
            else:
                return None
                
    except Exception as e:
        print(f"Error sampling WorldCover at ({lon}, {lat}): {e}")
        return None


def remap_worldcover_to_clutter(worldcover_class: int) -> str:
    """
    Remap WorldCover classes to simplified clutter categories.
    
    WorldCover classes:
    10: Tree cover, 20: Shrubland, 30: Grassland, 40: Cropland, 50: Built-up,
    60: Bare/sparse vegetation, 70: Snow/ice, 80: Water, 90: Wetland, 95: Mangroves, 100: Moss/lichen
    
    Args:
        worldcover_class: WorldCover class code
    
    Returns:
        Simplified clutter category: urban, suburban, rural, water, forest
    """
    if worldcover_class == 50:
        return 'urban'
    elif worldcover_class in [90, 100]:
        return 'suburban'
    elif worldcover_class in [30, 40]:
        return 'rural'
    elif worldcover_class == 80:
        return 'water'
    elif worldcover_class in [10, 20, 95]:
        return 'forest'
    else:
        return 'rural'  # Default for bare/sparse, snow/ice


def circular_mean(angles_deg: np.ndarray) -> float:
    """
    Compute circular mean of angles.
    
    Args:
        angles_deg: Array of angles in degrees
    
    Returns:
        Circular mean in degrees (0-360)
    """
    angles_rad = np.radians(angles_deg)
    sin_sum = np.sum(np.sin(angles_rad))
    cos_sum = np.sum(np.cos(angles_rad))
    mean_rad = np.arctan2(sin_sum, cos_sum)
    mean_deg = (np.degrees(mean_rad) + 360) % 360
    return float(mean_deg)


def circular_std(angles_deg: np.ndarray) -> float:
    """
    Compute circular standard deviation of angles.
    
    Args:
        angles_deg: Array of angles in degrees
    
    Returns:
        Circular standard deviation in degrees
    """
    angles_rad = np.radians(angles_deg)
    sin_sum = np.sum(np.sin(angles_rad))
    cos_sum = np.sum(np.cos(angles_rad))
    n = len(angles_rad)
    
    r = np.sqrt(sin_sum**2 + cos_sum**2) / n
    std_rad = np.sqrt(-2 * np.log(r))
    std_deg = np.degrees(std_rad)
    
    return float(std_deg)