"""
Geometric feature extraction for Smart CAPEX.
Computes DEM-based terrain features for sites.
"""

from typing import Dict, Optional, List
import logging
from dataclasses import dataclass

from services.visualization.dem_processor import DEMProcessor

logger = logging.getLogger(__name__)


@dataclass
class GeometricFeatureResult:
    """Result of geometric feature extraction."""
    site_id: str
    elevation_m: Optional[float]
    slope_deg: Optional[float]
    aspect_deg: Optional[float]
    roughness_m: Optional[float]
    elevation_std_1km: Optional[float]
    elevation_range_1km: Optional[float]
    elevation_mean_1km: Optional[float]
    antenna_height_m: float
    success: bool
    error_message: Optional[str] = None


class GeometricFeatureExtractor:
    """
    Extracts DEM-based geometric features for telecom sites.
    
    Computes 4 primary features from Smart CAPEX Phase 1 specification:
    - elevation_m: Site elevation above sea level (meters)
    - slope_deg: Local terrain slope (degrees, 0-90)
    - aspect_deg: Slope orientation (degrees, 0-360, 0=North)
    - roughness_m: Terrain roughness (meters, std dev in 1km radius)
    
    Plus additional statistical features for 1km neighborhood:
    - elevation_std_1km: Standard deviation of elevations
    - elevation_range_1km: Max - Min elevation
    - elevation_mean_1km: Mean elevation
    """
    
    def __init__(self, dem_vrt_path: str = "data/geographic/dem/copernicus_glo30.vrt"):
        """
        Initialize geometric feature extractor.
        
        Args:
            dem_vrt_path: Path to DEM VRT mosaic file
        """
        self.dem_processor = DEMProcessor(dem_vrt_path)
        logger.info(f"Initialized GeometricFeatureExtractor with DEM: {dem_vrt_path}")
    
    def extract_features(self, site_id: str, latitude: float, longitude: float, antenna_height_m: float = 0) -> GeometricFeatureResult:
        """
        Extract all geometric features for a site.
        
        Args:
            site_id: Unique site identifier
            latitude: Site latitude (WGS84)
            longitude: Site longitude (WGS84)
            
        Returns:
            GeometricFeatureResult with extracted features
        """
        try:
            # Primary features
            elevation = self.dem_processor.get_elevation(latitude, longitude)
            slope = self.dem_processor.compute_slope(latitude, longitude, buffer_m=200)
            aspect = self.dem_processor.compute_aspect(latitude, longitude, buffer_m=200)
            roughness = self.dem_processor.compute_roughness(latitude, longitude, buffer_m=1000)
            
            # 1km neighborhood statistics
            stats = self.dem_processor.get_elevation_stats(latitude, longitude, buffer_m=1000)
            
            return GeometricFeatureResult(
                site_id=site_id,
                elevation_m=elevation,
                slope_deg=slope,
                aspect_deg=aspect,
                roughness_m=roughness,
                elevation_std_1km=stats.get('std'),
                elevation_range_1km=stats.get('range'),
                elevation_mean_1km=stats.get('mean'),
                antenna_height_m=antenna_height_m,
                success=True
            )
            
        except Exception as e:
            logger.error(f"Failed to extract geometric features for site {site_id}: {e}")
            return GeometricFeatureResult(
                site_id=site_id,
                elevation_m=None,
                slope_deg=None,
                aspect_deg=None,
                roughness_m=None,
                elevation_std_1km=None,
                elevation_range_1km=None,
                elevation_mean_1km=None,
                antenna_height_m=antenna_height_m,
                success=False,
                error_message=str(e)
            )
    
    def extract_batch(self, sites: List[Dict]) -> List[GeometricFeatureResult]:
        """
        Extract geometric features for multiple sites.
        
        Args:
            sites: List of dicts with keys: site_id, latitude, longitude
            
        Returns:
            List of GeometricFeatureResult objects
        """
        results = []
        total = len(sites)
        
        logger.info(f"Extracting geometric features for {total} sites...")
        
        for idx, site in enumerate(sites, 1):
            site_id = site['site_id']
            lat = site['latitude']
            lon = site['longitude']
            
            result = self.extract_features(site_id, lat, lon)
            results.append(result)
            
            if idx % 10 == 0 or idx == total:
                logger.info(f"Processed {idx}/{total} sites ({idx/total*100:.1f}%)")
        
        # Summary statistics
        successful = sum(1 for r in results if r.success)
        failed = total - successful
        
        logger.info(f"Geometric feature extraction complete: {successful} succeeded, {failed} failed")
        
        return results
    
    def to_dict(self, result: GeometricFeatureResult) -> Dict:
        """
        Convert GeometricFeatureResult to dictionary for database storage.
        
        Args:
            result: GeometricFeatureResult object
            
        Returns:
            Dictionary with feature values (None if extraction failed)
        """
        if not result.success:
            return {
                'z_antenna_m': 0.0,
                'terrain_slope_deg': 0.0,
                'terrain_aspect_deg': 0.0,
                'terrain_roughness_m': 0.0,
            }
        
        return {
            'z_antenna_m': result.elevation_m + result.antenna_height_m if result.elevation_m is not None else None,
            'terrain_slope_deg': result.slope_deg,
            'terrain_aspect_deg': result.aspect_deg,
            'terrain_roughness_m': result.roughness_m,
        }
