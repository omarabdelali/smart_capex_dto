"""
MAOS Monthly KPI Data Loader

Loads Huawei MAOS monthly KPI counter data from Excel files.
Used for launch detection and pre-launch feature extraction.

Key counters:
- L.Traffic.User.Avg: Average traffic per user (launch detection)
- L.Thrp.bits.DL/UL: Downlink/uplink throughput
- L.ChMeas.PRB.UL.Used.Avg/L.ChMeas.PRB.DL.Used.Avg: PRB utilization
- L.Traffic.User.RRC.Conn.Avg: RRC connected users
- L.ChMeas.PDSCH.PRB.DL.Used.Avg: PDSCH PRB usage
- L.ChMeas.RSRP.*.Avg: RSRP measurements

Reference: Spec Section 5.1 (Launch Detection Algorithm)
"""

import polars as pl
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class MAOSLoader:
    """Load and process MAOS monthly KPI data for launch detection and feature extraction."""
    
    # Expected column mappings (MAOS export format may vary)
    COLUMN_MAPPING = {
        # Cell identifiers
        'cell_name': 'CELL_NAME',
        'cell_id': 'CELL_ID',
        'site_name': 'SITE_NAME',
        'site_id': 'SITE_ID',
        
        # Traffic counters
        'L.Traffic.User.Avg': 'traffic_user_avg',
        'L.Thrp.bits.DL': 'thrp_bits_dl',
        'L.Thrp.bits.UL': 'thrp_bits_ul',
        
        # PRB utilization
        'L.ChMeas.PRB.DL.Used.Avg': 'prb_util_dl_pct',
        'L.ChMeas.PRB.UL.Used.Avg': 'prb_util_ul_pct',
        
        # RRC connections
        'L.Traffic.User.RRC.Conn.Avg': 'rrc_conn_avg',
        'L.Traffic.User.Active.Avg': 'active_users_avg',
        
        # Radio quality
        'L.ChMeas.CQI.Avg': 'cqi_avg',
        'L.ChMeas.RSRP.Avg': 'rsrp_avg_dbm',
        
        # Time dimension
        'month': 'month_date',
        'date': 'month_date',
    }
    
    def __init__(self, maos_dir: Path):
        """
        Initialize MAOS loader.
        
        Args:
            maos_dir: Directory containing MAOS Excel files
        """
        self.maos_dir = Path(maos_dir)
        self.data = None
        
    def load(self, file_pattern: str = "*.xlsx") -> pl.DataFrame:
        """
        Load MAOS monthly KPI data from Excel files.
        
        Args:
            file_pattern: Glob pattern for Excel files (default: "*.xlsx")
            
        Returns:
            Polars DataFrame with normalized KPI data
        """
        logger.info(f"Loading MAOS data from {self.maos_dir}")
        
        # Find all Excel files
        maos_files = list(self.maos_dir.glob(file_pattern))
        if not maos_files:
            logger.warning(f"No MAOS files found matching {file_pattern} in {self.maos_dir}")
            return pl.DataFrame()
        
        logger.info(f"Found {len(maos_files)} MAOS file(s)")
        
        # Load and concatenate all files
        dfs = []
        for file_path in maos_files:
            try:
                logger.info(f"Loading {file_path.name}")
                df = self._load_single_file(file_path)
                dfs.append(df)
            except Exception as e:
                logger.error(f"Failed to load {file_path}: {e}")
                continue
        
        if not dfs:
            logger.error("No MAOS data loaded successfully")
            return pl.DataFrame()
        
        # Concatenate all dataframes
        self.data = pl.concat(dfs, how="vertical")
        
        # Normalize and validate
        self.data = self._normalize_data(self.data)
        
        logger.info(f"Loaded {len(self.data)} MAOS records")
        logger.info(f"Date range: {self.data['month_date'].min()} to {self.data['month_date'].max()}")
        logger.info(f"Unique cells: {self.data['cell_name'].n_unique()}")
        
        return self.data
    
    def _load_single_file(self, file_path: Path) -> pl.DataFrame:
        """Load a single MAOS Excel file."""
        # Read Excel file
        df = pl.read_excel(file_path)
        
        # Normalize column names (remove spaces, lowercase)
        df.columns = [col.strip().replace(' ', '_').lower() for col in df.columns]
        
        return df
    
    def _normalize_data(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Normalize MAOS data:
        - Map columns to standard names
        - Parse dates
        - Handle missing values
        - Convert units
        """
        # Create column mapping (flexible matching)
        rename_map = {}
        for orig_col in df.columns:
            for maos_col, std_col in self.COLUMN_MAPPING.items():
                if maos_col.lower().replace('.', '_').replace(' ', '_') in orig_col:
                    rename_map[orig_col] = std_col
                    break
        
        # Rename columns
        df = df.rename(rename_map)
        
        # Parse month_date if it's a string
        if 'month_date' in df.columns:
            if df['month_date'].dtype == pl.Utf8:
                df = df.with_columns([
                    pl.col('month_date').str.strptime(pl.Date, format='%Y-%m-%d', strict=False)
                ])
        
        # Fill missing numeric values with 0
        numeric_cols = [
            'traffic_user_avg', 'thrp_bits_dl', 'thrp_bits_ul',
            'prb_util_dl_pct', 'prb_util_ul_pct', 'rrc_conn_avg',
            'active_users_avg', 'cqi_avg', 'rsrp_avg_dbm'
        ]
        for col in numeric_cols:
            if col in df.columns:
                df = df.with_columns([
                    pl.col(col).fill_null(0).fill_nan(0)
                ])
        
        # Sort by cell and date
        if 'cell_name' in df.columns and 'month_date' in df.columns:
            df = df.sort(['cell_name', 'month_date'])
        
        return df
    
    def detect_launches(
        self,
        min_traffic_threshold: float = 0.0,
        lookback_months: int = 2
    ) -> pl.DataFrame:
        """
        Detect newly launched cells using KPI-based algorithm.
        
        Algorithm (Spec Section 5.1):
        1. For each cell, find first month where traffic_user_avg > 0
        2. Verify NO traffic in previous lookback_months
        3. Mark as launch if criteria met
        
        Args:
            min_traffic_threshold: Minimum traffic to consider "active" (default: 0.0)
            lookback_months: Number of months to check for no prior traffic (default: 2)
            
        Returns:
            DataFrame with columns: cell_name, launch_date, pre_launch_months
        """
        if self.data is None or len(self.data) == 0:
            logger.warning("No MAOS data loaded. Call load() first.")
            return pl.DataFrame()
        
        logger.info("Detecting launches using KPI-based algorithm...")
        
        # Get data with traffic > threshold
        active_data = self.data.filter(pl.col('traffic_user_avg') > min_traffic_threshold)
        
        # Find first active month for each cell
        first_active = (
            active_data
            .group_by('cell_name')
            .agg([
                pl.col('month_date').min().alias('first_active_month')
            ])
        )
        
        # For each cell, check if there was NO traffic in previous months
        launches = []
        for row in first_active.iter_rows(named=True):
            cell_name = row['cell_name']
            first_month = row['first_active_month']
            
            # Get all data for this cell before first active month
            prior_data = self.data.filter(
                (pl.col('cell_name') == cell_name) &
                (pl.col('month_date') < first_month)
            )
            
            # Check if there are at least lookback_months of prior data with zero traffic
            if len(prior_data) >= lookback_months:
                max_prior_traffic = prior_data['traffic_user_avg'].max()
                if max_prior_traffic <= min_traffic_threshold:
                    launches.append({
                        'cell_name': cell_name,
                        'launch_date': first_month,
                        'pre_launch_months': len(prior_data)
                    })
        
        if not launches:
            logger.warning("No launches detected")
            return pl.DataFrame()
        
        launch_df = pl.DataFrame(launches)
        logger.info(f"Detected {len(launch_df)} cell launches")
        
        return launch_df
    
    def get_pre_launch_kpis(
        self,
        cell_name: str,
        launch_date: datetime,
        months_before: int = 1
    ) -> Optional[Dict]:
        """
        Extract pre-launch KPIs for a cell.
        
        Used for building pre-launch feature vectors (9 features).
        
        Args:
            cell_name: Cell name
            launch_date: Launch date
            months_before: Number of months before launch to extract (default: 1)
            
        Returns:
            Dictionary with pre-launch KPI aggregates or None if insufficient data
        """
        if self.data is None:
            return None
        
        # Get data from months_before period before launch
        pre_data = self.data.filter(
            (pl.col('cell_name') == cell_name) &
            (pl.col('month_date') < launch_date) &
            (pl.col('month_date') >= launch_date - pl.duration(days=30 * months_before))
        )
        
        if len(pre_data) == 0:
            return None
        
        # Compute aggregates
        kpis = {
            'avg_traffic_dl_gb': pre_data['thrp_bits_dl'].mean() / (8 * 1e9) if 'thrp_bits_dl' in pre_data.columns else 0.0,
            'avg_traffic_ul_gb': pre_data['thrp_bits_ul'].mean() / (8 * 1e9) if 'thrp_bits_ul' in pre_data.columns else 0.0,
            'avg_users': pre_data['active_users_avg'].mean() if 'active_users_avg' in pre_data.columns else 0.0,
            'avg_prb_util_pct': pre_data['prb_util_dl_pct'].mean() if 'prb_util_dl_pct' in pre_data.columns else 0.0,
            'peak_hour_traffic_gb': pre_data['thrp_bits_dl'].max() / (8 * 1e9) if 'thrp_bits_dl' in pre_data.columns else 0.0,
            'peak_hour_users': pre_data['active_users_avg'].max() if 'active_users_avg' in pre_data.columns else 0.0,
            'avg_cqi': pre_data['cqi_avg'].mean() if 'cqi_avg' in pre_data.columns else 0.0,
            'avg_rsrp_dbm': pre_data['rsrp_avg_dbm'].mean() if 'rsrp_avg_dbm' in pre_data.columns else -100.0,
            'congestion_hours_per_day': 0.0  # Placeholder - requires hourly data
        }
        
        return kpis
    
    def get_statistics(self) -> Dict:
        """Get statistics about loaded MAOS data."""
        if self.data is None or len(self.data) == 0:
            return {}
        
        return {
            'total_records': len(self.data),
            'unique_cells': self.data['cell_name'].n_unique() if 'cell_name' in self.data.columns else 0,
            'date_range': {
                'min': str(self.data['month_date'].min()) if 'month_date' in self.data.columns else None,
                'max': str(self.data['month_date'].max()) if 'month_date' in self.data.columns else None
            },
            'avg_traffic_per_cell': self.data['traffic_user_avg'].mean() if 'traffic_user_avg' in self.data.columns else 0.0,
            'cells_with_zero_traffic': len(self.data.filter(pl.col('traffic_user_avg') == 0)) if 'traffic_user_avg' in self.data.columns else 0
        }