from django.core.management.base import BaseCommand
from services.models.prediction.recipient_reference import freeze_pair_reference


class Command(BaseCommand):
    help='Freeze global event-recipient P5-P95 ranges by historical cutoff'
    def handle(self,*args,**options):
        self.stdout.write(str(freeze_pair_reference()))
