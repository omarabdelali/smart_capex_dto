"""
DEM Processor Service

Handles Digital Elevation Model (DEM) data processing for visualization and feature extraction.
Uses Copernicus GLO-30 DEM data (30m resolution).

Key Functions:
- Extract elevation at point coordinates
- Generate hillshade for 3D visualization
- Compute slope and aspect rasters
- Generate map tiles for Leaflet visualization

MVC: Business logic in services layer
"""

import numpy as np
import rasterio
from rasterio.warp import transform_bounds, reproject, Resampling
from rasterio.enums import ColorInterp
from rasterio.transform import from_bounds
from PIL import Image
import io
import logging
from pathlib import Path
from typing import Tuple, Optional, Dict
import math

logger = logging.getLogger(__name__)


class DEMProcessor:
    """Process DEM data for visualization and feature extraction."""
    
    def __init__(self, dem_path: str = None):
        """
        Initialize DEM processor.
        
        Args:
            dem_path: Path to DEM file (VRT or GeoTIFF). If None, uses default VRT mosaic.
        """
        if dem_path is None:
            # Use VRT mosaic covering all of Tunisia
            dem_path = Path(__file__).parent.parent.parent / 'data' / 'geographic' / 'dem' / 'copernicus_glo30.vrt'
        
        self.dem_path = str(dem_path)
        logger.info(f"Initialized DEMProcessor with {self.dem_path}")
    
    def get_elevation(self, lat: float, lon: float) -> Optional[float]:
        """
        Get elevation at a specific point.
        
        Args:
            lat: Latitude (WGS84)
            lon: Longitude (WGS84)
            
        Returns:
            Elevation in meters above sea level, or None if out of bounds
        """
        try:
            with rasterio.open(self.dem_path) as src:
                # Get pixel coordinates
                py, px = src.index(lon, lat)
                
                # Check bounds
                if px < 0 or py < 0 or px >= src.width or py >= src.height:
                    logger.warning(f"Point ({lat}, {lon}) out of DEM bounds")
                    return None
                
                # Read elevation value
                window = rasterio.windows.Window(px, py, 1, 1)
                elevation = src.read(1, window=window)[0, 0]
                
                # Check for NoData
                if src.nodata is not None and elevation == src.nodata:
                    return None
                
                return float(elevation)
                
        except Exception as e:
            logger.error(f"Error reading elevation at ({lat}, {lon}): {e}")
            return None
    
    def get_elevation_stats(self, lat: float, lon: float, buffer_m: float = 1000) -> Dict[str, float]:
        """
        Get elevation statistics within a buffer around a point.
        
        Args:
            lat: Center latitude (WGS84)
            lon: Center longitude (WGS84)
            buffer_m: Buffer radius in meters
            
        Returns:
            Dictionary with mean, min, max, std elevation
        """
        try:
            with rasterio.open(self.dem_path) as src:
                # Convert buffer from meters to degrees (approximate at this latitude)
                # 1 degree ~ 111 km at equator, adjust for latitude
                buffer_deg = buffer_m / (111000 * math.cos(math.radians(lat)))
                
                # Define bounds
                minx, miny = lon - buffer_deg, lat - buffer_deg
                maxx, maxy = lon + buffer_deg, lat + buffer_deg
                
                # Get window
                window = rasterio.windows.from_bounds(minx, miny, maxx, maxy, src.transform)
                
                # Read data
                data = src.read(1, window=window, masked=True)
                
                if data.size == 0:
                    return {'mean': None, 'min': None, 'max': None, 'std': None}
                
                return {
                    'mean': float(np.mean(data)),
                    'min': float(np.min(data)),
                    'max': float(np.max(data)),
                    'std': float(np.std(data))
                }
                
        except Exception as e:
            logger.error(f"Error computing elevation stats at ({lat}, {lon}): {e}")
            return {'mean': None, 'min': None, 'max': None, 'std': None}
    
    def compute_slope(self, lat: float, lon: float, buffer_m: float = 200) -> Optional[float]:
        """
        Compute median terrain slope within buffer.
        
        Args:
            lat: Center latitude (WGS84)
            lon: Center longitude (WGS84)
            buffer_m: Buffer radius in meters
            
        Returns:
            Median slope in degrees, or None if error
        """
        try:
            with rasterio.open(self.dem_path) as src:
                # Convert buffer to degrees
                buffer_deg = buffer_m / (111000 * math.cos(math.radians(lat)))
                
                # Get window
                minx, miny = lon - buffer_deg, lat - buffer_deg
                maxx, maxy = lon + buffer_deg, lat + buffer_deg
                window = rasterio.windows.from_bounds(minx, miny, maxx, maxy, src.transform)
                
                # Read elevation data
                dem = src.read(1, window=window, masked=True)
                
                if dem.size == 0:
                    return None
                
                # Compute slope using gradient (rise over run)
                # Get pixel resolution in meters
                transform = src.window_transform(window)
                pixel_size_x = abs(transform.a) * 111000 * math.cos(math.radians(lat))
                pixel_size_y = abs(transform.e) * 111000
                
                # Compute gradients
                dy, dx = np.gradient(dem.filled(dem.mean()))
                slope_rad = np.arctan(np.sqrt((dx / pixel_size_x)**2 + (dy / pixel_size_y)**2))
                slope_deg = np.degrees(slope_rad)
                
                return float(np.median(slope_deg))
                
        except Exception as e:
            logger.error(f"Error computing slope at ({lat}, {lon}): {e}")
            return None
    
    def compute_aspect(self, lat: float, lon: float, buffer_m: float = 200) -> Optional[float]:
        """
        Compute dominant terrain aspect (slope direction) within buffer.
        
        Args:
            lat: Center latitude (WGS84)
            lon: Center longitude (WGS84)
            buffer_m: Buffer radius in meters
            
        Returns:
            Dominant aspect in degrees (0-360, 0=North), or None if error
        """
        try:
            with rasterio.open(self.dem_path) as src:
                # Convert buffer to degrees
                buffer_deg = buffer_m / (111000 * math.cos(math.radians(lat)))
                
                # Get window
                minx, miny = lon - buffer_deg, lat - buffer_deg
                maxx, maxy = lon + buffer_deg, lat + buffer_deg
                window = rasterio.windows.from_bounds(minx, miny, maxx, maxy, src.transform)
                
                # Read elevation data
                dem = src.read(1, window=window, masked=True)
                
                if dem.size == 0:
                    return None
                
                # Compute aspect using gradient
                dy, dx = np.gradient(dem.filled(dem.mean()))
                
                # Aspect = atan2(dy, dx) converted to 0-360° with 0=North
                aspect_rad = np.arctan2(dy, -dx)  # Note: -dx to get correct direction
                aspect_deg = np.degrees(aspect_rad)
                
                # Convert to 0-360 range with 0=North
                aspect_deg = (90 - aspect_deg) % 360
                
                # Return circular mean (weighted by slope magnitude)
                slope = np.sqrt(dx**2 + dy**2)
                weights = slope / np.sum(slope) if np.sum(slope) > 0 else None
                
                if weights is not None:
                    # Circular weighted mean
                    sin_sum = np.sum(weights * np.sin(np.radians(aspect_deg)))
                    cos_sum = np.sum(weights * np.cos(np.radians(aspect_deg)))
                    mean_aspect = np.degrees(np.arctan2(sin_sum, cos_sum)) % 360
                    return float(mean_aspect)
                else:
                    return float(np.median(aspect_deg))
                
        except Exception as e:
            logger.error(f"Error computing aspect at ({lat}, {lon}): {e}")
            return None
    
    def compute_roughness(self, lat: float, lon: float, buffer_m: float = 1000) -> Optional[float]:
        """
        Compute terrain roughness (elevation standard deviation) within buffer.
        
        Args:
            lat: Center latitude (WGS84)
            lon: Center longitude (WGS84)
            buffer_m: Buffer radius in meters
            
        Returns:
            Terrain roughness in meters (std dev of elevation), or None if error
        """
        stats = self.get_elevation_stats(lat, lon, buffer_m)
        return stats.get('std')
    
    def generate_hillshade(
        self,
        bbox: Tuple[float, float, float, float],
        width: int = 256,
        height: int = 256,
        azimuth: float = 315,
        altitude: float = 45
    ) -> Optional[bytes]:
        """
        Generate hillshade image for visualization.
        
        Args:
            bbox: Bounding box (minx, miny, maxx, maxy) in WGS84
            width: Output image width in pixels
            height: Output image height in pixels
            azimuth: Light source azimuth (0-360°, 0=North)
            altitude: Light source altitude (0-90°)
            
        Returns:
            PNG image bytes, or None if error
        """
        try:
            with rasterio.open(self.dem_path) as src:
                # Get window for bbox
                window = rasterio.windows.from_bounds(*bbox, src.transform)
                
                # Read DEM data
                dem = src.read(1, window=window, masked=True)
                
                if dem.size == 0:
                    return None
                
                # Resize to requested dimensions
                from scipy.ndimage import zoom
                zoom_factors = (height / dem.shape[0], width / dem.shape[1])
                dem_resized = zoom(dem.filled(dem.mean()), zoom_factors, order=1)
                
                # Compute hillshade
                azimuth_rad = np.radians(360 - azimuth + 90)  # Convert to math convention
                altitude_rad = np.radians(altitude)
                
                # Compute gradients
                dy, dx = np.gradient(dem_resized)
                
                # Compute slope and aspect
                slope = np.arctan(np.sqrt(dx**2 + dy**2))
                aspect = np.arctan2(-dx, dy)
                
                # Hillshade formula
                hillshade = (
                    np.sin(altitude_rad) * np.cos(slope) +
                    np.cos(altitude_rad) * np.sin(slope) * np.cos(azimuth_rad - aspect)
                )
                
                # Normalize to 0-255
                hillshade = np.clip(hillshade * 255, 0, 255).astype(np.uint8)
                
                # Convert to PIL Image
                img = Image.fromarray(hillshade, mode='L')
                
                # Save to bytes
                buffer = io.BytesIO()
                img.save(buffer, format='PNG')
                buffer.seek(0)
                
                return buffer.getvalue()
                
        except Exception as e:
            logger.error(f"Error generating hillshade for bbox {bbox}: {e}")
            return None
    
    def generate_elevation_tile(
        self,
        bbox: Tuple[float, float, float, float],
        width: int = 256,
        height: int = 256,
        colormap: str = 'terrain'
    ) -> Optional[bytes]:
        """
        Generate elevation map tile with colormap.
        
        Args:
            bbox: Bounding box (minx, miny, maxx, maxy) in WGS84
            width: Output image width in pixels
            height: Output image height in pixels
            colormap: Matplotlib colormap name
            
        Returns:
            PNG image bytes, or None if error
        """
        try:
            import matplotlib.pyplot as plt
            import matplotlib.cm as cm
            
            with rasterio.open(self.dem_path) as src:
                # Get window for bbox
                window = rasterio.windows.from_bounds(*bbox, src.transform)
                
                # Read DEM data
                dem = src.read(1, window=window, masked=True)
                
                if dem.size == 0:
                    return None
                
                # Resize to requested dimensions
                from scipy.ndimage import zoom
                zoom_factors = (height / dem.shape[0], width / dem.shape[1])
                dem_resized = zoom(dem.filled(dem.mean()), zoom_factors, order=1)
                
                # Normalize elevation to 0-1
                vmin, vmax = dem_resized.min(), dem_resized.max()
                if vmax > vmin:
                    dem_normalized = (dem_resized - vmin) / (vmax - vmin)
                else:
                    dem_normalized = np.zeros_like(dem_resized)
                
                # Apply colormap
                cmap = cm.get_cmap(colormap)
                colored = cmap(dem_normalized)
                
                # Convert to RGB (0-255)
                rgb = (colored[:, :, :3] * 255).astype(np.uint8)
                
                # Convert to PIL Image
                img = Image.fromarray(rgb, mode='RGB')
                
                # Save to bytes
                buffer = io.BytesIO()
                img.save(buffer, format='PNG')
                buffer.seek(0)
                
                return buffer.getvalue()
                
        except Exception as e:
            logger.error(f"Error generating elevation tile for bbox {bbox}: {e}")
            return None


# Singleton instance
_dem_processor = None

def get_dem_processor() -> DEMProcessor:
    """Get singleton DEM processor instance."""
    global _dem_processor
    if _dem_processor is None:
        _dem_processor = DEMProcessor()
    return _dem_processor