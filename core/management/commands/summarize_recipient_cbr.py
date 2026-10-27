from django.core.management.base import BaseCommand
from services.models.prediction.recipient_reporting import write_recipient_report


class Command(BaseCommand):
    help='Summarize saved recipient validation, matched-case errors and interval readiness'
    def add_arguments(self,parser):
        parser.add_argument('--input',default='docs/verification/recipient_cbr/validation.json')
    def handle(self,*args,**options):
        self.stdout.write(str(write_recipient_report(options['input'])))
