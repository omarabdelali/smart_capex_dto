"""
Site Clustering Module for Smart CAPEX Phase 2.
Implements spatial clustering with deduplication, polygon generation, and boundary validation.

Key components:
1. SiteDeduplicator: Remove duplicate sites within 50m using spatial clustering
2. DBSCANClustering: Cluster sites using DBSCAN with haversine distance
3. ClusterPolygonBuilder: Generate concave hull polygons using alpha shapes (alpha=0.05)
4. ClusterAnalyzer: Compute 6 cluster features for each site
5. TunisiaBoundsValidator: Validate sites are within Tunisia boundaries

See spec Section 8 for cluster feature definitions.
"""

import numpy as np
import polars as pl
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime
import logging

from sklearn.cluster import DBSCAN
from geopy.distance import geodesic
import alphashape
from shapely.geometry import Point, Polygon, MultiPoint
import geopandas as gpd

logger = logging.getLogger(__name__)


@dataclass
class Site:
    """Minimal site representation for clustering."""
    site_id: str
    site_name: str
    latitude: float
    longitude: float
    traffic_gb: float = 0.0
    users: float = 0.0
    
    @property
    def coords(self) -> Tuple[float, float]:
        """Return (lat, lon) tuple."""
        return (self.latitude, self.longitude)


@dataclass
class ClusterResult:
    """Result of clustering analysis for a single site."""
    site_id: str
    cluster_id: int
    is_cluster_edge: bool
    out_of_bounds: bool
    cluster_size: int
    cluster_density_sites_per_km2: float
    cluster_avg_traffic_gb: float
    cluster_avg_users: float
    dist_to_cluster_centroid_m: float


class SiteDeduplicator:
    """
    Remove duplicate sites using spatial proximity threshold.
    
    Sites within 50m of each other are considered duplicates.
    When duplicates are found, keep the first occurrence in the list.
    """
    
    def __init__(self, threshold_m: float = 50.0):
        """
        Initialize deduplicator.
        
        Args:
            threshold_m: Distance threshold in meters for deduplication (default: 50m)
        """
        self.threshold_m = threshold_m
        logger.info(f"Initialized SiteDeduplicator with threshold={threshold_m}m")
    
    def deduplicate(self, sites: List[Site]) -> List[Site]:
        """
        Remove duplicate sites based on proximity threshold.
        
        Args:
            sites: List of Site objects
            
        Returns:
            List of deduplicated Site objects (first occurrence kept)
        """
        if not sites:
            return []
        
        logger.info(f"Deduplicating {len(sites)} sites with threshold={self.threshold_m}m")
        
        # Build distance matrix using haversine distance
        n = len(sites)
        dist_matrix = np.zeros((n, n))
        
        for i in range(n):
            for j in range(i + 1, n):
                dist = geodesic(sites[i].coords, sites[j].coords).meters
                dist_matrix[i, j] = dist
                dist_matrix[j, i] = dist
        
        # Use DBSCAN to find groups of nearby sites
        clustering = DBSCAN(
            eps=self.threshold_m / 1000.0,  # Convert to km
            min_samples=1,
            metric='precomputed'
        ).fit(dist_matrix / 1000.0)  # Convert matrix to km
        
        # Keep first occurrence from each cluster
        unique_sites = []
        seen_clusters = set()
        
        for i, cluster_id in enumerate(clustering.labels_):
            if cluster_id not in seen_clusters:
                unique_sites.append(sites[i])
                seen_clusters.add(cluster_id)
        
        logger.info(f"Deduplication removed {len(sites) - len(unique_sites)} duplicate sites")
        logger.info(f"Retained {len(unique_sites)} unique sites")
        
        return unique_sites


def haversine_distance_matrix(coords: np.ndarray) -> np.ndarray:
    """
    Compute haversine distance matrix for array of (lat, lon) coordinates.
    
    Args:
        coords: Array of shape (n, 2) with [latitude, longitude]
        
    Returns:
        Distance matrix of shape (n, n) in kilometers
    """
    n = len(coords)
    dist_matrix = np.zeros((n, n))
    
    for i in range(n):
        for j in range(i + 1, n):
            dist_km = geodesic(coords[i], coords[j]).kilometers
            dist_matrix[i, j] = dist_km
            dist_matrix[j, i] = dist_km
    
    return dist_matrix


