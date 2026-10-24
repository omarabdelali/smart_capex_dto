"""
Cell Plan Excel loader for Smart CAPEX.
Loads cell plan data and aggregates cells into sites.
Includes site clustering integration.
"""

import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional
from django.conf import settings
from core.models import Site, Cell
from services.models.preprocessing.site_clustering import SiteClusteringPipeline, Site as ClusterSite


class CellPlanLoader:
    """
    Loads cell plan data from Excel file and creates Site/Cell objects.
    Aggregates multiple cells per site by Site ID/Name.
    """
    
    def __init__(self, cellplan_path: Optional[str] = None, run_clustering: bool = True):
        """
        Initialize loader with cell plan file path.
        
        Args:
            cellplan_path: Path to cell plan Excel file. If None, uses settings.CELLPLAN_DIR
            run_clustering: Whether to run clustering pipeline after loading sites
        """
        if cellplan_path is None:
            self.cellplan_path = Path(settings.CELLPLAN_DIR) / 'Cell_Plan_Data_21102026.xlsx'
        else:
            self.cellplan_path = Path(cellplan_path)
        
        if not self.cellplan_path.exists():
            raise FileNotFoundError(f"Cell plan file not found: {self.cellplan_path}")
        
        self.run_clustering = run_clustering
        self.clustering_pipeline: Optional[SiteClusteringPipeline] = SiteClusteringPipeline() if run_clustering else None
    
    def load(self) -> Dict[str, int]:
        """
        Load cell plan data and create Site/Cell database records.
        
        Returns:
            Dictionary with counts: {'sites': N, 'cells': M}
        """
        print(f"Loading cell plan from: {self.cellplan_path}")
        
        # Read Excel file
        df = pd.read_excel(self.cellplan_path)
        
        print(f"Loaded {len(df)} rows from cell plan")
        print(f"Columns: {list(df.columns)}")
        
        # Normalize column names (strip whitespace, lowercase)
        df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_')
        
        # Map technology names to standard format
        tech_mapping = {
            'GSM': '2G',
            'UMTS': '3G',
            'LTE': '4G',
        }
        
        # Apply technology mapping
        if 'technology' in df.columns:
            df['technology'] = df['technology'].str.upper().map(tech_mapping).fillna(df['technology'])
        
        # Group by site to aggregate cells
        site_groups = df.groupby(['site_id', 'site_name'])
        
        sites_created = 0
        cells_created = 0
        site_errors = 0
        cell_errors = 0
        
        print(f"\nProcessing {len(site_groups)} site groups...")
        
        for (site_id, site_name), site_cells in site_groups:
            try:
                # Get site coordinates (use first cell's coordinates)
                first_cell = site_cells.iloc[0]
                lat = first_cell['latitude']
                lon = first_cell['longitude']
                
                # Validate coordinates
                if pd.isna(lat) or pd.isna(lon):
                    print(f"Warning: Site {site_id} has invalid coordinates (lat={lat}, lon={lon}), skipping")
                    site_errors += 1
                    continue
                
                # Validate site_name (handle NaN)
                if pd.isna(site_name):
                    site_name = f"Site_{site_id}"
                    print(f"Warning: Site {site_id} has no name, using {site_name}")
                
                # Create or update site
                site, created = Site.objects.get_or_create(
                    site_id=str(site_id),
                    defaults={
                        'site_name': str(site_name),
                        'latitude': float(lat),
                        'longitude': float(lon),
                        'location': f'POINT({lon} {lat})',  # WKT format for CharField
                    }
                )
                
                if created:
                    sites_created += 1
                    if sites_created % 500 == 0:
                        print(f"  Created {sites_created} sites so far...")
                
            except Exception as e:
                print(f"Error creating site {site_id}: {e}")
                site_errors += 1
                continue
            
            # Create cells for this site
            for _, cell_row in site_cells.iterrows():
                try:
                    # Validate cell_id
                    cell_id = cell_row.get('cell_id')
                    if pd.isna(cell_id):
                        print(f"Warning: Cell with no ID for site {site_id}, skipping")
                        cell_errors += 1
                        continue
                    
                    # Map band/frequency
                    band = str(cell_row.get('band', ''))
                    frequency = float(cell_row.get('frequency', 0)) if not pd.isna(cell_row.get('frequency')) else 0.0
                    
                    # Get technology
                    technology = cell_row.get('technology', '4G')
                    if technology not in ['2G', '3G', '4G']:
                        technology = '4G'  # Default to 4G
                    
                    # Get antenna height
                    antenna_height_val = cell_row.get('antenna_height', 25)
                    antenna_height = float(antenna_height_val) if not pd.isna(antenna_height_val) else 25.0
                    
                    # Get cell_name
                    cell_name = cell_row.get('cell_name', f"Cell_{cell_id}")
                    if pd.isna(cell_name):
                        cell_name = f"Cell_{cell_id}"
                    
                    # Get azimuth
                    azimuth_val = cell_row.get('azimuth', 0)
                    azimuth = float(azimuth_val) if not pd.isna(azimuth_val) else 0.0
                    
                    # Create cell
                    cell, created = Cell.objects.get_or_create(
                        cell_id=str(cell_id),
                        defaults={
                            'site': site,
                            'cell_name': str(cell_name),
                            'cgi': str(cell_row.get('cgi', '')),
                            'technology': technology,
                            'frequency': frequency,
                            'band': band,
                            'bandwidth_mhz': self._get_bandwidth(technology, band),
                            'azimuth': azimuth,
                            'antenna_height_m': antenna_height,
                        }
                    )
                    
                    if created:
                        cells_created += 1
                        if cells_created % 5000 == 0:
                            print(f"  Created {cells_created} cells so far...")
                
                except Exception as e:
                    print(f"Error creating cell {cell_row.get('cell_id', 'UNKNOWN')} for site {site_id}: {e}")
                    cell_errors += 1
                    continue
        
        total_sites_db = Site.objects.count()
        total_cells_db = Cell.objects.count()
        
        print(f"\n{'='*60}")
        print(f"LOADING SUMMARY")
        print(f"{'='*60}")
        print(f"New sites created: {sites_created}")
        print(f"New cells created: {cells_created}")
        print(f"Site errors: {site_errors}")
        print(f"Cell errors: {cell_errors}")
        print(f"Total sites in database: {total_sites_db}")
        print(f"Total cells in database: {total_cells_db}")
        
        if sites_created == 0 and total_sites_db > 0:
            print(f"\n✓ All {total_sites_db} sites already exist in database (no new records created)")
        
        print(f"{'='*60}\n")
        
        result: Dict = {
            'sites': sites_created,
            'cells': cells_created,
            'site_errors': site_errors,
            'cell_errors': cell_errors,
            'total_sites': Site.objects.count(),
            'total_cells': Cell.objects.count(),
        }
        
        # Run clustering pipeline if enabled
        if self.run_clustering and sites_created > 0:
            print("\n" + "="*60)
            print("Running site clustering pipeline...")
            print("="*60)
            
            clustering_result = self.run_clustering_pipeline()
            result['clustering'] = clustering_result
        
        return result
    
    def _get_bandwidth(self, technology: str, band: str) -> float:
        """
        Estimate bandwidth based on technology and band.
        
        Args:
            technology: 2G, 3G, or 4G
            band: Frequency band name
        
        Returns:
            Bandwidth in MHz
        """
        # Default bandwidths by technology
        bw_defaults = {
            '2G': 0.2,  # 200 kHz
            '3G': 5.0,  # 5 MHz
            '4G': 10.0, # 10 MHz (can be 5, 10, 15, or 20)
        }
        
        # Try to extract from band name
        if 'B20' in band.upper():
            return 10.0  # LTE Band 20 typically 10MHz
        elif 'B3' in band.upper():
            return 20.0  # LTE Band 3 can be 10-20MHz
        elif 'B1' in band.upper():
            return 15.0  # LTE Band 1 typically 15MHz
        
        return bw_defaults.get(technology, 10.0)
    
    def get_statistics(self) -> Dict:
        """
        Get statistics about loaded cell plan data.
        
        Returns:
            Dictionary with various statistics
        """
        total_sites = Site.objects.count()
        total_cells = Cell.objects.count()
        
        # Technology breakdown
        tech_counts = {}
        for tech_choice in Cell.TECHNOLOGY_CHOICES:
            tech_code = tech_choice[0]
            count = Cell.objects.filter(technology=tech_code).count()
            tech_counts[tech_code] = count
        
        # Sites by technology
        sites_2g = Site.objects.filter(cells__technology='2G').distinct().count()
        sites_3g = Site.objects.filter(cells__technology='3G').distinct().count()
        sites_4g = Site.objects.filter(cells__technology='4G').distinct().count()
        
        # Average cells per site
        avg_cells_per_site = total_cells / total_sites if total_sites > 0 else 0
        
        return {
            'total_sites': total_sites,
            'total_cells': total_cells,
            'cells_by_tech': tech_counts,
            'sites_with_2g': sites_2g,
            'sites_with_3g': sites_3g,
            'sites_with_4g': sites_4g,
            'avg_cells_per_site': round(avg_cells_per_site, 2),
        }
    
    def run_clustering_pipeline(self) -> Dict:
        """
        Run the full site clustering pipeline on all sites in database.
        
        Returns:
            Dictionary with clustering results and statistics
        """
        if self.clustering_pipeline is None:
            raise RuntimeError("Clustering pipeline not initialized. Set run_clustering=True.")
        
        # Get all sites from database
        sites = Site.objects.all()
        
        if sites.count() == 0:
            return {
                'error': 'No sites found in database',
                'total_sites': 0,
            }
        
        print(f"\nProcessing {sites.count()} sites through clustering pipeline...")
        
        # Convert Django QuerySet to ClusterSite dataclass objects
        cluster_sites = []
        for site in sites:
            cluster_site = ClusterSite(
                site_id=site.site_id,
                site_name=site.site_name,
                latitude=site.latitude,
                longitude=site.longitude,
                traffic_gb=0.0,  # Will be populated from KPIs later
                users=0  # Will be populated from KPIs later
            )
            cluster_sites.append(cluster_site)
        
        # Run clustering pipeline
        cluster_results = self.clustering_pipeline.run(cluster_sites)
        
        # Get polygons for statistics
        polygons = self.clustering_pipeline.get_polygons(cluster_sites)
        
        # Convert results to dict format
        import pandas as pd
        sites_df = pd.DataFrame([
            {
                'site_id': r.site_id,
                'cluster_id': r.cluster_id,
                'is_cluster_edge': r.is_cluster_edge,
                'out_of_bounds': r.out_of_bounds,
                'cluster_size': r.cluster_size,
                'cluster_density_sites_per_km2': r.cluster_density_sites_per_km2,
                'cluster_avg_traffic_gb': r.cluster_avg_traffic_gb,
                'cluster_avg_users': r.cluster_avg_users,
                'dist_to_cluster_centroid_m': r.dist_to_cluster_centroid_m,
            }
            for r in cluster_results
        ])
        
        # Count clusters
        n_clusters = len(set(sites_df['cluster_id']) - {-1})
        n_noise = (sites_df['cluster_id'] == -1).sum()
        out_of_bounds_count = sites_df['out_of_bounds'].sum()
        
        result = {
            'sites': sites_df,
            'polygons': polygons,
            'n_clusters': n_clusters,
            'n_noise': n_noise,
            'out_of_bounds_count': out_of_bounds_count,
        }
        
        # Update Site model with clustering results
        self._update_sites_with_clustering(result)
        
        return result
    
    def _update_sites_with_clustering(self, clustering_result: Dict):
        """
        Update Site objects in database with clustering results.
        
        Args:
            clustering_result: Result dict from SiteClusteringPipeline
        """
        sites_df = clustering_result.get('sites')
        if sites_df is None or len(sites_df) == 0:
            print("No clustering results to update")
            return
        
        print(f"\nUpdating {len(sites_df)} sites with clustering results...")
        
        updated_count = 0
        for _, row in sites_df.iterrows():
            try:
                site = Site.objects.get(site_id=row['site_id'])
                
                # Update clustering fields
                site.cluster_id = int(row['cluster_id'])
                site.is_cluster_edge = bool(row['is_cluster_edge'])
                site.out_of_bounds = bool(row['out_of_bounds'])
                
                site.save(update_fields=['cluster_id', 'is_cluster_edge', 'out_of_bounds'])
                updated_count += 1
                
            except Site.DoesNotExist:
                print(f"Warning: Site {row['site_id']} not found in database")
            except Exception as e:
                print(f"Error updating site {row['site_id']}: {e}")
        
        print(f"Updated {updated_count} sites with clustering data")
        
        # Print clustering summary
        print("\n" + "="*60)
        print("CLUSTERING SUMMARY")
        print("="*60)
        print(f"Total sites processed: {len(sites_df)}")
        print(f"Valid clusters found: {clustering_result.get('n_clusters', 0)}")
        print(f"Noise points (single-site clusters): {clustering_result.get('n_noise', 0)}")
        print(f"Out-of-bounds sites: {clustering_result.get('out_of_bounds_count', 0)}")
        print(f"Edge sites: {(sites_df['is_cluster_edge'] == True).sum()}")
        print(f"Interior sites: {(sites_df['is_cluster_edge'] == False).sum()}")
        print("="*60)
