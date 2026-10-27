"""
Angular Neighborhood Profile (ANP) - KEY INNOVATION

Implements the Angular Neighborhood Profile feature set for edge vs infill classification.
ANP analyzes the angular distribution of neighboring sites in 360° around target site.

15 ANP Features (Spec Section 7.4):
- n_tier1, n_tier2: Neighbor counts by distance tier
- t1_to_t2_ratio: Ratio of tier1 to tier2 neighbors
- t1_nearest_m, t2_nearest_m: Nearest neighbor distances
- angular_uniformity: Entropy of angular distribution
- max_empty_arc_deg: Largest gap in coverage
- n_empty_bins: Number of 30° bins with no neighbors
- dominant_sector_deg: Most concentrated 30° sector
- dominant_sector_count: Neighbors in dominant sector
- edge_score: Edge vs infill classification (0-1, 1=edge)
- bearing_stddev_deg: Circular standard deviation of bearings
- avg_neighbor_dist_t1_m, avg_neighbor_dist_t2_m: Mean distances
- coverage_asymmetry: Difference between max and min arc lengths

Reference: Spec Section 7.4 (Angular Neighborhood Profile)

This is the CORE DIFFERENTIATOR of Smart CAPEX Phase 1.
"""

import numpy as np
from typing import Dict, List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class ANPComputer:
    """Compute Angular Neighborhood Profile features for a site."""
    
    # Distance tiers (meters)
    TIER1_MAX = 2000  # ≤ 2km
    TIER2_MIN = 2000  # > 2km
    TIER2_MAX = 5000  # ≤ 5km
    
    # Angular binning
    N_BINS = 12  # 12 bins of 30° each
    BIN_SIZE_DEG = 360.0 / N_BINS  # 30°
    
    def __init__(self, use_sector_alignment: bool = True, tier_scheme="standard"):
        """
        Initialize ANP computer.
        
        Args:
            use_sector_alignment: Align bins to 0°, 120°, 240° (standard tri-sector)
        """
        self.tier_scheme = tier_scheme
        self.use_sector_alignment = use_sector_alignment
        
    def compute_anp(
        self,
        target_lat: float,
        target_lon: float,
        neighbor_coords: List[Tuple[float, float]],
        neighbor_distances: Optional[List[float]] = None
    ) -> Dict[str, float]:
        """
        Compute full ANP feature set for a target site.
        
        Args:
            target_lat: Target site latitude (WGS84)
            target_lon: Target site longitude (WGS84)
            neighbor_coords: List of (lat, lon) tuples for neighboring sites
            neighbor_distances: Optional pre-computed distances in meters
            
        Returns:
            Dictionary with 15 ANP features
        """
        if not neighbor_coords:
            return self._empty_anp()
        
        # Compute bearings and distances if not provided
        from services.utils.geo_utils import compute_bearing, haversine
        
        neighbors = []
        for i, (lat, lon) in enumerate(neighbor_coords):
            bearing = compute_bearing(target_lat, target_lon, lat, lon)
            distance = neighbor_distances[i] if neighbor_distances else haversine(
                target_lat, target_lon, lat, lon
            )
            neighbors.append({
                'bearing': bearing,
                'distance': distance,
                'lat': lat,
                'lon': lon
            })
        
        # Filter by distance tiers
        from .neighborhood import tier
        tier1 = [n for n in neighbors if tier(n['distance'],self.tier_scheme)=='tier1']
        tier2 = [n for n in neighbors if tier(n['distance'],self.tier_scheme)=='tier2']
        
        # Extract bearings for each tier
        t1_bearings = [n['bearing'] for n in tier1]
        t2_bearings = [n['bearing'] for n in tier2]
        all_bearings = t1_bearings + t2_bearings
        
        # Compute ANP features
        anp_features = {}
        
        # 1. Neighbor counts
        anp_features['n_tier1'] = len(tier1)
        anp_features['n_tier2'] = len(tier2)
        anp_features['t1_to_t2_ratio'] = len(tier1) / len(tier2) if len(tier2) > 0 else (
            len(tier1) if len(tier1) > 0 else 0.0
        )
        
        # 2. Nearest neighbor distances
        anp_features['t1_nearest_m'] = min([n['distance'] for n in tier1]) if tier1 else 9999.0
        anp_features['t2_nearest_m'] = min([n['distance'] for n in tier2]) if tier2 else 9999.0
        
        # 3. Average distances
        anp_features['avg_neighbor_dist_t1_m'] = np.mean([n['distance'] for n in tier1]) if tier1 else 0.0
        anp_features['avg_neighbor_dist_t2_m'] = np.mean([n['distance'] for n in tier2]) if tier2 else 0.0
        
        # 4. Angular distribution analysis
        if all_bearings:
            angular_features = self._compute_angular_features(all_bearings)
            anp_features.update(angular_features)
        else:
            anp_features.update({
                'angular_uniformity': 0.0,
                'max_empty_arc_deg': 360.0,
                'n_empty_bins': self.N_BINS,
                'dominant_sector_deg': 0.0,
                'dominant_sector_count': 0,
                'bearing_stddev_deg': 0.0,
                'coverage_asymmetry': 1.0
            })
        
        # 5. Edge score (composite metric: 1 = edge, 0 = infill)
        anp_features['edge_score'] = self._compute_edge_score(anp_features)
        
        return anp_features
    
    def _compute_angular_features(self, bearings: List[float]) -> Dict[str, float]:
        """
        Compute angular distribution features from bearings.
        
        Features:
        - angular_uniformity: Entropy of angular distribution (0 = concentrated, high = uniform)
        - max_empty_arc_deg: Largest angular gap
        - n_empty_bins: Number of 30° bins with zero neighbors
        - dominant_sector_deg: Center of most populated sector
        - dominant_sector_count: Number of neighbors in dominant sector
        - bearing_stddev_deg: Circular standard deviation
        - coverage_asymmetry: Imbalance metric
        """
        bearings = np.array(bearings)
        
        # Create angular bins (0-30, 30-60, ..., 330-360)
        bins = np.arange(0, 360 + self.BIN_SIZE_DEG, self.BIN_SIZE_DEG)
        bin_counts, _ = np.histogram(bearings, bins=bins)
        
        # Angular uniformity (normalized entropy)
        # H = -Σ(p_i * log(p_i)) where p_i = count_i / total
        probabilities = bin_counts / len(bearings)
        probabilities = probabilities[probabilities > 0]  # Remove zeros for log
        entropy = -np.sum(probabilities * np.log(probabilities))
        max_entropy = np.log(self.N_BINS)  # Maximum entropy for uniform distribution
        angular_uniformity = entropy / max_entropy if max_entropy > 0 else 0.0
        
        # Empty bins
        n_empty_bins = np.sum(bin_counts == 0)
        
        # Dominant sector
        dominant_bin_idx = np.argmax(bin_counts)
        dominant_sector_deg = dominant_bin_idx * self.BIN_SIZE_DEG + self.BIN_SIZE_DEG / 2
        dominant_sector_count = int(bin_counts[dominant_bin_idx])
        
        # Maximum empty arc (largest contiguous gap)
        max_empty_arc_deg = self._compute_max_empty_arc(bearings)
        
        # Circular statistics
        from services.utils.geo_utils import circular_std
        bearing_stddev_deg = circular_std(bearings)
        
        # Coverage asymmetry (difference between longest and shortest arcs)
        coverage_asymmetry = self._compute_coverage_asymmetry(bearings)
        
        return {
            'angular_uniformity': float(angular_uniformity),
            'max_empty_arc_deg': float(max_empty_arc_deg),
            'n_empty_bins': int(n_empty_bins),
            'dominant_sector_deg': float(dominant_sector_deg),
            'dominant_sector_count': int(dominant_sector_count),
            'bearing_stddev_deg': float(bearing_stddev_deg),
            'coverage_asymmetry': float(coverage_asymmetry)
        }
    
    def _compute_max_empty_arc(self, bearings: List[float]) -> float:
        """
        Compute the largest contiguous angular gap.
        
        Edge sites have large gaps (e.g., 180°+ facing away from network).
        Infill sites have small gaps (surrounded by neighbors).
        """
        if len(bearings) == 0:
            return 360.0
        
        # Sort bearings
        sorted_bearings = np.sort(bearings)
        
        # Compute gaps between consecutive bearings
        gaps = np.diff(sorted_bearings)
        
        # Don't forget the wrap-around gap (360° - last + first)
        wraparound_gap = 360.0 - sorted_bearings[-1] + sorted_bearings[0]
        
        all_gaps = np.append(gaps, wraparound_gap)
        
        return float(np.max(all_gaps))
    
    def _compute_coverage_asymmetry(self, bearings: List[float]) -> float:
        """
        Compute coverage asymmetry.
        
        Measures the imbalance in angular coverage.
        High asymmetry → edge site (neighbors on one side)
        Low asymmetry → infill site (surrounded evenly)
        """
        if len(bearings) < 2:
            return 1.0
        
        sorted_bearings = np.sort(bearings)
        gaps = np.diff(sorted_bearings)
        wraparound_gap = 360.0 - sorted_bearings[-1] + sorted_bearings[0]
        all_gaps = np.append(gaps, wraparound_gap)
        
        # Asymmetry = (max_gap - min_gap) / 360
        asymmetry = (np.max(all_gaps) - np.min(all_gaps)) / 360.0
        
        return float(asymmetry)
    
    def _compute_edge_score(self, anp_features: Dict[str, float]) -> float:
        """
        Compute edge score (0-1, where 1 = edge, 0 = infill).
        
        Edge indicators:
        - Large max_empty_arc_deg (e.g., >180°)
        - High n_empty_bins (e.g., >6 out of 12)
        - Low angular_uniformity (concentrated on one side)
        - High coverage_asymmetry
        - Low n_tier1 (fewer close neighbors)
        
        Formula (weighted combination):
        edge_score = 0.3 * (max_empty_arc / 180) +
                     0.2 * (n_empty_bins / 12) +
                     0.2 * (1 - angular_uniformity) +
                     0.2 * coverage_asymmetry +
                     0.1 * (1 - min(n_tier1 / 6, 1.0))
        
        Clamped to [0, 1]
        """
        max_arc_score = min(anp_features.get('max_empty_arc_deg', 0) / 180.0, 1.0)
        empty_bins_score = anp_features.get('n_empty_bins', 0) / self.N_BINS
        uniformity_score = 1.0 - anp_features.get('angular_uniformity', 1.0)
        asymmetry_score = anp_features.get('coverage_asymmetry', 0)
        neighbor_score = 1.0 - min(anp_features.get('n_tier1', 0) / 6.0, 1.0)
        
        edge_score = (
            0.3 * max_arc_score +
            0.2 * empty_bins_score +
            0.2 * uniformity_score +
            0.2 * asymmetry_score +
            0.1 * neighbor_score
        )
        
        return float(np.clip(edge_score, 0.0, 1.0))
    
    def _empty_anp(self) -> Dict[str, float]:
        """Return empty ANP feature set (no neighbors)."""
        return {
            'n_tier1': 0,
            'n_tier2': 0,
            't1_to_t2_ratio': 0.0,
            't1_nearest_m': 9999.0,
            't2_nearest_m': 9999.0,
            'angular_uniformity': 0.0,
            'max_empty_arc_deg': 360.0,
            'n_empty_bins': self.N_BINS,
            'dominant_sector_deg': 0.0,
            'dominant_sector_count': 0,
            'edge_score': 1.0,  # No neighbors → definitely edge
            'bearing_stddev_deg': 0.0,
            'avg_neighbor_dist_t1_m': 0.0,
            'avg_neighbor_dist_t2_m': 0.0,
            'coverage_asymmetry': 1.0
        }
    
    def classify_site(self, anp_features: Dict[str, float], threshold: float = 0.5) -> str:
        """
        Classify site as EDGE or INFILL based on edge_score.
        
        Args:
            anp_features: Computed ANP features
            threshold: Edge score threshold (default: 0.5)
            
        Returns:
            "EDGE" or "INFILL"
        """
        edge_score = anp_features.get('edge_score', 0.5)
        return "EDGE" if edge_score >= threshold else "INFILL"
    
    def visualize_angular_distribution(
        self,
        bearings: List[float],
        title: str = "Angular Neighborhood Profile"
    ) -> Optional[object]:
        """
        Create polar plot visualization of angular distribution.
        
        Args:
            bearings: List of neighbor bearings (0-360°)
            title: Plot title
            
        Returns:
            Matplotlib figure object (if matplotlib available) or None
        """
        try:
            import matplotlib.pyplot as plt
            
            fig = plt.figure(figsize=(8, 8))
            ax = fig.add_subplot(111, projection='polar')
            
            # Convert bearings to radians (matplotlib uses radians, 0=East)
            # Rotate to make 0=North: subtract 90° and convert
            bearings_rad = np.deg2rad(np.array(bearings) - 90)
            
            # Plot as histogram
            bins = np.linspace(0, 2 * np.pi, self.N_BINS + 1)
            ax.hist(bearings_rad, bins=bins, color='skyblue', edgecolor='black', alpha=0.7)
            
            ax.set_theta_zero_location('N')
            ax.set_theta_direction(-1)  # Clockwise
            ax.set_title(title, pad=20)
            
            return fig
            
        except ImportError:
            logger.warning("matplotlib not available for visualization")
            return None