class DBSCANClustering:
    """
    Spatial clustering using DBSCAN with haversine distance.
    
    DBSCAN parameters:
    - eps: Maximum distance between neighbors (in km)
    - min_samples: Minimum sites to form a dense cluster
    
    Noise points (cluster_id=-1 from DBSCAN) are treated as single-site
    clusters with cluster_id=-1 assigned per site (not shared).
    """
    
    def __init__(self, eps_km: float = 2.0, min_samples: int = 3):
        """
        Initialize DBSCAN clustering.
        
        Args:
            eps_km: Maximum distance between neighbors in km (default: 2.0)
            min_samples: Minimum sites to form dense cluster (default: 3)
        """
        self.eps_km = eps_km
        self.min_samples = min_samples
        logger.info(f"Initialized DBSCANClustering with eps={eps_km}km, min_samples={min_samples}")
    
    def fit(self, sites: List[Site]) -> Dict[str, int]:
        """
        Perform DBSCAN clustering on sites.
        
        Args:
            sites: List of Site objects
            
        Returns:
            Dictionary mapping site_id -> cluster_id
            Noise points get cluster_id=-1 (per site, not shared)
        """
        if not sites:
            return {}
        
        logger.info(f"Clustering {len(sites)} sites with DBSCAN")
        
        # Extract coordinates
        coords = np.array([s.coords for s in sites])
        
        # Compute haversine distance matrix
        dist_matrix = haversine_distance_matrix(coords)
        
        # Run DBSCAN
        clustering = DBSCAN(
            eps=self.eps_km,
            min_samples=self.min_samples,
            metric='precomputed'
        ).fit(dist_matrix)
        
        # Map site_id to cluster_id
        cluster_map = {}
        noise_counter = 0
        
        for site, label in zip(sites, clustering.labels_):
            if label == -1:
                # Noise point: assign unique negative cluster_id per site
                cluster_map[site.site_id] = -1
                noise_counter += 1
            else:
                cluster_map[site.site_id] = int(label)
        
        n_clusters = len(set(clustering.labels_)) - (1 if -1 in clustering.labels_ else 0)
        logger.info(f"Found {n_clusters} clusters and {noise_counter} noise points")
        
        return cluster_map


