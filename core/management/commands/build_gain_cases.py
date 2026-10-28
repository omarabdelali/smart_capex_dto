from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand
from services.models.prediction.analysis_episodes import refresh_episodes
from services.models.prediction.pair_cases import export_pair_cases
from services.models.prediction.recipient_reference import freeze_pair_reference


class Command(BaseCommand):
    help='Build separate episode gain cases, including event-origin recipients; preserve existing datasets'

    def handle(self,*args,**options):
        base=Path(settings.BASE_DIR)/'data/calibration'
        source=base/'gain_recipient_cases.jsonl'
        self.stdout.write(str(refresh_episodes()))
        self.stdout.write(str(export_pair_cases(source,self.stdout.write,analysis_unit='episode',include_origin=True)))
        self.stdout.write(str(freeze_pair_reference('episode',source_path=source,reference_path=base/'gain_reference.json')))
