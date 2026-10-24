"""
KPI feature extraction for Smart CAPEX.
Computes pre-launch KPI features from MAOS data.
"""

from typing import Dict, Optional, List
import logging
from dataclasses import dataclass
from datetime import datetime

from services.models.preprocessing.maos_loader import MAOSMonthlyLoader

logger = logging.getLogger(__name__)


@dataclass
class KPIFeatureResult:
    """Result of KPI feature extraction."""
    site_id: str
    launch_month: Optional[datetime]
    coverage_ratio_pre: Optional[float]
    coverage_gap_pre: Optional[float]
    avg_prb_pre: Optional[float]
    avg_rrc_pre: Optional[float]
    avg_throughput_pre: Optional[float]
    avg_latency_pre: Optional[float]
    dl_traffic_pre_gb_day: Optional[float]
    traffic_density_mbb_pre: Optional[float]
    traffic_density_fwa_pre: Optional[float]
    traffic_density_box_pre: Optional[float]
    traffic_ratio_pre: Optional[float]
    gap_score_pre: Optional[float]
    success: bool
    error_message: Optional[str] = None


class KPIFeatureExtractor:
    """
    Extracts pre-launch KPI features from MAOS monthly data.
    
    Computes 12 KPI features from Smart CAPEX Phase 1 specification:
    - coverage_ratio_pre: Pre-launch coverage ratio (0-1)
    - coverage_gap_pre: Pre-launch coverage gap (0-1)
    - avg_prb_pre: Average PRB utilization (0-100%)
    - avg_rrc_pre: Average connected users (0-800)
    - avg_throughput_pre: Average user throughput Mbps (0-80)
    - avg_latency_pre: Average P95 latency ms (0-95)
    - dl_traffic_pre_gb_day: Daily downlink traffic GB/day (0-800)
    - traffic_density_mbb_pre: Mobile broadband traffic density (0-1000)
    - traffic_density_fwa_pre: Fixed wireless traffic density (0-1000)
    - traffic_density_box_pre: FDD Boxies traffic density (0-1000)
    - traffic_ratio_pre: Demand to capacity ratio (0-10)
    - gap_score_pre: Combined gap metric (0-10)
    
    Data source: MAOS monthly KPI CSV (36 months)
    """
    
    def __init__(self, maos_csv_path: str):
        """
        Initialize KPI feature extractor.
        
        Args:
            maos_csv_path: Path to MAOS monthly KPI CSV file
        """
        self.maos_loader = MAOSMonthlyLoader(maos_csv_path)
        self.maos_loader.load()
        
        logger.info(f"Initialized KPIFeatureExtractor with MAOS data")
        
        # Log summary
        stats = self.maos_loader.get_summary_stats()
        logger.info(f"MAOS data: {stats['unique_sites']} sites, {stats['total_rows']} rows")
    
    def extract_features(
        self,
        site_id: str,
        launch_month: Optional[datetime] = None
    ) -> KPIFeatureResult:
        """
        Extract all KPI features for a site.
        
        Args:
            site_id: Unique site identifier
            launch_month: Launch month (if None, will auto-detect)
            
        Returns:
            KPIFeatureResult with extracted features
        """
        try:
            # Detect or use provided launch month
            if launch_month is None:
                launch_month = self.maos_loader.detect_launch_month(site_id)
            
            if launch_month is None:
                logger.warning(f"No launch detected for site {site_id}")
                return KPIFeatureResult(
                    site_id=site_id,
                    launch_month=None,
                    coverage_ratio_pre=None,
                    coverage_gap_pre=None,
                    avg_prb_pre=None,
                    avg_rrc_pre=None,
                    avg_throughput_pre=None,
                    avg_latency_pre=None,
                    dl_traffic_pre_gb_day=None,
                    traffic_density_mbb_pre=None,
                    traffic_density_fwa_pre=None,
                    traffic_density_box_pre=None,
                    traffic_ratio_pre=None,
                    gap_score_pre=None,
                    success=False,
                    error_message="No launch month detected"
                )
            
            # Compute pre-launch KPIs
            kpis = self.maos_loader.compute_pre_launch_kpis(site_id, launch_month, n_months_pre=6)
            
            # Map MAOS KPI names to model field names
            # Note: Actual column names depend on MAOS CSV format
            # This mapping may need adjustment based on actual data
            return KPIFeatureResult(
                site_id=site_id,
                launch_month=launch_month,
                coverage_ratio_pre=kpis.get('Coverage_Ratio_pre'),
                coverage_gap_pre=kpis.get('Coverage_Gap_pre'),
                avg_prb_pre=kpis.get('PRB_Utilization_Pct_pre'),
                avg_rrc_pre=kpis.get('RRC_Connected_Users_pre'),
                avg_throughput_pre=kpis.get('Avg_User_Throughput_Mbps_pre'),
                avg_latency_pre=kpis.get('Latency_P95_ms_pre'),
                dl_traffic_pre_gb_day=kpis.get('DL_Traffic_GB_pre'),
                traffic_density_mbb_pre=kpis.get('Traffic_Density_MBB_pre'),
                traffic_density_fwa_pre=kpis.get('Traffic_Density_FWA_pre'),
                traffic_density_box_pre=kpis.get('Traffic_Density_BOX_pre'),
                traffic_ratio_pre=kpis.get('Traffic_Ratio_pre'),
                gap_score_pre=kpis.get('Gap_Score_pre'),
                success=True
            )
            
        except Exception as e:
            logger.error(f"Failed to extract KPI features for site {site_id}: {e}")
            return KPIFeatureResult(
                site_id=site_id,
                launch_month=None,
                coverage_ratio_pre=None,
                coverage_gap_pre=None,
                avg_prb_pre=None,
                avg_rrc_pre=None,
                avg_throughput_pre=None,
                avg_latency_pre=None,
                dl_traffic_pre_gb_day=None,
                traffic_density_mbb_pre=None,
                traffic_density_fwa_pre=None,
                traffic_density_box_pre=None,
                traffic_ratio_pre=None,
                gap_score_pre=None,
                success=False,
                error_message=str(e)
            )
    
    def extract_batch(
        self,
        site_ids: List[str],
        launch_dates: Optional[Dict[str, datetime]] = None
    ) -> List[KPIFeatureResult]:
        """
        Extract KPI features for multiple sites.
        
        Args:
            site_ids: List of site identifiers
            launch_dates: Optional dict of {site_id: launch_month}
            
        Returns:
            List of KPIFeatureResult objects
        """
        results = []
        total = len(site_ids)
        
        logger.info(f"Extracting KPI features for {total} sites...")
        
        for idx, site_id in enumerate(site_ids, 1):
            launch_month = launch_dates.get(site_id) if launch_dates else None
            result = self.extract_features(site_id, launch_month)
            results.append(result)
            
            if idx % 10 == 0 or idx == total:
                logger.info(f"Processed {idx}/{total} sites ({idx/total*100:.1f}%)")
        
        # Summary statistics
        successful = sum(1 for r in results if r.success)
        failed = total - successful
        
        logger.info(f"KPI feature extraction complete: {successful} succeeded, {failed} failed")
        
        return results
    
    def to_dict(self, result: KPIFeatureResult) -> Dict:
        """
        Convert KPIFeatureResult to dictionary for database storage.
        
        Args:
            result: KPIFeatureResult object
            
        Returns:
            Dictionary with feature values (None if extraction failed)
        """
        if not result.success:
            return {
                'coverage_ratio_pre': None,
                'coverage_gap_pre': None,
                'avg_prb_pre': None,
                'avg_rrc_pre': None,
                'avg_throughput_pre': None,
                'avg_latency_pre': None,
                'dl_traffic_pre_gb_day': None,
                'traffic_density_mbb_pre': None,
                'traffic_density_fwa_pre': None,
                'traffic_density_box_pre': None,
                'traffic_ratio_pre': None,
                'gap_score_pre': None,
            }
        
        return {
            'coverage_ratio_pre': result.coverage_ratio_pre,
            'coverage_gap_pre': result.coverage_gap_pre,
            'avg_prb_pre': result.avg_prb_pre,
            'avg_rrc_pre': result.avg_rrc_pre,
            'avg_throughput_pre': result.avg_throughput_pre,
            'avg_latency_pre': result.avg_latency_pre,
            'dl_traffic_pre_gb_day': result.dl_traffic_pre_gb_day,
            'traffic_density_mbb_pre': result.traffic_density_mbb_pre,
            'traffic_density_fwa_pre': result.traffic_density_fwa_pre,
            'traffic_density_box_pre': result.traffic_density_box_pre,
            'traffic_ratio_pre': result.traffic_ratio_pre,
            'gap_score_pre': result.gap_score_pre,
        }