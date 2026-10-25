"""
Django management command to extract features for Smart CAPEX Phase 1.

Usage:
    python manage.py extract_features --cluster 7
    python manage.py extract_features --all
    python manage.py extract_features --site SITE001 SITE002
"""

from django.core.management.base import BaseCommand
from services.models.features.pipeline import FeatureExtractionPipeline
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Extract features for Smart CAPEX sites'

    def add_arguments(self, parser):
        parser.add_argument(
            '--cluster',
            type=int,
            help='Extract features for sites in specified cluster',
        )
        parser.add_argument(
            '--site',
            nargs='+',
            help='Extract features for specific site IDs',
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Extract features for all sites',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Re-extract features even if they already exist',
        )
        parser.add_argument(
            '--maos-csv',
            type=str,
            help='Path to MAOS monthly KPI CSV file',
        )

    def handle(self, *args, **options):
        """Execute feature extraction."""
        
        # Initialize pipeline
        self.stdout.write("Initializing feature extraction pipeline...")
        
        pipeline = FeatureExtractionPipeline(
            maos_csv_path=options.get('maos_csv')
        )
        
        # Determine extraction scope
        cluster_id = options.get('cluster')
        site_ids = options.get('site')
        extract_all = options.get('all')
        skip_existing = not options.get('force')
        
        if not any([cluster_id, site_ids, extract_all]):
            self.stdout.write(
                self.style.ERROR('Must specify --cluster, --site, or --all')
            )
            return
        
        # Display extraction parameters
        if cluster_id:
            self.stdout.write(f"Extracting features for cluster {cluster_id}")
        elif site_ids:
            self.stdout.write(f"Extracting features for {len(site_ids)} sites")
        else:
            self.stdout.write("Extracting features for ALL sites")
        
        if skip_existing:
            self.stdout.write("Skipping sites with existing features")
        else:
            self.stdout.write(self.style.WARNING("Re-extracting ALL features (--force)"))
        
        # Execute extraction
        self.stdout.write("\nStarting feature extraction...")
        
        try:
            stats = pipeline.extract_and_save_features(
                cluster_id=cluster_id,
                site_ids=site_ids,
                skip_existing=skip_existing
            )
            
            # Display results
            self.stdout.write("\n" + "="*60)
            self.stdout.write(self.style.SUCCESS("Feature Extraction Complete"))
            self.stdout.write("="*60)
            
            self.stdout.write(f"Total sites processed: {stats['total']}")
            # ASCII-only labels keep this report compatible with Windows consoles.
            self.stdout.write(self.style.SUCCESS(f"Successful: {stats['successful']}"))
            
            if stats['failed'] > 0:
                self.stdout.write(self.style.ERROR(f"Failed: {stats['failed']}"))
            
            # Display feature-specific failures
            if stats.get('geometric_failures', 0) > 0:
                self.stdout.write(
                    self.style.WARNING(f"  - Geometric failures: {stats['geometric_failures']}")
                )
            if stats.get('clutter_failures', 0) > 0:
                self.stdout.write(
                    self.style.WARNING(f"  - Clutter failures: {stats['clutter_failures']}")
                )
            if stats.get('spatial_failures', 0) > 0:
                self.stdout.write(
                    self.style.WARNING(f"  - Spatial failures: {stats['spatial_failures']}")
                )
            if stats.get('anp_failures', 0) > 0:
                self.stdout.write(
                    self.style.WARNING(f"  - ANP failures: {stats['anp_failures']}")
                )
            if stats.get('kpi_failures', 0) > 0:
                self.stdout.write(
                    self.style.WARNING(f"  - KPI failures: {stats['kpi_failures']}")
                )
            
            self.stdout.write("\n" + "="*60)
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Feature extraction failed: {e}")
            )
            raise
