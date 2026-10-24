"""
Django management command to load cell plan data and run clustering pipeline.
Run with: python manage.py load_and_cluster
"""

from django.core.management.base import BaseCommand
from services.models.preprocessing.cellplan_loader import CellPlanLoader
from core.models import Site


class Command(BaseCommand):
    help = 'Load cell plan data and run clustering pipeline'

    def handle(self, *args, **options):
        self.stdout.write("=" * 60)
        self.stdout.write("Smart CAPEX: Load Cell Plan and Run Clustering")
        self.stdout.write("=" * 60)

        # Step 1: Load cell plan data
        self.stdout.write("\n[1/2] Loading cell plan data...")
        loader = CellPlanLoader('data/cellplan/Cell_Plan_Data_21102026.xlsx', run_clustering=True)
        
        try:
            load_result = loader.load()
            sites_msg = f"{load_result['sites']} new" if load_result['sites'] > 0 else "0 new"
            cells_msg = f"{load_result['cells']} new" if load_result['cells'] > 0 else "0 new"
            self.stdout.write(self.style.SUCCESS(
                f"✓ Loaded {sites_msg} sites and {cells_msg} cells to database"
            ))
            self.stdout.write(f"  Total in database: {load_result['total_sites']} sites, {load_result['total_cells']} cells")
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ Error loading cell plan: {e}"))
            return

        # Step 2: Run clustering pipeline (if not already run during load)
        self.stdout.write("\n[2/2] Running clustering pipeline...")
        
        try:
            # If new sites were created, clustering already ran during load()
            # Otherwise, run it explicitly on existing sites
            if load_result['sites'] == 0 and Site.objects.count() > 0:
                cluster_result = loader.run_clustering_pipeline()
            elif 'clustering' in load_result:
                cluster_result = load_result['clustering']
            else:
                self.stdout.write(self.style.WARNING("⚠ No sites to cluster"))
                return
            
            self.stdout.write("\n" + "=" * 60)
            self.stdout.write("Clustering Results:")
            self.stdout.write("=" * 60)
            self.stdout.write(f"Number of clusters: {cluster_result.get('n_clusters', 0)}")
            self.stdout.write(f"Noise sites (single-site clusters): {cluster_result.get('n_noise', 0)}")
            self.stdout.write(f"Out-of-bounds sites: {cluster_result.get('out_of_bounds_count', 0)}")
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ Error running clustering: {e}"))
            import traceback
            self.stdout.write(traceback.format_exc())
            return

        # Verify database updates
        site_count = Site.objects.count()
        clustered_count = Site.objects.exclude(cluster_id=-1).count()
        edge_count = Site.objects.filter(is_cluster_edge=True).count()
        oob_count = Site.objects.filter(out_of_bounds=True).count()

        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("Database Verification:")
        self.stdout.write("=" * 60)
        self.stdout.write(f"Total sites in database: {site_count}")
        self.stdout.write(f"Sites in clusters (not noise): {clustered_count}")
        self.stdout.write(f"Edge sites: {edge_count}")
        self.stdout.write(f"Out-of-bounds sites: {oob_count}")

        self.stdout.write("\n" + self.style.SUCCESS("✓ Data loading and clustering complete!"))
        self.stdout.write(self.style.SUCCESS("✓ Refresh your browser to see clustered sites on the map"))
        self.stdout.write("=" * 60)