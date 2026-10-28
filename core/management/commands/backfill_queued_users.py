from django.core.management.base import BaseCommand
from services.models.preprocessing.maos_report_loader import MAOSReportLoader


class Command(BaseCommand):
    help='Backfill nullable queued-user counters from the active monthly MAOS report.'

    def handle(self,*args,**options):
        loader=MAOSReportLoader(str(MAOSReportLoader.discover_monthly_csv()))
        self.stdout.write(str(loader.import_queued_users(lambda stats:self.stdout.write(str(stats)))))
