"""
Similarity Engine Module

Components:
- gower_distance.py: Gower distance for mixed numeric/categorical features
- hierarchical_filter.py: Business logic filters (event_type, tech, bands)
- kernel_weights.py: Gaussian kernel weighting
"""

from .engine import rank_similar_cases
from .feature_vector import build_site_similarity_vector

__all__ = ['rank_similar_cases', 'build_site_similarity_vector']
