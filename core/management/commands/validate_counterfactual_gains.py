from django.core.management.base import BaseCommand
from services.models.prediction.gain_validation import validate_gains


class Command(BaseCommand):
    help='Run a small chronological gain pilot with origin/recipient purging and explicit coverage'

    def add_arguments(self,parser):
        parser.add_argument('--events-per-type',type=int,default=1)
        parser.add_argument('--output',default='docs/verification/counterfactual_gains/pilot.json')

    def handle(self,*args,**options):
        if options['events_per_type']<1:
            raise ValueError('events-per-type must be positive')
        self.stdout.write(str(validate_gains(options['output'],options['events_per_type'],self.stdout.write)))
