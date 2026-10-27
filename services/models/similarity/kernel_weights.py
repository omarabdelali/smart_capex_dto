"""
Kernel Weighting for Case-Based Reasoning

Implements Gaussian kernel weighting for similar cases in prediction.
Weights nearby cases more heavily than distant cases.

Gaussian Kernel: w(d) = exp(-d²/2h²)
where:
- d: Gower distance to case
- h: bandwidth parameter (adaptive)

Bandwidth estimation: h = median(pairwise_distances) / 2

Reference: Spec Section 9.3 (Kernel Weighting)
"""

import numpy as np
from typing import List, Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class KernelWeights:
    """Compute kernel weights for similar cases."""
    
    def __init__(
        self,
        kernel_type: str = 'gaussian',
        bandwidth: Optional[float] = None,
        bandwidth_method: str = 'median'
    ):
        """
        Initialize kernel weights computer.
        
        Args:
            kernel_type: Type of kernel ('gaussian', 'epanechnikov', 'uniform')
            bandwidth: Fixed bandwidth parameter (None for adaptive)
            bandwidth_method: Method for adaptive bandwidth ('median', 'scott', 'silverman')
        """
        self.kernel_type = kernel_type
        self.bandwidth = bandwidth
        self.bandwidth_method = bandwidth_method
        
    def compute_weights(
        self,
        distances: List[float],
        normalize: bool = True
    ) -> np.ndarray:
        """
        Compute kernel weights from distances.
        
        Args:
            distances: List of Gower distances to cases
            normalize: Whether to normalize weights to sum to 1
            
        Returns:
            Array of weights (same length as distances)
        """
        distances = np.array(distances)
        
        # Estimate bandwidth if not provided
        if self.bandwidth is None:
            h = self._estimate_bandwidth(distances)
        else:
            h = self.bandwidth
        
        # Compute kernel weights
        if self.kernel_type == 'gaussian':
            weights = self._gaussian_kernel(distances, h)
        elif self.kernel_type == 'epanechnikov':
            weights = self._epanechnikov_kernel(distances, h)
        elif self.kernel_type == 'uniform':
            weights = self._uniform_kernel(distances, h)
        else:
            raise ValueError(f"Unknown kernel type: {self.kernel_type}")
        
        # Normalize if requested
        if normalize:
            if self.kernel_type == 'gaussian' and len(distances) and h > 0:
                log_weights = -0.5 * (distances / h) ** 2
                weights = np.exp(log_weights - np.max(log_weights))
            total = np.sum(weights)
            if total > 0:
                weights = weights / total
            else:
                # All weights zero → equal weights
                weights = np.ones_like(weights) / len(weights)
        
        return weights
    
    def _gaussian_kernel(self, distances: np.ndarray, h: float) -> np.ndarray:
        """
        Gaussian (RBF) kernel: K(d) = exp(-d²/2h²)
        
        Args:
            distances: Array of distances
            h: Bandwidth parameter
            
        Returns:
            Array of kernel values
        """
        if h == 0:
            logger.warning("Bandwidth is zero, using uniform weights")
            return np.ones_like(distances)
        
        return np.exp(-0.5 * (distances / h) ** 2)
    
    def _epanechnikov_kernel(self, distances: np.ndarray, h: float) -> np.ndarray:
        """
        Epanechnikov kernel: K(d) = max(0, 1 - (d/h)²) * 0.75
        
        Args:
            distances: Array of distances
            h: Bandwidth parameter
            
        Returns:
            Array of kernel values
        """
        if h == 0:
            return np.ones_like(distances)
        
        u = distances / h
        weights = np.maximum(0, 1 - u ** 2) * 0.75
        return weights
    
    def _uniform_kernel(self, distances: np.ndarray, h: float) -> np.ndarray:
        """
        Uniform kernel: K(d) = 1 if d ≤ h, else 0
        
        Args:
            distances: Array of distances
            h: Bandwidth parameter
            
        Returns:
            Array of kernel values
        """
        if h == 0:
            return np.ones_like(distances)
        
        weights = (distances <= h).astype(float)
        return weights
    
    def _estimate_bandwidth(self, distances: np.ndarray) -> float:
        """
        Estimate bandwidth parameter adaptively.
        
        Methods:
        - 'median': h = median(distances) / 2
        - 'scott': h = n^(-1/5) * std(distances)
        - 'silverman': h = (n * 3/4)^(-1/5) * std(distances)
        
        Args:
            distances: Array of distances
            
        Returns:
            Estimated bandwidth
        """
        if len(distances) == 0:
            return 1.0
        
        if self.bandwidth_method == 'median':
            # Use half of median pairwise distance
            from .calibration import policy
            median_dist = np.median(distances)
            h = median_dist * policy()['kernel_width_factor'] if median_dist > 0 else 0.1
            
        elif self.bandwidth_method == 'scott':
            # Scott's rule: h = n^(-1/5) * σ
            n = len(distances)
            std_dist = np.std(distances)
            h = n ** (-0.2) * std_dist if std_dist > 0 else 0.1
            
        elif self.bandwidth_method == 'silverman':
            # Silverman's rule: h = (n * 3/4)^(-1/5) * σ
            n = len(distances)
            std_dist = np.std(distances)
            h = (n * 0.75) ** (-0.2) * std_dist if std_dist > 0 else 0.1
            
        else:
            raise ValueError(f"Unknown bandwidth method: {self.bandwidth_method}")
        
        logger.debug(f"Estimated bandwidth: h={h:.4f} using {self.bandwidth_method} method")
        return max(h, 1e-6)  # Ensure non-zero bandwidth
    
    def weighted_average(
        self,
        values: List[float],
        distances: List[float]
    ) -> Tuple[float, float]:
        """
        Compute weighted average using kernel weights.
        
        Args:
            values: Target values to average
            distances: Distances to each value
            
        Returns:
            Tuple of (weighted_mean, effective_n)
        """
        values = np.array(values)
        weights = self.compute_weights(distances, normalize=True)
        
        # Weighted mean
        weighted_mean = np.sum(weights * values)
        
        # Effective sample size (1 / sum(w_i²))
        effective_n = 1.0 / np.sum(weights ** 2) if np.sum(weights ** 2) > 0 else 1.0
        
        return float(weighted_mean), float(effective_n)
    
    def weighted_percentile(
        self,
        values: List[float],
        distances: List[float],
        percentile: float = 50.0
    ) -> float:
        """
        Compute weighted percentile.
        
        Args:
            values: Target values
            distances: Distances to each value
            percentile: Percentile to compute (0-100)
            
        Returns:
            Weighted percentile value
        """
        values = np.array(values)
        weights = self.compute_weights(distances, normalize=True)
        
        # Sort values and weights together
        sorted_indices = np.argsort(values)
        sorted_values = values[sorted_indices]
        sorted_weights = weights[sorted_indices]
        
        # Cumulative weights
        cumsum_weights = np.cumsum(sorted_weights)
        
        # Find percentile
        target = percentile / 100.0
        idx = np.searchsorted(cumsum_weights, target)
        
        if idx >= len(sorted_values):
            return sorted_values[-1]
        
        return float(sorted_values[idx])
    
    def get_effective_bandwidth(self, distances: List[float]) -> float:
        """
        Get the bandwidth that would be used for given distances.
        
        Args:
            distances: Array of distances
            
        Returns:
            Bandwidth value
        """
        if self.bandwidth is not None:
            return self.bandwidth
        else:
            return self._estimate_bandwidth(np.array(distances))
    
    def get_statistics(self, distances: List[float]) -> Dict:
        """
        Get statistics about kernel weighting.
        
        Args:
            distances: Array of distances
            
        Returns:
            Dictionary with statistics
        """
        distances = np.array(distances)
        weights = self.compute_weights(distances, normalize=True)
        
        return {
            'kernel_type': self.kernel_type,
            'bandwidth': self.get_effective_bandwidth(distances),
            'bandwidth_method': self.bandwidth_method,
            'n_cases': len(distances),
            'min_distance': float(np.min(distances)) if len(distances) > 0 else 0.0,
            'max_distance': float(np.max(distances)) if len(distances) > 0 else 0.0,
            'mean_distance': float(np.mean(distances)) if len(distances) > 0 else 0.0,
            'effective_n': 1.0 / np.sum(weights ** 2) if np.sum(weights ** 2) > 0 else 1.0,
            'max_weight': float(np.max(weights)) if len(weights) > 0 else 0.0,
            'min_weight': float(np.min(weights)) if len(weights) > 0 else 0.0
        }