class ClusterPolygonBuilder:
    """
    Generate concave hull polygons for clusters using alpha shapes.
    
    Alpha shapes create tighter boundaries than convex hull by allowing
    concavities. Fixed alpha=0.05 parameter based on spec requirements.
    
    For single-site clusters, uses a small circular buffer around the site.
    """
    
    def __init__(self, alpha: float = 0.05, buffer_m: float = 100.0):
        """
        Initialize polygon builder.
        
        Args:
            alpha: Alpha parameter for alpha shapes (default: 0.05, fixed per spec)
            buffer_m: Buffer radius for single-site clusters (default: 100m)
        """
        self.alpha = alpha
        self.buffer_m = buffer_m
        logger.info(f"Initialized ClusterPolygonBuilder with alpha={alpha}, buffer={buffer_m}m")
    
    def build_polygons(
        self, 
        sites: List[Site], 
        cluster_map: Dict[str, int]
    ) -> Dict[int, Polygon]:
        """
        Build concave hull polygons for each cluster.
        
        Args:
            sites: List of Site objects
            cluster_map: Dictionary mapping site_id -> cluster_id
            
        Returns:
            Dictionary mapping cluster_id -> Polygon
        """
        logger.info(f"Building cluster polygons with alpha={self.alpha}")
        
        # Group sites by cluster
        cluster_sites: Dict[int, List[Site]] = {}
        for site in sites:
            cid = cluster_map.get(site.site_id, -1)
            if cid not in cluster_sites:
                cluster_sites[cid] = []
            cluster_sites[cid].append(site)
        
        # Build polygon for each cluster
        polygons = {}
        
        for cluster_id, cluster_sites_list in cluster_sites.items():
            if cluster_id == -1:
                # Noise points: each gets small buffer
                for site in cluster_sites_list:
                    point = Point(site.longitude, site.latitude)
                    buffer_deg = self.buffer_m / 111320.0
                    polygons[cluster_id] = point.buffer(buffer_deg)
            elif len(cluster_sites_list) == 1:
                # Single site cluster: use buffer
                site = cluster_sites_list[0]
                point = Point(site.longitude, site.latitude)
                buffer_deg = self.buffer_m / 111320.0
                polygons[cluster_id] = point.buffer(buffer_deg)
            elif len(cluster_sites_list) == 2:
                # Two sites: create simple polygon connecting them with buffer
                points = [Point(s.longitude, s.latitude) for s in cluster_sites_list]
                line = MultiPoint(points).convex_hull
                buffer_deg = self.buffer_m / 111320.0
                polygons[cluster_id] = line.buffer(buffer_deg)
            else:
                # Multiple sites: use alpha shape
                try:
                    points = np.array([(s.longitude, s.latitude) for s in cluster_sites_list])
                    alpha_shape = alphashape.alphashape(points, self.alpha)
                    
                    if isinstance(alpha_shape, Polygon):
                        polygons[cluster_id] = alpha_shape
                    else:
                        # Fallback to convex hull if alpha shape fails
                        logger.warning(f"Alpha shape failed for cluster {cluster_id}, using convex hull")
                        point_list = [(s.longitude, s.latitude) for s in cluster_sites_list]
                        multipoint = MultiPoint(point_list)
                        polygons[cluster_id] = multipoint.convex_hull
                        
                except Exception as e:
                    logger.warning(f"Error creating alpha shape for cluster {cluster_id}: {e}")
                    # Fallback to convex hull
                    point_list = [(s.longitude, s.latitude) for s in cluster_sites_list]
                    multipoint = MultiPoint(point_list)
                    polygons[cluster_id] = multipoint.convex_hull
        
        logger.info(f"Built {len(polygons)} cluster polygons")
        return polygons
    
    def identify_edge_sites(
        self,
        sites: List[Site],
        cluster_map: Dict[str, int],
        polygons: Dict[int, Polygon]
    ) -> Dict[str, bool]:
        """
        Identify which sites are on the edge of their cluster polygon.
        
        A site is on the edge if it's close to the polygon boundary.
        
        Args:
            sites: List of Site objects
            cluster_map: Dictionary mapping site_id -> cluster_id
            polygons: Dictionary mapping cluster_id -> Polygon
            
        Returns:
            Dictionary mapping site_id -> is_edge (bool)
        """
        edge_map = {}
        edge_threshold_deg = 0.001  # ~111m at Tunisia latitude
        
        for site in sites:
            cluster_id = cluster_map.get(site.site_id, -1)
            
            if cluster_id not in polygons:
                edge_map[site.site_id] = True  # Noise points are edges
                continue
            
            polygon = polygons[cluster_id]
            point = Point(site.longitude, site.latitude)
            
            # Check distance to polygon boundary
            dist_to_boundary = point.distance(polygon.boundary)
            is_edge = dist_to_boundary < edge_threshold_deg
            
            edge_map[site.site_id] = is_edge
        
        n_edge = sum(edge_map.values())
        logger.info(f"Identified {n_edge} edge sites out of {len(sites)} total sites")
        
        return edge_map


