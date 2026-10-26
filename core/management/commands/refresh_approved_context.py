import json
from django.core.management.base import BaseCommand
from services.models.features.approved_context import backfill_approved_context


class Command(BaseCommand):
    help='Refresh approved KPI-derived configuration and static absolute antenna elevations'

    def add_arguments(self,parser):
        parser.add_argument('--configuration-only',action='store_true')

    def handle(self,*args,**options):
        if options['configuration_only']:
            from services.models.features.approved_context import backfill_approved_configuration
            self.stdout.write(json.dumps(backfill_approved_configuration(),indent=2))
            return
        result=backfill_approved_context(progress=lambda value:self.stdout.write(json.dumps(value)))
        self.stdout.write(json.dumps(result,indent=2))
