"""Detect added cells from imported MAOS monthly activity."""

from django.core.management.base import BaseCommand, CommandError

from services.models.preprocessing.maos_launch_detector import MAOSLaunchDetector


class Command(BaseCommand):
    help = 'Detect hierarchical radio events at strictly positive traffic activation months'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--refresh-configuration', action='store_true')

    def handle(self, *args, **options):
        import json
        from services.models.preprocessing.network_events import detect_events
        try:
            stats = detect_events()[3] if options['dry_run'] else MAOSLaunchDetector().detect_and_save()
            if options['refresh_configuration'] and not options['dry_run']:
                from services.models.preprocessing.network_events import refresh_event_configuration
                stats['configuration_rows_refreshed'] = refresh_event_configuration()
        except Exception as exc:
            raise CommandError(f'Radio event detection failed: {exc}') from exc
        self.stdout.write(json.dumps(stats, indent=2, default=str))