class ClusterAnalyzer:
    """
    Compute cluster features for each site.
    
    Computes 6 features per spec Section 8:
    1. cluster_id: ID from DBSCAN
    2. cluster_size: Number of sites in cluster
    3. cluster_density_sites_per_km2: Spatial density
    4. cluster_avg_traffic_gb: Average traffic across cluster
    5. cluster_avg_users: Average users across cluster
    6. dist_to_cluster_centroid_m: Distance to cluster center
    """
    
    def analyze(
        self,
        sites: List[Site],
        cluster_map: Dict[str, int],
        polygons: Dict[int, Polygon]
    ) -> Dict[str, Dict[str, float]]:
        """
        Compute cluster features for all sites.
        
        Args:
            sites: List of Site objects
            cluster_map: Dictionary mapping site_id -> cluster_id
            polygons: Dictionary mapping cluster_id -> Polygon
            
        Returns:
            Dictionary mapping site_id -> feature dict
        """
        logger.info(f"Computing cluster features for {len(sites)} sites")
        
        # Group sites by cluster
        cluster_sites: Dict[int, List[Site]] = {}
        for site in sites:
            cid = cluster_map.get(site.site_id, -1)
            if cid not in cluster_sites:
                cluster_sites[cid] = []
            cluster_sites[cid].append(site)
        
        # Compute cluster-level statistics
        cluster_stats = {}
        for cluster_id, csites in cluster_sites.items():
            # Cluster size
            size = len(csites)
            
            # Cluster density (sites per km²)
            if cluster_id in polygons:
                # Convert polygon area from deg² to km²
                # At Tunisia latitude (~35°), 1° ≈ 111km lat, 91km lon
                area_deg2 = polygons[cluster_id].area
                area_km2 = area_deg2 * 111.0 * 91.0
                density = size / area_km2 if area_km2 > 0 else 0
            else:
                density = 0
            
            # Cluster average traffic and users
            avg_traffic = np.mean([s.traffic_gb for s in csites])
            avg_users = np.mean([s.users for s in csites])
            
            # Cluster centroid
            lats = [s.latitude for s in csites]
            lons = [s.longitude for s in csites]
            centroid_lat = np.mean(lats)
            centroid_lon = np.mean(lons)
            
            cluster_stats[cluster_id] = {
                'size': size,
                'density': density,
                'avg_traffic': avg_traffic,
                'avg_users': avg_users,
                'centroid': (centroid_lat, centroid_lon)
            }
        
        # Compute per-site features
        site_features = {}
        for site in sites:
            cluster_id = cluster_map.get(site.site_id, -1)
            stats = cluster_stats.get(cluster_id, {
                'size': 1,
                'density': 0,
                'avg_traffic': 0,
                'avg_users': 0,
                'centroid': (site.latitude, site.longitude)
            })
            
            # Distance to centroid
            dist_to_centroid_m = geodesic(
                (site.latitude, site.longitude),
                stats['centroid']
            ).meters
            
            site_features[site.site_id] = {
                'cluster_size': stats['size'],
                'cluster_density_sites_per_km2': stats['density'],
                'cluster_avg_traffic_gb': stats['avg_traffic'],
                'cluster_avg_users': stats['avg_users'],
                'dist_to_cluster_centroid_m': dist_to_centroid_m
            }
        
        logger.info(f"Computed cluster features for {len(site_features)} sites")
        return site_features


class TunisiaBoundsValidator:
    """
    Validate that sites are within Tunisia geographic boundaries.
    
    Uses a simplified bounding box for Tunisia:
    - Latitude: 30.2°N to 37.5°N
    - Longitude: 7.5°E to 11.6°E
    
    For production, should use actual Tunisia polygon from Natural Earth or OSM.
    """
    
    # Tunisia approximate bounding box
    MIN_LAT = 30.2
    MAX_LAT = 37.5
    MIN_LON = 7.5
    MAX_LON = 11.6
    
    def __init__(self, tunisia_polygon: Optional[Polygon] = None):
        """
        Initialize bounds validator.
        
        Args:
            tunisia_polygon: Optional detailed Tunisia polygon.
                           If None, uses bounding box approximation.
        """
        self.tunisia_polygon = tunisia_polygon
        if tunisia_polygon:
            logger.info("Initialized TunisiaBoundsValidator with detailed polygon")
        else:
            logger.info("Initialized TunisiaBoundsValidator with bounding box")
    
    def validate(self, sites: List[Site]) -> Dict[str, bool]:
        """
        Check if sites are within Tunisia boundaries.
        
        Args:
            sites: List of Site objects
            
        Returns:
            Dictionary mapping site_id -> out_of_bounds (bool)
            True if site is OUTSIDE Tunisia, False if inside
        """
        logger.info(f"Validating {len(sites)} sites against Tunisia boundaries")
        
        out_of_bounds_map = {}
        
        if self.tunisia_polygon:
            # Use detailed polygon
            for site in sites:
                point = Point(site.longitude, site.latitude)
                out_of_bounds = not self.tunisia_polygon.contains(point)
                out_of_bounds_map[site.site_id] = out_of_bounds
        else:
            # Use bounding box
            for site in sites:
                out_of_bounds = not (
                    self.MIN_LAT <= site.latitude <= self.MAX_LAT and
                    self.MIN_LON <= site.longitude <= self.MAX_LON
                )
                out_of_bounds_map[site.site_id] = out_of_bounds
        
        n_out_of_bounds = sum(out_of_bounds_map.values())
        logger.info(f"Found {n_out_of_bounds} sites outside Tunisia boundaries")
        
        return out_of_bounds_map


