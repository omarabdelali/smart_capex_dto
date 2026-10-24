"""
Script to load cell plan data and run clustering pipeline.
Run with: python manage.py shell < scripts/load_and_cluster.py
"""

import os
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smart_capex_backend.settings')
django.setup()

from services.models.preprocessing.cellplan_loader import CellPlanLoader
from services.models.preprocessing.site_clustering import SiteClusteringPipeline
from core.models import Site

print("=" * 60)
print("Smart CAPEX: Load Cell Plan and Run Clustering")
print("=" * 60)

# Step 1: Load cell plan data
print("\n[1/2] Loading cell plan data...")
loader = CellPlanLoader('data/cellplan/Cell_Plan_Data_21102026.xlsx', run_clustering=False)
load_result = loader.load()
print(f"✓ Loaded {load_result['sites']} sites and {load_result['cells']} cells to database")

# Step 2: Run clustering pipeline
print("\n[2/2] Running clustering pipeline...")
cluster_result = loader.run_clustering_pipeline()
results = cluster_result

print("\n" + "=" * 60)
print("Clustering Results:")
print("=" * 60)
print(f"Total sites processed: {results['total_sites']}")
print(f"Sites after deduplication: {results['deduplicated_sites']}")
print(f"Number of clusters: {results['n_clusters']}")
print(f"Noise sites (cluster_id=-1): {results['noise_sites']}")
print(f"Edge sites: {results['edge_sites']}")
print(f"Out-of-bounds sites: {results['out_of_bounds_sites']}")

# Verify database updates
site_count = Site.objects.count()
clustered_count = Site.objects.exclude(cluster_id=-1).count()
edge_count = Site.objects.filter(is_cluster_edge=True).count()
oob_count = Site.objects.filter(out_of_bounds=True).count()

print("\n" + "=" * 60)
print("Database Verification:")
print("=" * 60)
print(f"Total sites in database: {site_count}")
print(f"Sites in clusters (not noise): {clustered_count}")
print(f"Edge sites: {edge_count}")
print(f"Out-of-bounds sites: {oob_count}")

print("\n✓ Data loading and clustering complete!")
print("✓ Refresh your browser to see clustered sites on the map")
print("=" * 60)