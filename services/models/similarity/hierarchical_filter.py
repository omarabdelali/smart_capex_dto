"""
Hierarchical Filtering for Case-Based Reasoning

Implements hierarchical filtering to select relevant historical cases for prediction.
Filters cases based on configuration similarity before computing Gower distance.

Three-level filter (Spec Section 9.2):
1. event_type must match exactly
2. tech_added must match exactly
3. bands_added overlap ≥ 50%

Relaxation logic:
- If pool < 3 after all filters, relax filter 3 (bands)
- If still < 3, relax filter 2 (tech)
- If still < 3, use global model (all cases)

Reference: Spec Section 9.2 (Hierarchical Filtering)
"""

from typing import Dict, List, Set, Optional
import logging

logger = logging.getLogger(__name__)


class HierarchicalFilter:
    """Filter historical cases based on configuration similarity."""
    
    def __init__(
        self,
        min_pool_size: int = 3,
        band_overlap_threshold: float = 0.5
    ):
        """
        Initialize hierarchical filter.
        
        Args:
            min_pool_size: Minimum number of cases required (default: 3)
            band_overlap_threshold: Minimum band overlap ratio (default: 0.5)
        """
        self.min_pool_size = min_pool_size
        self.band_overlap_threshold = band_overlap_threshold
        
    def filter_cases(
        self,
        query: Dict[str, any],
        candidates: List[Dict[str, any]],
        return_filter_level: bool = False
    ) -> List[int] | tuple[List[int], int]:
        """
        Apply hierarchical filtering to select relevant cases.
        
        Args:
            query: Query feature vector with event_type, tech_added, bands_added
            candidates: List of candidate feature vectors
            return_filter_level: Whether to return the filter level used
            
        Returns:
            List of indices of filtered cases, optionally with filter level (0-3)
        """
        # This partition must survive every relaxation, including global fallback.
        query_scheme = query.get('tier_scheme')
        compatible = [i for i,c in enumerate(candidates) if query_scheme is None or c.get('tier_scheme') == query_scheme]
        # Extract query configuration
        query_event = query.get('event_type', '')
        query_tech = query.get('tech_added', '')
        query_bands = self._parse_bands(query.get('bands_added', ''))
        
        # Level 1: event_type match
        level1_indices = []
        for i, candidate in enumerate(candidates):
            if i not in compatible:
                continue
            if candidate.get('event_type', '') == query_event:
                level1_indices.append(i)
        
        logger.debug(f"Level 1 (event_type={query_event}): {len(level1_indices)} cases")
        
        if len(level1_indices) >= self.min_pool_size:
            # Level 2: tech_added match
            level2_indices = []
            for i in level1_indices:
                if candidates[i].get('tech_added', '') == query_tech:
                    level2_indices.append(i)
            
            logger.debug(f"Level 2 (tech_added={query_tech}): {len(level2_indices)} cases")
            
            if len(level2_indices) >= self.min_pool_size:
                # Level 3: bands overlap
                level3_indices = []
                for i in level2_indices:
                    candidate_bands = self._parse_bands(candidates[i].get('bands_added', ''))
                    overlap = self._compute_band_overlap(query_bands, candidate_bands)
                    
                    if overlap >= self.band_overlap_threshold:
                        level3_indices.append(i)
                
                logger.debug(f"Level 3 (bands overlap ≥{self.band_overlap_threshold}): {len(level3_indices)} cases")
                
                if len(level3_indices) >= self.min_pool_size:
                    logger.info(f"Using filter level 3 (full hierarchy) with {len(level3_indices)} cases")
                    return (level3_indices, 3) if return_filter_level else level3_indices
                else:
                    logger.info(f"Relaxed to filter level 2 (event+tech) with {len(level2_indices)} cases")
                    return (level2_indices, 2) if return_filter_level else level2_indices
            else:
                logger.info(f"Relaxed to filter level 1 (event only) with {len(level1_indices)} cases")
                return (level1_indices, 1) if return_filter_level else level1_indices
        else:
            # Fallback to global model (all cases)
            logger.warning(f"Insufficient cases at level 1. Using global model with {len(candidates)} cases")
            all_indices = compatible
            return (all_indices, 0) if return_filter_level else all_indices
    
    def _parse_bands(self, bands_str: str) -> Set[str]:
        """
        Parse bands string into set of band identifiers.
        
        Args:
            bands_str: Comma-separated band string (e.g., "800,1800,2600")
            
        Returns:
            Set of band identifiers
        """
        if not bands_str or bands_str == '':
            return set()
        
        # Split by comma and strip whitespace
        bands = [b.strip() for b in str(bands_str).split(',')]
        return set(bands)
    
    def _compute_band_overlap(self, bands1: Set[str], bands2: Set[str]) -> float:
        """
        Compute Jaccard overlap between two band sets.
        
        Jaccard = |A ∩ B| / |A ∪ B|
        
        Args:
            bands1: First set of bands
            bands2: Second set of bands
            
        Returns:
            Overlap ratio in [0, 1]
        """
        if not bands1 and not bands2:
            return 1.0  # Both empty → perfect match
        
        if not bands1 or not bands2:
            return 0.0  # One empty → no overlap
        
        intersection = bands1.intersection(bands2)
        union = bands1.union(bands2)
        
        if len(union) == 0:
            return 0.0
        
        return len(intersection) / len(union)
    
    def get_filter_statistics(
        self,
        query: Dict[str, any],
        candidates: List[Dict[str, any]]
    ) -> Dict:
        """
        Get statistics about filtering at each level.
        
        Args:
            query: Query feature vector
            candidates: List of candidate feature vectors
            
        Returns:
            Dictionary with counts at each filter level
        """
        if query.get('tier_scheme') is not None:
            candidates=[c for c in candidates if c.get('tier_scheme')==query['tier_scheme']]
        query_event = query.get('event_type', '')
        query_tech = query.get('tech_added', '')
        query_bands = self._parse_bands(query.get('bands_added', ''))
        
        # Level 1
        level1_count = sum(1 for c in candidates if c.get('event_type', '') == query_event)
        
        # Level 2
        level2_count = sum(
            1 for c in candidates
            if c.get('event_type', '') == query_event and c.get('tech_added', '') == query_tech
        )
        
        # Level 3
        level3_count = 0
        for c in candidates:
            if c.get('event_type', '') == query_event and c.get('tech_added', '') == query_tech:
                candidate_bands = self._parse_bands(c.get('bands_added', ''))
                overlap = self._compute_band_overlap(query_bands, candidate_bands)
                if overlap >= self.band_overlap_threshold:
                    level3_count += 1
        
        return {
            'total_cases': len(candidates),
            'level1_event_match': level1_count,
            'level2_event_tech_match': level2_count,
            'level3_full_match': level3_count,
            'query_event': query_event,
            'query_tech': query_tech,
            'query_bands': list(query_bands)
        }
    
    def explain_filtering(
        self,
        query: Dict[str, any],
        candidates: List[Dict[str, any]],
        selected_indices: List[int],
        filter_level: int
    ) -> str:
        """
        Generate human-readable explanation of filtering.
        
        Args:
            query: Query feature vector
            candidates: List of candidate feature vectors
            selected_indices: Indices of selected cases
            filter_level: Filter level used (0-3)
            
        Returns:
            Explanation string
        """
        stats = self.get_filter_statistics(query, candidates)
        
        explanations = {
            0: f"Used global model (all {stats['total_cases']} cases) because insufficient matches at event level.",
            1: f"Filtered by event type '{stats['query_event']}' → {stats['level1_event_match']} cases (relaxed from tech/band filters).",
            2: f"Filtered by event '{stats['query_event']}' + tech '{stats['query_tech']}' → {stats['level2_event_tech_match']} cases (relaxed band filter).",
            3: f"Full hierarchical filter: event '{stats['query_event']}' + tech '{stats['query_tech']}' + bands {stats['query_bands']} → {stats['level3_full_match']} cases."
        }
        
        prefix=f"Tier scheme {query['tier_scheme']} only. " if query.get('tier_scheme') else ''
        return prefix+explanations.get(filter_level, f"Used {len(selected_indices)} filtered cases")
