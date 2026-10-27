from django.core.management.base import BaseCommand
from services.models.prediction.recipient_validation import validate_recipients


class Command(BaseCommand):
    help='Run rolling recipient CBR/control/ramp validation and build dated interval calibration'
    def add_arguments(self,parser):
        parser.add_argument('--events-per-type',type=int,default=24)
        parser.add_argument('--recipients-per-event',type=int,default=1)
        parser.add_argument('--output',default='docs/verification/recipient_cbr/validation.json')
    def handle(self,*args,**options):
        report=validate_recipients(options['output'],options['events_per_type'],options['recipients_per_event'],self.stdout.write)
        self.stdout.write(f"Validated {report['sample_events']} events / {report['sample_pairs']} recipient cases")
