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
        loader = CellPlanLoader('data/cellplan/Cell_Plan_Data_21102026.xlsx', run_clustering=False)
        
        try:
            load_result = loader.load()
            self.stdout.write(self.style.SUCCESS(
                f"✓ Loaded {load_result['sites']} sites and {load_result['cells']} cells to database"
            ))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ Error loading cell plan: {e}"))
            return

        # Step 2: Run clustering pipeline
        self.stdout.write("\n[2/2] Running clustering pipeline...")
        
        try:
            cluster_result = loader.run_clustering_pipeline()
            
            self.stdout.write("\n" + "=" * 60)
            self.stdout.write("Clustering Results:")
            self.stdout.write("=" * 60)
            self.stdout.write(f"Total sites processed: {cluster_result['total_sites']}")
            self.stdout.write(f"Sites after deduplication: {cluster_result['deduplicated_sites']}")
            self.stdout.write(f"Number of clusters: {cluster_result['n_clusters']}")
            self.stdout.write(f"Noise sites (cluster_id=-1): {cluster_result['noise_sites']}")
            self.stdout.write(f"Edge sites: {cluster_result['edge_sites']}")
            self.stdout.write(f"Out-of-bounds sites: {cluster_result['out_of_bounds_sites']}")
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ Error running clustering: {e}"))
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