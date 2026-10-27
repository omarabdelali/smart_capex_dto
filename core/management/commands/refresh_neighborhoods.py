import json
from pathlib import Path
from django.core.management.base import BaseCommand
from services.models.features.neighborhood import refresh_current,refresh_context_features


class Command(BaseCommand):
    help = 'Reconcile physical site labels and rebuild current virtual traffic neighborhoods'

    def handle(self,*args,**options):
        result = refresh_current(progress=lambda value:self.stdout.write(json.dumps(value)))
        result['context_features']=refresh_context_features(progress=lambda value:self.stdout.write(json.dumps(value)))
        path = Path('docs/verification/noise_virtual_clusters/backfill.json')
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(result,indent=2),encoding='utf-8')
        self.stdout.write(json.dumps(result,indent=2))
