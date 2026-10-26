"""Thin command adapter for local road ingestion and backfill."""
import json
from django.core.management.base import BaseCommand
from services.models.features.road_features import backfill_roads, refresh_road_provenance


class Command(BaseCommand):
    help = 'Prepare local Geofabrik road source and persist site road features'

    def add_arguments(self, parser):
        parser.add_argument('--site', nargs='+')
        parser.add_argument('--source')
        parser.add_argument('--extract-date', help='Authoritative extract date YYYY-MM-DD; omit if unknown')
        parser.add_argument('--provenance-only',action='store_true')

    def handle(self, *args, **options):
        if options['provenance_only']:
            self.stdout.write(json.dumps(refresh_road_provenance(options.get('source'),options.get('extract_date')),indent=2))
            return
        result = backfill_roads(options.get('site'), progress_callback=lambda p:self.stdout.write(json.dumps(p)),
                                source_path=options.get('source'), extract_date=options.get('extract_date'))
        self.stdout.write(json.dumps(result, indent=2))
