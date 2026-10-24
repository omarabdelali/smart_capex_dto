"""Detect added cells from imported MAOS monthly activity."""

from django.core.management.base import BaseCommand, CommandError

from services.models.preprocessing.maos_launch_detector import MAOSLaunchDetector


class Command(BaseCommand):
    help = 'Detect first-activity 2G, 3G, LTE, and site additions from MAOS history'

    def handle(self, *args, **options):
        try:
            stats = MAOSLaunchDetector().detect_and_save()
        except Exception as exc:
            raise CommandError(f'Cell addition detection failed: {exc}') from exc

        self.stdout.write(f"Cells evaluated: {stats['cells_evaluated']:,}")
        self.stdout.write(self.style.SUCCESS(f"Added cells detected: {stats['detected_cells']:,}"))
        self.stdout.write(self.style.SUCCESS(f"Sites with detected technology events: {stats['detected_sites']:,}"))
        self.stdout.write(f"Site/technology events: {stats['detected_site_technologies']:,}")
        self.stdout.write(f"MAOS history starts: {stats['data_start']}")