class SiteClusteringPipeline:
    """
    Complete clustering pipeline orchestrator.
    
    Combines all clustering components into a single workflow:
    1. Deduplicate sites (50m threshold)
    2. Cluster sites with DBSCAN
    3. Build cluster polygons (alpha shapes)
    4. Identify edge sites
    5. Compute cluster features
    6. Validate Tunisia boundaries
    """
    
    def __init__(
        self,
        dedup_threshold_m: float = 50.0,
        dbscan_eps_km: float = 2.0,
        dbscan_min_samples: int = 3,
        alpha: float = 0.05,
        tunisia_polygon: Optional[Polygon] = None
    ):
        """
        Initialize clustering pipeline.
        
        Args:
            dedup_threshold_m: Deduplication distance threshold (default: 50m)
            dbscan_eps_km: DBSCAN eps parameter (default: 2.0km)
            dbscan_min_samples: DBSCAN min_samples parameter (default: 3)
            alpha: Alpha shape parameter (default: 0.05, fixed per spec)
            tunisia_polygon: Optional Tunisia boundary polygon
        """
        self.deduplicator = SiteDeduplicator(dedup_threshold_m)
        self.clustering = DBSCANClustering(dbscan_eps_km, dbscan_min_samples)
        self.polygon_builder = ClusterPolygonBuilder(alpha)
        self.analyzer = ClusterAnalyzer()
        self.bounds_validator = TunisiaBoundsValidator(tunisia_polygon)
        
        logger.info("Initialized SiteClusteringPipeline")
    
    def run(self, sites: List[Site]) -> List[ClusterResult]:
        """
        Run complete clustering pipeline.
        
        Args:
            sites: List of Site objects
            
        Returns:
            List of ClusterResult objects with all features computed
        """
        logger.info(f"Starting clustering pipeline with {len(sites)} sites")
        
        # Step 1: Deduplicate
        unique_sites = self.deduplicator.deduplicate(sites)
        
        # Step 2: Cluster
        cluster_map = self.clustering.fit(unique_sites)
        
        # Step 3: Build polygons
        polygons = self.polygon_builder.build_polygons(unique_sites, cluster_map)
        
        # Step 4: Identify edge sites
        edge_map = self.polygon_builder.identify_edge_sites(unique_sites, cluster_map, polygons)
        
        # Step 5: Compute cluster features
        feature_map = self.analyzer.analyze(unique_sites, cluster_map, polygons)
        
        # Step 6: Validate boundaries
        bounds_map = self.bounds_validator.validate(unique_sites)
        
        # Step 7: Combine results
        results = []
        for site in unique_sites:
            cluster_id = cluster_map.get(site.site_id, -1)
            is_edge = edge_map.get(site.site_id, True)
            out_of_bounds = bounds_map.get(site.site_id, False)
            features = feature_map.get(site.site_id, {})
            
            result = ClusterResult(
                site_id=site.site_id,
                cluster_id=cluster_id,
                is_cluster_edge=is_edge,
                out_of_bounds=out_of_bounds,
                cluster_size=int(features.get('cluster_size', 1)),
                cluster_density_sites_per_km2=float(features.get('cluster_density_sites_per_km2', 0.0)),
                cluster_avg_traffic_gb=float(features.get('cluster_avg_traffic_gb', 0.0)),
                cluster_avg_users=float(features.get('cluster_avg_users', 0.0)),
                dist_to_cluster_centroid_m=float(features.get('dist_to_cluster_centroid_m', 0.0))
            )
            results.append(result)
        
        logger.info(f"Clustering pipeline completed with {len(results)} results")
        return results
    
    def get_polygons(self, sites: List[Site]) -> Dict[int, Polygon]:
        """
        Get cluster polygons for visualization.
        
        Args:
            sites: List of Site objects
            
        Returns:
            Dictionary mapping cluster_id -> Polygon
        """
        unique_sites = self.deduplicator.deduplicate(sites)
        cluster_map = self.clustering.fit(unique_sites)
        polygons = self.polygon_builder.build_polygons(unique_sites, cluster_map)
        return polygons
