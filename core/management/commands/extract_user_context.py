import json
from pathlib import Path
from django.core.management.base import BaseCommand
from services.models.features.maos_context import backfill_user_context


class Command(BaseCommand):
    help = 'Recalculate all persisted pre-event T1/T2/cluster user ratios'

    def handle(self,*args,**options):
        result = backfill_user_context(progress_callback=lambda p:self.stdout.write(json.dumps(p)))
        output = Path('docs/verification/user_context/backfill.json')
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(result,indent=2),encoding='utf-8')
        self.stdout.write(json.dumps(result,indent=2))
