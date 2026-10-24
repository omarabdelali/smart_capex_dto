"""
Feature Extraction Pipeline for Smart CAPEX.
Orchestrates all feature extractors and saves to database.
"""

from typing import List, Dict, Optional
import logging
from datetime import datetime

from django.db import transaction

from core.models import Site
from core.models.features import (
    ConfigurationFeatures,
    GeometricFeatures,
    ClutterFeatures,
    SpatialFeatures,
    ANPFeatures,
    KPIFeatures,
    ClusterFeatures,
)

from .geometric import GeometricFeatureExtractor
from .clutter import ClutterFeatureExtractor
from .spatial import SpatialFeatureExtractor
from .anp import ANPComputer
from .kpi import KPIFeatureExtractor

logger = logging.getLogger(__name__)


class FeatureExtractionPipeline:
    """
    Orchestrates feature extraction for Smart CAPEX Phase 1.
    
    Extracts and saves all 60 Phase 1 features:
    - Configuration (10): From cell plan data
    - Geometric (4): DEM-based terrain features
    - Clutter (4): Land cover and building features
    - Spatial (8): Neighbor-based features
    - ANP (15): Angular Neighborhood Profile (KEY INNOVATION)
    - KPI (12): Pre-launch KPI features
    - Cluster (6): Clustering features
    - event_type (1): Launch vs existing classification
    """
    
    def __init__(
        self,
        dem_vrt_path: str = "data/geographic/dem/copernicus_glo30.vrt",
        worldcover_path: str = "data/geographic/worldcover/ESA_WorldCover_10m_2021_v200_Tunisia.tif",
        maos_csv_path: Optional[str] = None
    ):
        """
        Initialize feature extraction pipeline.
        
        Args:
            dem_vrt_path: Path to DEM VRT mosaic
            worldcover_path: Path to WorldCover GeoTIFF
            maos_csv_path: Path to MAOS monthly KPI CSV (optional)
        """
        # Initialize extractors
        self.geometric_extractor = GeometricFeatureExtractor(dem_vrt_path)
        self.clutter_extractor = ClutterFeatureExtractor(worldcover_path)
        
        # KPI extractor (optional - only if MAOS data available)
        self.kpi_extractor = None
        if maos_csv_path:
            try:
                self.kpi_extractor = KPIFeatureExtractor(maos_csv_path)
                logger.info("KPI extractor initialized with MAOS data")
            except Exception as e:
                logger.warning(f"Could not initialize KPI extractor: {e}")
        
        logger.info("Feature extraction pipeline initialized")
    
    def extract_and_save_features(
        self,
        cluster_id: Optional[int] = None,
        site_ids: Optional[List[str]] = None,
        skip_existing: bool = True
    ) -> Dict[str, int]:
        """
        Extract all features for sites and save to database.
        
        Args:
            cluster_id: Extract features for sites in this cluster only (None = all sites)
            site_ids: Extract features for specific site IDs (overrides cluster_id)
            skip_existing: Skip sites that already have features extracted
            
        Returns:
            Dictionary with extraction statistics
        """
        # Get sites to process
        if site_ids:
            sites = Site.objects.filter(site_id__in=site_ids)
        elif cluster_id is not None:
            sites = Site.objects.filter(cluster_id=cluster_id)
        else:
            sites = Site.objects.all()
        
        total_sites = sites.count()
        logger.info(f"Processing {total_sites} sites...")
        
        # Filter out sites with existing features if requested
        if skip_existing:
            sites = sites.filter(geometric_features__isnull=True)
            logger.info(f"{sites.count()} sites need feature extraction (skipping {total_sites - sites.count()} with existing features)")
        
        if sites.count() == 0:
            logger.info("No sites to process")
            return {'total': 0, 'successful': 0, 'failed': 0}
        
        # Prepare site data for spatial/ANP extractors
        sites_data = list(sites.values('site_id', 'latitude', 'longitude', 'cluster_id'))
        
        # Initialize spatial and ANP extractors (need all sites data)
        spatial_extractor = SpatialFeatureExtractor(sites_data)
        anp_computer = ANPComputer()
        
        # Track statistics
        stats = {
            'total': sites.count(),
            'successful': 0,
            'failed': 0,
            'geometric_failures': 0,
            'clutter_failures': 0,
            'spatial_failures': 0,
            'anp_failures': 0,
            'kpi_failures': 0,
        }
        
        # Process each site
        for idx, site in enumerate(sites, 1):
            try:
                logger.info(f"Processing site {site.site_id} ({idx}/{stats['total']})...")
                
                with transaction.atomic():
                    # 1. Geometric features (DEM-based)
                    geo_result = self.geometric_extractor.extract_features(
                        site.site_id, site.latitude, site.longitude
                    )
                    if not geo_result.success:
                        stats['geometric_failures'] += 1
                    
                    GeometricFeatures.objects.update_or_create(
                        site=site,
                        defaults=self.geometric_extractor.to_dict(geo_result)
                    )
                    
                    # 2. Clutter features (land cover, buildings)
                    clutter_result = self.clutter_extractor.extract_features(
                        site.site_id, site.latitude, site.longitude
                    )
                    if not clutter_result.success:
                        stats['clutter_failures'] += 1
                    
                    ClutterFeatures.objects.update_or_create(
                        site=site,
                        defaults=self.clutter_extractor.to_dict(clutter_result)
                    )
                    
                    # 3. Spatial features (neighbor analysis)
                    spatial_result = spatial_extractor.extract_features(site.site_id)
                    if not spatial_result.success:
                        stats['spatial_failures'] += 1
                    
                    SpatialFeatures.objects.update_or_create(
                        site=site,
                        defaults=spatial_extractor.to_dict(spatial_result)
                    )
                    
                    # 4. ANP features (Angular Neighborhood Profile - KEY INNOVATION)
                    anp_result = self._extract_anp_features(site, anp_computer, sites_data)
                    if anp_result is None:
                        stats['anp_failures'] += 1
                    else:
                        ANPFeatures.objects.update_or_create(
                            site=site,
                            defaults=anp_result
                        )
                    
                    # 5. KPI features (if MAOS data available)
                    if self.kpi_extractor:
                        kpi_result = self.kpi_extractor.extract_features(site.site_id)
                        if not kpi_result.success:
                            stats['kpi_failures'] += 1
                        
                        KPIFeatures.objects.update_or_create(
                            site=site,
                            defaults=self.kpi_extractor.to_dict(kpi_result)
                        )
                    
                    # 6. Configuration features (from cell plan - already populated)
                    # 7. Cluster features (from clustering - already populated)
                    
                    stats['successful'] += 1
                    logger.info(f"✓ Site {site.site_id} features extracted successfully")
                    
            except Exception as e:
                stats['failed'] += 1
                logger.error(f"✗ Failed to extract features for site {site.site_id}: {e}")
        
        # Log summary
        logger.info(f"Feature extraction complete:")
        logger.info(f"  Total sites: {stats['total']}")
        logger.info(f"  Successful: {stats['successful']}")
        logger.info(f"  Failed: {stats['failed']}")
        logger.info(f"  Geometric failures: {stats['geometric_failures']}")
        logger.info(f"  Clutter failures: {stats['clutter_failures']}")
        logger.info(f"  Spatial failures: {stats['spatial_failures']}")
        logger.info(f"  ANP failures: {stats['anp_failures']}")
        logger.info(f"  KPI failures: {stats['kpi_failures']}")
        
        return stats
    
    def _extract_anp_features(
        self,
        site: Site,
        anp_computer: ANPComputer,
        sites_data: List[Dict]
    ) -> Optional[Dict]:
        """
        Extract ANP features for a site.
        
        Args:
            site: Site model instance
            anp_computer: ANP computer instance
            sites_data: List of all sites with coords
            
        Returns:
            Dictionary of ANP features or None if extraction failed
        """
        try:
            # Get neighbor data (within 5km)
            neighbors = []
            for other_site in sites_data:
                if other_site['site_id'] == site.site_id:
                    continue
                
                # Simple distance check (approximate)
                lat_diff = abs(other_site['latitude'] - site.latitude)
                lon_diff = abs(other_site['longitude'] - site.longitude)
                
                # Rough 5km filter (0.045° ≈ 5km at Tunisia latitude)
                if lat_diff < 0.045 and lon_diff < 0.045:
                    neighbors.append({
                        'latitude': other_site['latitude'],
                        'longitude': other_site['longitude'],
                    })
            
            # Compute ANP features
            neighbor_coords = [(n['latitude'], n['longitude']) for n in neighbors]
            
            anp_result = anp_computer.compute_anp(
                target_lat=site.latitude,
                target_lon=site.longitude,
                neighbor_coords=neighbor_coords
            )
            
            return {
                'n_tier1': anp_result['n_tier1'],
                'n_tier2': anp_result['n_tier2'],
                't1_to_t2_ratio': anp_result['t1_to_t2_ratio'],
                't1_nearest_m': anp_result['t1_nearest_m'],
                't2_nearest_m': anp_result['t2_nearest_m'],
                'angular_uniformity': anp_result['angular_uniformity'],
                'max_empty_arc_deg': anp_result['max_empty_arc_deg'],
                'n_empty_bins': anp_result['n_empty_bins'],
                'dominant_sector_deg': anp_result['dominant_sector_deg'],
                'dominant_sector_count': anp_result['dominant_sector_count'],
                'edge_score': anp_result['edge_score'],
                'bearing_stddev_deg': anp_result['bearing_stddev_deg'],
                'avg_neighbor_dist_t1_m': anp_result['avg_neighbor_dist_t1_m'],
                'avg_neighbor_dist_t2_m': anp_result['avg_neighbor_dist_t2_m'],
                'coverage_asymmetry': anp_result['coverage_asymmetry'],
            }
            
        except Exception as e:
            logger.error(f"Failed to extract ANP features for site {site.site_id}: {e}")
            return None