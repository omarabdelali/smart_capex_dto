from django.core.management.base import BaseCommand
from services.models.prediction.pair_validation import validate_pairs


class Command(BaseCommand):
    help='Run nested chronological event-origin-grouped recipient CBR validation (offline only)'

    def add_arguments(self,parser):
        parser.add_argument('--input',default='data/calibration/event_recipient_cases.jsonl')
        parser.add_argument('--output',default='docs/verification/pair_cbr/nested-validation.json')
        parser.add_argument('--events-per-type',type=int,default=60)
        parser.add_argument('--recipients-per-event',type=int,default=3)
        parser.add_argument('--horizons',default='1,3,6')

    def handle(self,*args,**o):
        report=validate_pairs(o['input'],o['output'],o['events_per_type'],o['recipients_per_event'],
            tuple(int(v) for v in o['horizons'].split(',')),self.stdout.write)
        self.stdout.write(f"Validated {report['sample_events']} events / {report['sample_pairs']} pairs; offline only")
