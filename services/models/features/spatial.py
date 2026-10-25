"""
Spatial feature extraction for Smart CAPEX.
Computes neighbor-based spatial features for sites.
"""

from typing import Dict, Optional, List
import logging
from dataclasses import dataclass
import math

import numpy as np
from scipy.spatial import distance_matrix

logger = logging.getLogger(__name__)


@dataclass
class SpatialFeatureResult:
    """Result of spatial feature extraction."""
    site_id: str
    neighbor_count_1km: Optional[int]
    neighbor_count_2km: Optional[int]
    neighbor_count_5km: Optional[int]
    neighbor_count_3km: Optional[int]
    n_2g_sites_2km: Optional[int]
    n_3g_sites_2km: Optional[int]
    n_4g_sites_2km: Optional[int]
    neighbor_avg_antenna_height_m: Optional[float]
    avg_neighbor_distance_km: Optional[float]
    nearest_neighbor_distance_km: Optional[float]
    density_score: Optional[float]
    isolation_score: Optional[float]
    cluster_centrality: Optional[float]
    success: bool
    error_message: Optional[str] = None


class SpatialFeatureExtractor:
    """
    Extracts neighbor-based spatial features for telecom sites.
    
    Computes 8 primary features from Smart CAPEX Phase 1 specification:
    - neighbor_count_1km: Number of neighboring sites within 1km
    - neighbor_count_2km: Number of neighboring sites within 2km
    - neighbor_count_5km: Number of neighboring sites within 5km
    - avg_neighbor_distance_km: Average distance to all neighbors in 5km (km)
    - nearest_neighbor_distance_km: Distance to nearest neighbor (km)
    - density_score: Spatial density metric (neighbors per km²)
    - isolation_score: Inverse of nearest neighbor distance (0=isolated, high=dense)
    - cluster_centrality: Distance from site to cluster centroid (km)
    
    These features help distinguish edge sites from interior sites.
    """
    
    def __init__(self, sites_data: List[Dict], site_technologies=None, site_antenna_heights=None):
        """
        Initialize spatial feature extractor.
        
        Args:
            sites_data: List of all sites with keys: site_id, latitude, longitude, cluster_id
        """
        self.sites_data = sites_data
        self.site_coords = {
            site['site_id']: (site['latitude'], site['longitude'])
            for site in sites_data
        }
        self.site_clusters = {
            site['site_id']: site.get('cluster_id')
            for site in sites_data
        }
        self.site_technologies = site_technologies or {}
        self.site_antenna_heights = site_antenna_heights or {}
        
        logger.info(f"Initialized SpatialFeatureExtractor with {len(sites_data)} sites")
    
    def extract_features(self, site_id: str) -> SpatialFeatureResult:
        """
        Extract all spatial features for a site.
        
        Args:
            site_id: Unique site identifier
            
        Returns:
            SpatialFeatureResult with extracted features
        """
        try:
            if site_id not in self.site_coords:
                raise ValueError(f"Site {site_id} not found in sites data")
            
            site_lat, site_lon = self.site_coords[site_id]
            cluster_id = self.site_clusters[site_id]
            
            # Get all other sites
            other_sites = [
                (sid, lat, lon) 
                for sid, (lat, lon) in self.site_coords.items() 
                if sid != site_id
            ]
            
            if len(other_sites) == 0:
                # Single site - all features are zero/None
                return SpatialFeatureResult(
                    site_id=site_id,
                    neighbor_count_1km=0,
                    neighbor_count_2km=0,
                    neighbor_count_5km=0,
                    neighbor_count_3km=0,
                    n_2g_sites_2km=0,
                    n_3g_sites_2km=0,
                    n_4g_sites_2km=0,
                    neighbor_avg_antenna_height_m=0.0,
                    avg_neighbor_distance_km=None,
                    nearest_neighbor_distance_km=None,
                    density_score=0.0,
                    isolation_score=0.0,
                    cluster_centrality=None,
                    success=True
                )
            
            # Calculate distances to all other sites
            distances_km = []
            for other_id, other_lat, other_lon in other_sites:
                dist_km = self._haversine_distance(site_lat, site_lon, other_lat, other_lon)
                distances_km.append(dist_km)
            
            distances_km = np.array(distances_km)
            
            # Neighbor counts
            neighbor_count_1km = int(np.sum(distances_km <= 1.0))
            neighbor_count_2km = int(np.sum(distances_km <= 2.0))
            neighbor_count_3km = int(np.sum(distances_km <= 3.0))
            neighbor_count_5km = int(np.sum(distances_km <= 5.0))

            neighbor_sites_2km = [
                other_sites[index][0]
                for index, distance in enumerate(distances_km)
                if distance <= 2.0
            ]
            technology_counts = {
                tech: sum(tech in self.site_technologies.get(neighbor_id, set()) for neighbor_id in neighbor_sites_2km)
                for tech in ('2G', '3G', '4G')
            }
            neighbor_heights = [
                self.site_antenna_heights[neighbor_id]
                for neighbor_id in neighbor_sites_2km
                if self.site_antenna_heights.get(neighbor_id) is not None
            ]
            
            # Average distance to neighbors within 5km
            neighbors_5km = distances_km[distances_km <= 5.0]
            avg_neighbor_distance_km = float(np.mean(neighbors_5km)) if len(neighbors_5km) > 0 else None
            
            # Nearest neighbor distance
            nearest_neighbor_distance_km = float(np.min(distances_km))
            
            # Density score (neighbors per km²)
            # Use 5km radius = π * 5² = 78.54 km²
            density_score = neighbor_count_5km / 78.54
            
            # Isolation score (inverse of nearest neighbor distance)
            # Higher score = less isolated
            isolation_score = 1.0 / nearest_neighbor_distance_km if nearest_neighbor_distance_km > 0 else 0.0
            
            # Cluster centrality (distance from cluster centroid)
            cluster_centrality = self._compute_cluster_centrality(site_id, site_lat, site_lon, cluster_id)
            
            return SpatialFeatureResult(
                site_id=site_id,
                neighbor_count_1km=neighbor_count_1km,
                neighbor_count_2km=neighbor_count_2km,
                neighbor_count_5km=neighbor_count_5km,
                neighbor_count_3km=neighbor_count_3km,
                n_2g_sites_2km=technology_counts['2G'],
                n_3g_sites_2km=technology_counts['3G'],
                n_4g_sites_2km=technology_counts['4G'],
                neighbor_avg_antenna_height_m=float(np.mean(neighbor_heights)) if neighbor_heights else 0.0,
                avg_neighbor_distance_km=avg_neighbor_distance_km,
                nearest_neighbor_distance_km=nearest_neighbor_distance_km,
                density_score=density_score,
                isolation_score=isolation_score,
                cluster_centrality=cluster_centrality,
                success=True
            )
            
        except Exception as e:
            logger.error(f"Failed to extract spatial features for site {site_id}: {e}")
            return SpatialFeatureResult(
                site_id=site_id,
                neighbor_count_1km=None,
                neighbor_count_2km=None,
                neighbor_count_5km=None,
                neighbor_count_3km=None,
                n_2g_sites_2km=None,
                n_3g_sites_2km=None,
                n_4g_sites_2km=None,
                neighbor_avg_antenna_height_m=None,
                avg_neighbor_distance_km=None,
                nearest_neighbor_distance_km=None,
                density_score=None,
                isolation_score=None,
                cluster_centrality=None,
                success=False,
                error_message=str(e)
            )
    
    def _haversine_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Calculate great-circle distance between two points using Haversine formula.
        
        Args:
            lat1, lon1: First point coordinates (degrees)
            lat2, lon2: Second point coordinates (degrees)
            
        Returns:
            Distance in kilometers
        """
        R = 6371.0  # Earth radius in kilometers
        
        lat1_rad = math.radians(lat1)
        lon1_rad = math.radians(lon1)
        lat2_rad = math.radians(lat2)
        lon2_rad = math.radians(lon2)
        
        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad
        
        a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        
        return R * c
    
    def _compute_cluster_centrality(
        self,
        site_id: str,
        site_lat: float,
        site_lon: float,
        cluster_id: Optional[int]
    ) -> Optional[float]:
        """
        Compute distance from site to its cluster centroid.
        
        Args:
            site_id: Site identifier
            site_lat: Site latitude
            site_lon: Site longitude
            cluster_id: Cluster identifier
            
        Returns:
            Distance to cluster centroid in km, or None if no cluster
        """
        if cluster_id is None or cluster_id == -1:
            return None
        
        # Find all sites in same cluster
        cluster_sites = [
            (lat, lon) 
            for sid, (lat, lon) in self.site_coords.items()
            if self.site_clusters.get(sid) == cluster_id
        ]
        
        if len(cluster_sites) <= 1:
            return 0.0  # Single site cluster or self only
        
        # Calculate cluster centroid
        cluster_lats = [lat for lat, lon in cluster_sites]
        cluster_lons = [lon for lat, lon in cluster_sites]
        
        centroid_lat = float(np.mean(cluster_lats))
        centroid_lon = float(np.mean(cluster_lons))
        
        # Distance from site to centroid
        distance_km = self._haversine_distance(site_lat, site_lon, centroid_lat, centroid_lon)
        
        return distance_km
    
    def extract_batch(self, site_ids: Optional[List[str]] = None) -> List[SpatialFeatureResult]:
        """
        Extract spatial features for multiple sites.
        
        Args:
            site_ids: List of site IDs to process (None = process all sites)
            
        Returns:
            List of SpatialFeatureResult objects
        """
        if site_ids is None:
            site_ids = list(self.site_coords.keys())
        
        results = []
        total = len(site_ids)
        
        logger.info(f"Extracting spatial features for {total} sites...")
        
        for idx, site_id in enumerate(site_ids, 1):
            result = self.extract_features(site_id)
            results.append(result)
            
            if idx % 10 == 0 or idx == total:
                logger.info(f"Processed {idx}/{total} sites ({idx/total*100:.1f}%)")
        
        # Summary statistics
        successful = sum(1 for r in results if r.success)
        failed = total - successful
        
        logger.info(f"Spatial feature extraction complete: {successful} succeeded, {failed} failed")
        
        return results
    
    def to_dict(self, result: SpatialFeatureResult) -> Dict:
        """
        Convert SpatialFeatureResult to dictionary for database storage.
        
        Args:
            result: SpatialFeatureResult object
            
        Returns:
            Dictionary with feature values (None if extraction failed)
        """
        if not result.success:
            return {
                'dist_nearest_site_m': 0,
                'n_sites_1km': 0,
                'n_sites_2km': 0,
                'n_sites_3km': 0,
                'n_2g_sites_2km': 0,
                'n_3g_sites_2km': 0,
                'n_4g_sites_2km': 0,
                'neighbor_avg_antenna_height_m': 0,
            }
        
        return {
            # Coincident coordinates are valid after source aggregation. Keep
            # their true zero distance; never serialize a required DB field as
            # None merely because the numeric value is falsy.
            'dist_nearest_site_m': (result.nearest_neighbor_distance_km or 0) * 1000,
            'n_sites_1km': result.neighbor_count_1km,
            'n_sites_2km': result.neighbor_count_2km,
            'n_sites_3km': result.neighbor_count_3km,
            'n_2g_sites_2km': result.n_2g_sites_2km,
            'n_3g_sites_2km': result.n_3g_sites_2km,
            'n_4g_sites_2km': result.n_4g_sites_2km,
            'neighbor_avg_antenna_height_m': result.neighbor_avg_antenna_height_m,
        }
