from django.core.management.base import BaseCommand
from services.models.prediction.pair_cases import export_pair_cases


class Command(BaseCommand):
    help='Export all current detected event-to-recipient cases with strict historical inputs'

    def add_arguments(self,parser):
        parser.add_argument('--output',default=None)
        parser.add_argument('--episodes',action='store_true',help='Export grouped physical-site/month cases separately')

    def handle(self,*args,**options):
        unit='episode' if options['episodes'] else 'event'
        output=options['output'] or f'data/calibration/{unit}_recipient_cases.jsonl'
        if options['episodes']:
            from services.models.prediction.analysis_episodes import refresh_episodes
            self.stdout.write(str(refresh_episodes()))
        self.stdout.write(str(export_pair_cases(output,self.stdout.write,analysis_unit=unit)))
        if options['output'] is None:
            from services.models.prediction.recipient_reference import freeze_pair_reference
            self.stdout.write(str(freeze_pair_reference(analysis_unit=unit)))
