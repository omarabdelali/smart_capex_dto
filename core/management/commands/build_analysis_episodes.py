from django.core.management.base import BaseCommand
from services.models.prediction.analysis_episodes import refresh_episodes


class Command(BaseCommand):
    help='Build versioned physical-site/month analysis episodes without changing raw events'

    def handle(self,*args,**options):
        self.stdout.write(str(refresh_episodes()))
