"""
MAOS Monthly KPI Data Loader for Smart CAPEX.
Loads and processes 36-month Huawei MAOS counter data.
"""

from typing import Dict, List, Optional, Tuple
import logging
from pathlib import Path
from datetime import datetime

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class MAOSMonthlyLoader:
    """
    Load and process MAOS monthly KPI data from CSV files.
    
    Expected CSV format (from Huawei MAOS):
    - Columns: Site_ID, Cell_ID, Month, <KPI columns>
    - KPI columns: DL_Traffic_GB, PRB_Utilization_Pct, RRC_Connected_Users, etc.
    - 36 months of historical data per site/cell
    """
    
    # Expected KPI columns in MAOS CSV
    REQUIRED_COLUMNS = [
        'Site_ID',
        'Cell_ID', 
        'Month',
    ]
    
    # KPI columns (may vary by MAOS export)
    KPI_COLUMNS = [
        'DL_Traffic_GB',          # Downlink traffic (GB)
        'PRB_Utilization_Pct',    # PRB utilization (%)
        'RRC_Connected_Users',    # Average connected users
        'Avg_User_Throughput_Mbps', # Average user throughput (Mbps)
        'Latency_P95_ms',         # P95 latency (ms)
        'Coverage_Ratio',         # Coverage ratio (0-1)
        'Handover_Success_Rate',  # Handover success rate (%)
    ]
    
    def __init__(self, csv_path: str):
        """
        Initialize MAOS monthly loader.
        
        Args:
            csv_path: Path to MAOS monthly KPI CSV file
        """
        self.csv_path = Path(csv_path)
        self.df = None
        
        if not self.csv_path.exists():
            raise FileNotFoundError(f"MAOS CSV file not found: {csv_path}")
        
        logger.info(f"Initialized MAOSMonthlyLoader with file: {csv_path}")
    
    def load(self) -> pd.DataFrame:
        """
        Load MAOS CSV data into DataFrame.
        
        Returns:
            DataFrame with MAOS monthly KPI data
        """
        logger.info(f"Loading MAOS data from {self.csv_path}...")
        
        try:
            # Read CSV with flexible encoding
            self.df = pd.read_csv(self.csv_path, encoding='utf-8-sig')
            
            # Clean column names (remove whitespace, standardize)
            self.df.columns = self.df.columns.str.strip()
            
            logger.info(f"Loaded {len(self.df)} rows, {len(self.df.columns)} columns")
            logger.info(f"Columns: {list(self.df.columns)}")
            
            # Validate required columns
            self._validate_columns()
            
            # Parse month column to datetime
            if 'Month' in self.df.columns:
                self.df['Month'] = pd.to_datetime(self.df['Month'], errors='coerce')
            
            # Sort by Site_ID, Cell_ID, Month
            self.df = self.df.sort_values(['Site_ID', 'Cell_ID', 'Month'])
            
            return self.df
            
        except Exception as e:
            logger.error(f"Failed to load MAOS CSV: {e}")
            raise
    
    def _validate_columns(self):
        """Validate that required columns are present."""
        if self.df is None:
            return
        
        missing = [col for col in self.REQUIRED_COLUMNS if col not in self.df.columns]
        
        if missing:
            logger.warning(f"Missing required columns: {missing}")
            logger.warning("Available columns will be used for KPI extraction")
    
    def get_site_monthly_data(self, site_id: str) -> pd.DataFrame:
        """
        Get all monthly KPI data for a specific site.
        
        Args:
            site_id: Site identifier
            
        Returns:
            DataFrame with monthly KPI data for site (all cells aggregated)
        """
        if self.df is None:
            raise ValueError("Data not loaded. Call load() first.")
        
        site_data = self.df[self.df['Site_ID'] == site_id].copy()
        
        if len(site_data) == 0:
            logger.warning(f"No data found for site {site_id}")
            return pd.DataFrame()
        
        # Aggregate cells to site level (sum traffic, avg others)
        agg_dict = {}
        
        for col in site_data.columns:
            if col in ['Site_ID', 'Month']:
                continue
            elif col == 'Cell_ID':
                agg_dict[col] = 'count'  # Count of cells
            elif 'Traffic' in col or 'GB' in col:
                agg_dict[col] = 'sum'  # Sum traffic
            elif col in self.df.select_dtypes(include=[np.number]).columns:
                agg_dict[col] = 'mean'  # Average other KPIs
        
        if 'Month' in site_data.columns:
            site_agg = site_data.groupby(['Site_ID', 'Month']).agg(agg_dict).reset_index()
        else:
            site_agg = site_data.groupby('Site_ID').agg(agg_dict).reset_index()
        
        return site_agg
    
    def detect_launch_month(
        self,
        site_id: str,
        traffic_col: str = 'DL_Traffic_GB',
        min_traffic_threshold: float = 0.1
    ) -> Optional[datetime]:
        """
        Detect launch month for a site based on traffic appearance.
        
        Launch detected when:
        - First month with traffic > threshold
        - No prior traffic history
        
        Args:
            site_id: Site identifier
            traffic_col: Column name for traffic metric
            min_traffic_threshold: Minimum traffic to consider as launch (GB)
            
        Returns:
            Launch month as datetime, or None if not detected
        """
        site_data = self.get_site_monthly_data(site_id)
        
        if len(site_data) == 0 or traffic_col not in site_data.columns:
            return None
        
        # Sort by month
        site_data = site_data.sort_values('Month')
        
        # Find first month with traffic > threshold
        has_traffic = site_data[traffic_col] > min_traffic_threshold
        
        if not has_traffic.any():
            return None  # No traffic ever
        
        # Get first month with traffic
        launch_idx = has_traffic.idxmax()
        launch_month = site_data.loc[launch_idx, 'Month']
        
        # Verify no prior traffic
        prior_months = site_data[site_data['Month'] < launch_month]
        if len(prior_months) > 0:
            max_prior_traffic = prior_months[traffic_col].max()
            if max_prior_traffic > min_traffic_threshold:
                # Had prior traffic - not a true launch
                return None
        
        return launch_month
    
    def compute_pre_launch_kpis(
        self,
        site_id: str,
        launch_month: datetime,
        n_months_pre: int = 6
    ) -> Dict[str, float]:
        """
        Compute pre-launch KPI averages for a site.
        
        Averages KPIs over n_months_pre before launch month.
        
        Args:
            site_id: Site identifier
            launch_month: Launch month (detected or provided)
            n_months_pre: Number of months before launch to average
            
        Returns:
            Dictionary of pre-launch KPI averages
        """
        site_data = self.get_site_monthly_data(site_id)
        
        if len(site_data) == 0 or 'Month' not in site_data.columns:
            return {}
        
        # Get pre-launch period
        pre_launch = site_data[
            (site_data['Month'] < launch_month) &
            (site_data['Month'] >= launch_month - pd.DateOffset(months=n_months_pre))
        ]
        
        if len(pre_launch) == 0:
            logger.warning(f"No pre-launch data for site {site_id}")
            return {}
        
        # Compute averages for numeric columns
        kpi_avgs = {}
        numeric_cols = pre_launch.select_dtypes(include=[np.number]).columns
        
        for col in numeric_cols:
            if col not in ['Site_ID', 'Cell_ID']:
                kpi_avgs[f'{col}_pre'] = pre_launch[col].mean()
        
        return kpi_avgs
    
    def extract_kpi_features_batch(
        self,
        site_ids: List[str],
        launch_dates: Optional[Dict[str, datetime]] = None
    ) -> List[Dict]:
        """
        Extract pre-launch KPI features for multiple sites.
        
        Args:
            site_ids: List of site identifiers
            launch_dates: Optional dict of {site_id: launch_month}
                         If not provided, will auto-detect launches
            
        Returns:
            List of dicts with KPI features per site
        """
        results = []
        total = len(site_ids)
        
        logger.info(f"Extracting KPI features for {total} sites...")
        
        for idx, site_id in enumerate(site_ids, 1):
            # Get or detect launch month
            if launch_dates and site_id in launch_dates:
                launch_month = launch_dates[site_id]
            else:
                launch_month = self.detect_launch_month(site_id)
            
            if launch_month is None:
                logger.warning(f"No launch detected for site {site_id}, skipping KPI extraction")
                results.append({
                    'site_id': site_id,
                    'launch_month': None,
                    'kpis': {}
                })
                continue
            
            # Compute pre-launch KPIs
            kpis = self.compute_pre_launch_kpis(site_id, launch_month)
            
            results.append({
                'site_id': site_id,
                'launch_month': launch_month,
                'kpis': kpis
            })
            
            if idx % 10 == 0 or idx == total:
                logger.info(f"Processed {idx}/{total} sites ({idx/total*100:.1f}%)")
        
        successful = sum(1 for r in results if r['launch_month'] is not None)
        logger.info(f"KPI feature extraction complete: {successful}/{total} sites with detected launches")
        
        return results
    
    def get_summary_stats(self) -> Dict:
        """
        Get summary statistics of loaded MAOS data.
        
        Returns:
            Dictionary with summary statistics
        """
        if self.df is None:
            raise ValueError("Data not loaded. Call load() first.")
        
        stats = {
            'total_rows': len(self.df),
            'unique_sites': self.df['Site_ID'].nunique() if 'Site_ID' in self.df.columns else 0,
            'unique_cells': self.df['Cell_ID'].nunique() if 'Cell_ID' in self.df.columns else 0,
            'date_range': None,
            'kpi_columns': []
        }
        
        if 'Month' in self.df.columns:
            stats['date_range'] = (
                self.df['Month'].min(),
                self.df['Month'].max()
            )
        
        numeric_cols = self.df.select_dtypes(include=[np.number]).columns
        stats['kpi_columns'] = [col for col in numeric_cols if col not in ['Site_ID', 'Cell_ID']]
        
        return stats