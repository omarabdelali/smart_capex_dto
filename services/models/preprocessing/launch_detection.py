"""
Launch Detection Module

Implements KPI-based launch detection algorithm for newly activated telecom sites.
Classifies launch events into types: NEW_SITE, TECH_ADD, BAND_ADD, SECTOR_ADD, etc.

Algorithm (Spec Section 5.1):
1. Use MAOS KPI data (traffic_user_avg) to detect first activation
2. No traffic (==0) before month 2, traffic appears from month 2+
3. Cross-reference with cell plan to classify event type
4. Validate against known launch dates if available

Reference: Spec Section 5.1 (Launch Detection)
"""

import polars as pl
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import logging

from .maos_loader import MAOSLoader
from .cellplan_loader import CellPlanLoader

logger = logging.getLogger(__name__)


class LaunchDetector:
    """Detect and classify newly launched telecom sites using KPI-based algorithm."""
    
    # Event type classification
    EVENT_TYPES = {
        'NEW_SITE': 'First cells at a new site location',
        'TECH_ADD': 'New technology added to existing site',
        'BAND_ADD': 'New frequency band added to existing technology',
        'SECTOR_ADD': 'New sector added (increase in cell count)',
        'CAPACITY_UPGRADE': 'Bandwidth or capacity upgrade',
        'REACTIVATION': 'Site reactivation after long outage'
    }
    
    def __init__(
        self,
        maos_loader: MAOSLoader,
        cellplan_loader: CellPlanLoader,
        min_traffic_threshold: float = 0.0,
        lookback_months: int = 2,
        reactivation_gap_months: int = 6
    ):
        """
        Initialize launch detector.
        
        Args:
            maos_loader: Loaded MAOS data
            cellplan_loader: Loaded cell plan data
            min_traffic_threshold: Minimum traffic to consider "active" (default: 0.0)
            lookback_months: Months to verify no prior traffic (default: 2)
            reactivation_gap_months: Gap to classify as reactivation vs new launch (default: 6)
        """
        self.maos_loader = maos_loader
        self.cellplan_loader = cellplan_loader
        self.min_traffic_threshold = min_traffic_threshold
        self.lookback_months = lookback_months
        self.reactivation_gap_months = reactivation_gap_months
        
        self.detected_launches = None
        
    def detect_all_launches(self) -> pl.DataFrame:
        """
        Detect all launches using KPI-based algorithm.
        
        Returns:
            DataFrame with columns:
            - site_id, site_name, cell_name, launch_date, event_type,
            - tech_added, bands_added, pre_launch_months
        """
        logger.info("Starting launch detection...")
        
        # Step 1: Detect cell-level launches from MAOS data
        cell_launches = self.maos_loader.detect_launches(
            min_traffic_threshold=self.min_traffic_threshold,
            lookback_months=self.lookback_months
        )
        
        if len(cell_launches) == 0:
            logger.warning("No launches detected in MAOS data")
            return pl.DataFrame()
        
        logger.info(f"Detected {len(cell_launches)} cell-level launches")
        
        # Step 2: Enrich with cell plan data and classify event types
        enriched_launches = self._enrich_with_cellplan(cell_launches)
        
        # Step 3: Aggregate to site level
        site_launches = self._aggregate_to_sites(enriched_launches)
        
        # Step 4: Classify event types
        classified_launches = self._classify_event_types(site_launches)
        
        self.detected_launches = classified_launches
        
        logger.info(f"Detected {len(classified_launches)} site-level launches")
        self._log_event_type_summary(classified_launches)
        
        return classified_launches
    
    def _enrich_with_cellplan(self, cell_launches: pl.DataFrame) -> pl.DataFrame:
        """
        Enrich launch data with cell plan information.
        
        Args:
            cell_launches: DataFrame from MAOS launch detection
            
        Returns:
            Enriched DataFrame with site_id, technology, band, etc.
        """
        if self.cellplan_loader.cells is None:
            logger.warning("Cell plan data not loaded. Cannot enrich launches.")
            return cell_launches
        
        # Get cell plan cells as DataFrame
        cellplan_data = []
        for cell in self.cellplan_loader.cells:
            cellplan_data.append({
                'cell_name': cell.cell_name,
                'site_id': cell.site.site_id,
                'site_name': cell.site.site_name,
                'technology': cell.technology,
                'frequency': cell.frequency,
                'band': cell.band,
                'bandwidth_mhz': cell.bandwidth_mhz,
                'azimuth': cell.azimuth,
                'antenna_height_m': cell.antenna_height_m
            })
        
        cellplan_df = pl.DataFrame(cellplan_data)
        
        # Join with cell launches
        enriched = cell_launches.join(
            cellplan_df,
            on='cell_name',
            how='left'
        )
        
        return enriched
    
    def _aggregate_to_sites(self, cell_launches: pl.DataFrame) -> pl.DataFrame:
        """
        Aggregate cell-level launches to site level.
        
        Multiple cells at same site launched at same time → single site launch event
        
        Args:
            cell_launches: Cell-level launch data
            
        Returns:
            Site-level launch data
        """
        if 'site_id' not in cell_launches.columns:
            logger.warning("No site_id in launches. Cannot aggregate.")
            return cell_launches
        
        # Group by site and launch_date
        site_launches = (
            cell_launches
            .group_by(['site_id', 'site_name', 'launch_date'])
            .agg([
                pl.col('cell_name').count().alias('cells_launched'),
                pl.col('technology').unique().alias('technologies'),
                pl.col('band').unique().alias('bands'),
                pl.col('pre_launch_months').min().alias('pre_launch_months')
            ])
        )
        
        return site_launches
    
    def _classify_event_types(self, site_launches: pl.DataFrame) -> pl.DataFrame:
        """
        Classify each launch into event type.
        
        Event types:
        - NEW_SITE: First cells at location
        - TECH_ADD: New technology at existing site
        - BAND_ADD: New band in existing technology
        - SECTOR_ADD: More cells/sectors
        - REACTIVATION: Restart after long outage
        
        Args:
            site_launches: Site-level launch data
            
        Returns:
            Launches with event_type classification
        """
        classified = []
        
        for row in site_launches.iter_rows(named=True):
            site_id = row['site_id']
            launch_date = row['launch_date']
            technologies = row['technologies']
            bands = row['bands']
            cells_count = row['cells_launched']
            
            # Determine event type
            event_type = self._determine_event_type(
                site_id,
                launch_date,
                technologies,
                bands,
                cells_count
            )
            
            classified.append({
                'site_id': site_id,
                'site_name': row['site_name'],
                'launch_date': launch_date,
                'event_type': event_type,
                'tech_added': ','.join(technologies) if isinstance(technologies, list) else str(technologies),
                'bands_added': ','.join(map(str, bands)) if isinstance(bands, list) else str(bands),
                'cells_launched': cells_count,
                'pre_launch_months': row['pre_launch_months']
            })
        
        return pl.DataFrame(classified)
    
    def _determine_event_type(
        self,
        site_id: str,
        launch_date: datetime,
        technologies: List[str],
        bands: List,
        cells_count: int
    ) -> str:
        """
        Determine event type for a site launch.
        
        Logic:
        1. Check if site existed before (in cell plan or MAOS history)
        2. If new → NEW_SITE
        3. If existing, check what changed:
           - Different technology → TECH_ADD
           - Same tech, different band → BAND_ADD
           - More cells → SECTOR_ADD
           - Long gap in traffic → REACTIVATION
        """
        # Check if site has earlier MAOS data
        if self.maos_loader.data is not None:
            prior_data = self.maos_loader.data.filter(
                (pl.col('site_id') == site_id) &
                (pl.col('month_date') < launch_date)
            )
            
            # Check for reactivation (long gap with previous traffic)
            if len(prior_data) > 0:
                last_traffic_date = prior_data.filter(
                    pl.col('traffic_user_avg') > 0
                )['month_date'].max()
                
                if last_traffic_date is not None:
                    gap_months = (launch_date - last_traffic_date).days / 30
                    if gap_months >= self.reactivation_gap_months:
                        return 'REACTIVATION'
            
            # Check if site existed before with different config
            if len(prior_data) > 0:
                prior_techs = prior_data['technology'].unique().to_list() if 'technology' in prior_data.columns else []
                
                # New technology added
                new_techs = [t for t in technologies if t not in prior_techs]
                if new_techs:
                    return 'TECH_ADD'
                
                # Same technology, check bands
                # (Simplified: assume BAND_ADD if technologies match)
                if set(technologies) == set(prior_techs):
                    return 'BAND_ADD'
                
                # More cells at same site
                return 'SECTOR_ADD'
        
        # Default: NEW_SITE (no prior data found)
        return 'NEW_SITE'
    
    def _log_event_type_summary(self, launches: pl.DataFrame):
        """Log summary of detected event types."""
        if 'event_type' not in launches.columns:
            return
        
        summary = launches.group_by('event_type').agg([
            pl.count().alias('count')
        ])
        
        logger.info("Launch event type summary:")
        for row in summary.iter_rows(named=True):
            logger.info(f"  {row['event_type']}: {row['count']}")
    
    def get_launch_for_site(
        self,
        site_id: str,
        launch_date: Optional[datetime] = None
    ) -> Optional[Dict]:
        """
        Get launch information for a specific site.
        
        Args:
            site_id: Site ID
            launch_date: Optional launch date (if multiple launches, return specific one)
            
        Returns:
            Dictionary with launch details or None if not found
        """
        if self.detected_launches is None:
            logger.warning("No launches detected yet. Call detect_all_launches() first.")
            return None
        
        launches = self.detected_launches.filter(pl.col('site_id') == site_id)
        
        if launch_date:
            launches = launches.filter(pl.col('launch_date') == launch_date)
        
        if len(launches) == 0:
            return None
        
        # Return most recent launch if multiple
        launch = launches.sort('launch_date', descending=True).row(0, named=True)
        return dict(launch)
    
    def validate_detection(
        self,
        ground_truth: pl.DataFrame,
        date_tolerance_days: int = 30
    ) -> Dict:
        """
        Validate launch detection against ground truth.
        
        Args:
            ground_truth: DataFrame with columns site_id, launch_date
            date_tolerance_days: Allowed difference in days (default: 30)
            
        Returns:
            Dictionary with precision, recall, F1-score
        """
        if self.detected_launches is None:
            logger.error("No launches detected. Cannot validate.")
            return {}
        
        detected = self.detected_launches
        
        # Join detected with ground truth
        matches = []
        for gt_row in ground_truth.iter_rows(named=True):
            site_id = gt_row['site_id']
            gt_date = gt_row['launch_date']
            
            # Find detected launch for this site
            det = detected.filter(pl.col('site_id') == site_id)
            
            if len(det) > 0:
                det_date = det['launch_date'].to_list()[0]
                date_diff = abs((det_date - gt_date).days)
                
                if date_diff <= date_tolerance_days:
                    matches.append({
                        'site_id': site_id,
                        'gt_date': gt_date,
                        'det_date': det_date,
                        'date_diff_days': date_diff
                    })
        
        # Compute metrics
        true_positives = len(matches)
        false_positives = len(detected) - true_positives
        false_negatives = len(ground_truth) - true_positives
        
        precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0
        recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0
        f1_score = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        
        validation_results = {
            'true_positives': true_positives,
            'false_positives': false_positives,
            'false_negatives': false_negatives,
            'precision': precision,
            'recall': recall,
            'f1_score': f1_score,
            'avg_date_diff_days': sum([m['date_diff_days'] for m in matches]) / len(matches) if matches else 0
        }
        
        logger.info(f"Validation results: Precision={precision:.2%}, Recall={recall:.2%}, F1={f1_score:.2%}")
        
        return validation_results
    
    def get_statistics(self) -> Dict:
        """Get statistics about detected launches."""
        if self.detected_launches is None:
            return {}
        
        return {
            'total_launches': len(self.detected_launches),
            'event_types': self.detected_launches.group_by('event_type').agg([
                pl.count().alias('count')
            ]).to_dicts(),
            'date_range': {
                'earliest': str(self.detected_launches['launch_date'].min()),
                'latest': str(self.detected_launches['launch_date'].max())
            },
            'avg_cells_per_launch': self.detected_launches['cells_launched'].mean() if 'cells_launched' in self.detected_launches.columns else 0
        }