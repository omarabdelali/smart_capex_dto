"""
Gower Distance - Mixed-Type Similarity Metric

Implements Gower distance for computing similarity between sites with mixed numeric/categorical features.
Gower distance handles different feature types appropriately:
- Numeric: Normalized Manhattan distance
- Categorical: 0 if match, 1 if no match

Formula: d_gower = Σ(w_i * δ_i) / Σ(w_i)
where:
- w_i: feature weight (group-specific)
- δ_i: feature-specific distance (0-1)

Feature group weights (Spec Section 8):
- Configuration: 0.28
- Pre-launch: 0.27
- Spatial: 0.20
- ANP: 0.15
- Cluster: 0.06
- Clutter: 0.04

Reference: Spec Section 8 (Similarity Metric)
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class GowerDistance:
    """Compute Gower distance between feature vectors with mixed types."""
    
    # Feature group weights from Spec Section 8
    DEFAULT_WEIGHTS = {
        'configuration': 0.28,
        'prelaunch': 0.27,
        'spatial': 0.20,
        'anp': 0.15,
        'cluster': 0.06,
        'clutter': 0.04
    }
    
    # Feature type mappings
    NUMERIC_FEATURES = [
        # Configuration (10 features)
        'sector_count_after', 'cells_per_sector_after', 'antenna_height_m',
        'total_bw_after_mhz', 'total_capacity_after_mbps',
        
        # Geometric (4 features)
        'z_antenna_m', 'terrain_slope_deg', 'terrain_roughness_m', 'terrain_aspect_deg',
        
        # Clutter (4 features)
        'clutter_entropy_2km', 'pct_building_area_1km', 'avg_building_height_m',
        
        # Spatial (8 features)
        'dist_nearest_site_m', 'n_sites_1km', 'n_sites_2km', 'n_sites_3km',
        'n_2g_sites_2km', 'n_3g_sites_2km', 'n_4g_sites_2km', 'neighbor_avg_antenna_height_m',
        
        # ANP (15 features - all numeric)
        'n_tier1', 'n_tier2', 't1_to_t2_ratio', 't1_nearest_m', 't2_nearest_m',
        'angular_uniformity', 'max_empty_arc_deg', 'n_empty_bins',
        'dominant_sector_deg', 'dominant_sector_count', 'edge_score',
        'bearing_stddev_deg', 'avg_neighbor_dist_t1_m', 'avg_neighbor_dist_t2_m',
        'coverage_asymmetry',
        
        # Pre-launch (9 features - all numeric)
        'avg_traffic_dl_gb', 'avg_traffic_ul_gb', 'avg_users', 'avg_prb_util_pct',
        'peak_hour_traffic_gb', 'peak_hour_users', 'avg_cqi', 'avg_rsrp_dbm',
        'congestion_hours_per_day',
        
        # Cluster (6 features)
        'cluster_size', 'cluster_density_sites_per_km2', 'cluster_avg_traffic_gb',
        'cluster_avg_users', 'dist_to_cluster_centroid_m'
    ]
    
    CATEGORICAL_FEATURES = [
        # Configuration
        'event_type', 'tech_added', 'bands_added',
        'tech_before_2g', 'tech_before_3g', 'tech_before_4g',
        'tech_after_2g', 'tech_after_3g', 'tech_after_4g',
        
        # Clutter
        'dominant_clutter',
        
        # Cluster
        'cluster_id'
    ]
    
    def __init__(
        self,
        feature_ranges: Optional[Dict[str, Tuple[float, float]]] = None,
        group_weights: Optional[Dict[str, float]] = None
    ):
        """
        Initialize Gower distance computer.
        
        Args:
            feature_ranges: Dictionary mapping feature names to (min, max) tuples for normalization
            group_weights: Custom feature group weights (defaults to spec weights)
        """
        self.feature_ranges = feature_ranges or {}
        self.group_weights = group_weights or self.DEFAULT_WEIGHTS.copy()
        
    def compute_distance(
        self,
        x1: Dict[str, any],
        x2: Dict[str, any],
        feature_weights: Optional[Dict[str, float]] = None
    ) -> float:
        """
        Compute Gower distance between two feature vectors.
        
        Args:
            x1: First feature vector (dict)
            x2: Second feature vector (dict)
            feature_weights: Optional per-feature weights (overrides group weights)
            
        Returns:
            Gower distance in [0, 1], where 0 = identical, 1 = maximally different
        """
        total_distance = 0.0
        total_weight = 0.0
        
        # Get all feature names from both vectors
        all_features = set(x1.keys()).union(set(x2.keys()))
        
        for feature in all_features:
            # Skip if feature missing in either vector
            if feature not in x1 or feature not in x2:
                continue
            
            # Get feature weight
            weight = self._get_feature_weight(feature, feature_weights)
            
            # Compute feature-specific distance
            delta = self._compute_feature_distance(feature, x1[feature], x2[feature])
            
            total_distance += weight * delta
            total_weight += weight
        
        # Normalize by total weight
        if total_weight == 0:
            return 1.0  # Maximum distance if no valid features
        
        return total_distance / total_weight
    
    def compute_distance_matrix(
        self,
        features: List[Dict[str, any]],
        query: Optional[Dict[str, any]] = None
    ) -> np.ndarray:
        """
        Compute pairwise Gower distance matrix.
        
        Args:
            features: List of feature vectors
            query: Optional query vector (compute distances to all features)
            
        Returns:
            Distance matrix (n x n) or distance vector (n,) if query provided
        """
        n = len(features)
        
        if query is not None:
            # Compute distances from query to all features
            distances = np.zeros(n)
            for i in range(n):
                distances[i] = self.compute_distance(query, features[i])
            return distances
        else:
            # Compute full pairwise distance matrix
            distances = np.zeros((n, n))
            for i in range(n):
                for j in range(i + 1, n):
                    dist = self.compute_distance(features[i], features[j])
                    distances[i, j] = dist
                    distances[j, i] = dist
            return distances
    
    def _compute_feature_distance(self, feature: str, val1: any, val2: any) -> float:
        """
        Compute distance for a single feature.
        
        Args:
            feature: Feature name
            val1: First value
            val2: Second value
            
        Returns:
            Distance in [0, 1]
        """
        # Handle missing values
        if val1 is None or val2 is None:
            return 1.0
        
        # Categorical features
        if feature in self.CATEGORICAL_FEATURES or isinstance(val1, str):
            return 0.0 if val1 == val2 else 1.0
        
        # Numeric features
        if feature in self.NUMERIC_FEATURES or isinstance(val1, (int, float)):
            # Get range for normalization
            if feature in self.feature_ranges:
                min_val, max_val = self.feature_ranges[feature]
                range_val = max_val - min_val
                
                if range_val == 0:
                    return 0.0  # No variation in this feature
                
                # Normalized Manhattan distance
                return abs(val1 - val2) / range_val
            else:
                # If range not provided, use raw difference (not ideal)
                logger.warning(f"No range provided for feature {feature}, using raw difference")
                return min(abs(val1 - val2), 1.0)
        
        # Unknown feature type - treat as categorical
        return 0.0 if val1 == val2 else 1.0
    
    def _get_feature_weight(
        self,
        feature: str,
        custom_weights: Optional[Dict[str, float]] = None
    ) -> float:
        """
        Get weight for a feature based on its group.
        
        Args:
            feature: Feature name
            custom_weights: Optional custom per-feature weights
            
        Returns:
            Feature weight
        """
        # Use custom weight if provided
        if custom_weights and feature in custom_weights:
            return custom_weights[feature]
        
        # Map feature to group
        group = self._get_feature_group(feature)
        
        if group in self.group_weights:
            # Divide group weight by number of features in group
            n_features_in_group = len([f for f in self.NUMERIC_FEATURES + self.CATEGORICAL_FEATURES
                                       if self._get_feature_group(f) == group])
            if n_features_in_group > 0:
                return self.group_weights[group] / n_features_in_group
        
        # Default weight
        return 1.0
    
    def _get_feature_group(self, feature: str) -> str:
        """Map feature name to its group."""
        # Configuration features
        if any(x in feature for x in ['event_type', 'tech_', 'band', 'sector', 'cells_per_sector',
                                       'antenna_height', 'bw_', 'capacity_']):
            return 'configuration'
        
        # Pre-launch features
        if any(x in feature for x in ['traffic', 'users', 'prb', 'cqi', 'rsrp', 'congestion']):
            return 'prelaunch'
        
        # ANP features
        if any(x in feature for x in ['tier', 'angular', 'bearing', 'edge_score', 'empty',
                                       'dominant_sector', 'coverage_asymmetry', 'neighbor_dist']):
            return 'anp'
        
        # Spatial features
        if any(x in feature for x in ['dist_', 'n_sites', 'n_2g', 'n_3g', 'n_4g', 'neighbor_avg']):
            return 'spatial'
        
        # Cluster features
        if 'cluster' in feature:
            return 'cluster'
        
        # Clutter features
        if any(x in feature for x in ['clutter', 'building', 'z_antenna', 'terrain']):
            return 'clutter'
        
        # Default
        return 'other'
    
    def fit_ranges(self, features: List[Dict[str, any]]):
        """
        Compute feature ranges from training data for normalization.
        
        Args:
            features: List of feature vectors
        """
        logger.info("Computing feature ranges from training data...")
        
        # Collect values for each numeric feature
        feature_values = {f: [] for f in self.NUMERIC_FEATURES}
        
        for feature_vec in features:
            for feature in self.NUMERIC_FEATURES:
                if feature in feature_vec and feature_vec[feature] is not None:
                    feature_values[feature].append(feature_vec[feature])
        
        # Compute min/max for each feature
        self.feature_ranges = {}
        for feature, values in feature_values.items():
            if values:
                self.feature_ranges[feature] = (min(values), max(values))
                logger.debug(f"Feature {feature}: range [{min(values):.2f}, {max(values):.2f}]")
        
        logger.info(f"Computed ranges for {len(self.feature_ranges)} features")
    
    def find_k_nearest(
        self,
        query: Dict[str, any],
        candidates: List[Dict[str, any]],
        k: int = 10,
        return_distances: bool = False
    ) -> List[int] | Tuple[List[int], List[float]]:
        """
        Find k nearest neighbors using Gower distance.
        
        Args:
            query: Query feature vector
            candidates: List of candidate feature vectors
            k: Number of neighbors to return
            return_distances: Whether to return distances as well
            
        Returns:
            List of indices of k nearest neighbors, optionally with distances
        """
        # Compute distances
        distances = self.compute_distance_matrix(candidates, query)
        
        # Get k smallest distances
        k = min(k, len(candidates))
        nearest_indices = np.argsort(distances)[:k]
        
        if return_distances:
            nearest_distances = distances[nearest_indices]
            return nearest_indices.tolist(), nearest_distances.tolist()
        else:
            return nearest_indices.tolist()
    
    def get_statistics(self) -> Dict:
        """Get statistics about configured distance metric."""
        return {
            'n_numeric_features': len(self.NUMERIC_FEATURES),
            'n_categorical_features': len(self.CATEGORICAL_FEATURES),
            'n_feature_ranges': len(self.feature_ranges),
            'group_weights': self.group_weights
        }