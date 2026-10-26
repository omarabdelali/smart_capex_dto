from django.core.management.base import BaseCommand
from services.models.features.road_diagnostics import save_road_diagnostics


class Command(BaseCommand):
    help = 'Report road/context correlations, VIF, and historical ablation eligibility'

    def handle(self, *args, **options):
        self.stdout.write(save_road_diagnostics())
