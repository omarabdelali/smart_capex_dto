"""
Clutter feature extraction for Smart CAPEX.
Computes land cover and building-based features for sites.
"""

from typing import Dict, Optional, List, Tuple
import logging
from dataclasses import dataclass
from pathlib import Path

import rasterio
from rasterio.warp import transform_geom
from rasterio.mask import mask
from shapely.geometry import Point, mapping
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class ClutterFeatureResult:
    """Result of clutter feature extraction."""
    site_id: str
    urban_pct: Optional[float]
    vegetation_pct: Optional[float]
    water_pct: Optional[float]
    building_density: Optional[float]
    success: bool
    error_message: Optional[str] = None


class ClutterFeatureExtractor:
    """
    Extracts land cover and building-based clutter features for telecom sites.
    
    Computes 4 primary features from Smart CAPEX Phase 1 specification:
    - urban_pct: Percentage of urban/built-up area in 1km radius (0-100)
    - vegetation_pct: Percentage of vegetation/forest in 1km radius (0-100)
    - water_pct: Percentage of water bodies in 1km radius (0-100)
    - building_density: Building footprint density in 1km radius (0-100)
    
    Data sources:
    - ESA WorldCover 2021 (10m resolution land cover)
    - OpenStreetMap or GHSL building footprints
    
    WorldCover classes (https://esa-worldcover.org/en):
    - 10: Tree cover
    - 20: Shrubland
    - 30: Grassland
    - 40: Cropland
    - 50: Built-up
    - 60: Bare / sparse vegetation
    - 70: Snow and ice
    - 80: Permanent water bodies
    - 90: Herbaceous wetland
    - 95: Mangroves
    - 100: Moss and lichen
    """
    
    # WorldCover class mapping
    URBAN_CLASSES = [50]  # Built-up
    VEGETATION_CLASSES = [10, 20, 30, 40, 90, 95]  # Tree, Shrub, Grass, Crop, Wetland, Mangroves
    WATER_CLASSES = [80]  # Permanent water
    
    def __init__(
        self,
        worldcover_path: str = "data/geographic/worldcover/ESA_WorldCover_10m_2021_v200_Tunisia.tif",
        buildings_path: Optional[str] = None
    ):
        """
        Initialize clutter feature extractor.
        
        Args:
            worldcover_path: Path to ESA WorldCover GeoTIFF
            buildings_path: Path to buildings vector layer (optional, for building_density)
        """
        self.worldcover_path = Path(worldcover_path)
        self.buildings_path = Path(buildings_path) if buildings_path else None
        
        # Validate WorldCover exists
        if not self.worldcover_path.exists():
            logger.warning(f"WorldCover file not found: {worldcover_path}")
        else:
            logger.info(f"Initialized ClutterFeatureExtractor with WorldCover: {worldcover_path}")
    
    def extract_features(
        self,
        site_id: str,
        latitude: float,
        longitude: float,
        buffer_m: float = 1000
    ) -> ClutterFeatureResult:
        """
        Extract all clutter features for a site.
        
        Args:
            site_id: Unique site identifier
            latitude: Site latitude (WGS84)
            longitude: Site longitude (WGS84)
            buffer_m: Buffer radius in meters (default 1000m)
            
        Returns:
            ClutterFeatureResult with extracted features
        """
        try:
            # Create buffer geometry (approximate degrees from meters)
            # At Tunisia latitude (~35°N), 1° ≈ 111 km
            buffer_deg = buffer_m / 111000
            point = Point(longitude, latitude)
            circle = point.buffer(buffer_deg)
            
            # Extract land cover percentages
            urban_pct, vegetation_pct, water_pct = self._extract_land_cover_percentages(
                circle, latitude, longitude
            )
            
            # Extract building density (placeholder - requires building data)
            building_density = self._extract_building_density(circle, buffer_m)
            
            return ClutterFeatureResult(
                site_id=site_id,
                urban_pct=urban_pct,
                vegetation_pct=vegetation_pct,
                water_pct=water_pct,
                building_density=building_density,
                success=True
            )
            
        except Exception as e:
            logger.error(f"Failed to extract clutter features for site {site_id}: {e}")
            return ClutterFeatureResult(
                site_id=site_id,
                urban_pct=None,
                vegetation_pct=None,
                water_pct=None,
                building_density=None,
                success=False,
                error_message=str(e)
            )
    
    def _extract_land_cover_percentages(
        self,
        geometry,
        latitude: float,
        longitude: float
    ) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """
        Extract land cover class percentages from WorldCover.
        
        Args:
            geometry: Shapely geometry (circle buffer)
            latitude: Site latitude
            longitude: Site longitude
            
        Returns:
            Tuple of (urban_pct, vegetation_pct, water_pct)
        """
        if not self.worldcover_path.exists():
            logger.warning("WorldCover data not available, returning None values")
            return None, None, None
        
        try:
            with rasterio.open(self.worldcover_path) as src:
                # Transform geometry to raster CRS
                geom_transformed = transform_geom(
                    'EPSG:4326',
                    src.crs,
                    mapping(geometry)
                )
                
                # Mask raster with geometry
                out_image, out_transform = mask(src, [geom_transformed], crop=True, nodata=0)
                
                # Extract land cover array (first band)
                lc_array = out_image[0]
                
                # Filter out nodata
                valid_pixels = lc_array[lc_array > 0]
                
                if len(valid_pixels) == 0:
                    return 0.0, 0.0, 0.0
                
                # Calculate percentages
                total = len(valid_pixels)
                
                urban_pixels = np.isin(valid_pixels, self.URBAN_CLASSES).sum()
                vegetation_pixels = np.isin(valid_pixels, self.VEGETATION_CLASSES).sum()
                water_pixels = np.isin(valid_pixels, self.WATER_CLASSES).sum()
                
                urban_pct = (urban_pixels / total) * 100
                vegetation_pct = (vegetation_pixels / total) * 100
                water_pct = (water_pixels / total) * 100
                
                return urban_pct, vegetation_pct, water_pct
                
        except Exception as e:
            logger.error(f"Error extracting land cover percentages: {e}")
            return None, None, None
    
    def _extract_building_density(self, geometry, buffer_m: float) -> Optional[float]:
        """
        Extract building footprint density.
        
        This is a placeholder implementation. In production, this would:
        1. Load building footprints from OSM or GHSL
        2. Clip to buffer geometry
        3. Calculate total building area / buffer area * 100
        
        Args:
            geometry: Shapely geometry (circle buffer)
            buffer_m: Buffer radius in meters
            
        Returns:
            Building density percentage (0-100) or None
        """
        # Placeholder: Return None until building data is available
        # In Phase 1, this feature may be omitted if building data is unavailable
        
        if self.buildings_path is None or not self.buildings_path.exists():
            logger.debug("Building data not available, returning None for building_density")
            return None
        
        # TODO: Implement building density calculation when data is available
        # import geopandas as gpd
        # buildings = gpd.read_file(self.buildings_path)
        # clipped = buildings.clip(geometry)
        # building_area = clipped.geometry.area.sum()
        # buffer_area = geometry.area * 111000 * 111000  # Convert deg² to m²
        # return (building_area / buffer_area) * 100
        
        return None
    
    def extract_batch(self, sites: List[Dict], buffer_m: float = 1000) -> List[ClutterFeatureResult]:
        """
        Extract clutter features for multiple sites.
        
        Args:
            sites: List of dicts with keys: site_id, latitude, longitude
            buffer_m: Buffer radius in meters
            
        Returns:
            List of ClutterFeatureResult objects
        """
        results = []
        total = len(sites)
        
        logger.info(f"Extracting clutter features for {total} sites...")
        
        for idx, site in enumerate(sites, 1):
            site_id = site['site_id']
            lat = site['latitude']
            lon = site['longitude']
            
            result = self.extract_features(site_id, lat, lon, buffer_m)
            results.append(result)
            
            if idx % 10 == 0 or idx == total:
                logger.info(f"Processed {idx}/{total} sites ({idx/total*100:.1f}%)")
        
        # Summary statistics
        successful = sum(1 for r in results if r.success)
        failed = total - successful
        
        logger.info(f"Clutter feature extraction complete: {successful} succeeded, {failed} failed")
        
        return results
    
    def to_dict(self, result: ClutterFeatureResult) -> Dict:
        """
        Convert ClutterFeatureResult to dictionary for database storage.
        
        Args:
            result: ClutterFeatureResult object
            
        Returns:
            Dictionary with feature values (None if extraction failed)
        """
        if not result.success:
            return {
                'urban_pct': None,
                'vegetation_pct': None,
                'water_pct': None,
                'building_density': None,
            }
        
        # Determine dominant clutter type
        dominant_clutter = 'rural'  # Default
        if result.urban_pct and result.urban_pct > 50:
            dominant_clutter = 'urban'
        elif result.urban_pct and result.urban_pct > 20:
            dominant_clutter = 'suburban'
        elif result.water_pct and result.water_pct > 50:
            dominant_clutter = 'water'
        elif result.vegetation_pct and result.vegetation_pct > 70:
            dominant_clutter = 'forest'
        
        # Calculate clutter entropy (land use diversity)
        # Shannon entropy of land cover percentages
        import numpy as np
        percentages = [
            result.urban_pct or 0,
            result.vegetation_pct or 0,
            result.water_pct or 0,
            100 - (result.urban_pct or 0) - (result.vegetation_pct or 0) - (result.water_pct or 0)  # other
        ]
        percentages = [p/100 for p in percentages if p > 0]
        clutter_entropy = -sum(p * np.log(p) for p in percentages) if percentages else 0.0
        
        return {
            'dominant_clutter': dominant_clutter,
            'clutter_entropy_2km': float(clutter_entropy),
            'pct_building_area_1km': result.building_density or 0.0,
            'avg_building_height_m': 0.0,  # TODO: Need GHSL building height data
        }
