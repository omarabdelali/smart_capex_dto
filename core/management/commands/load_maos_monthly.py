"""Load monthly Huawei MAOS counters from the native export format."""

from django.core.management.base import BaseCommand, CommandError

from services.models.preprocessing.maos_report_loader import MAOSReportLoader


class Command(BaseCommand):
    help = 'Import monthly MAOS counters and link rows to cells by exact cell name'

    def add_arguments(self, parser):
        parser.add_argument('--csv', help='Monthly MAOS CSV path; discovers the project export by default')

    def handle(self, *args, **options):
        try:
            csv_path = options['csv'] or MAOSReportLoader.discover_monthly_csv()
            stats = MAOSReportLoader(str(csv_path)).import_to_database()
        except Exception as exc:
            raise CommandError(f'MAOS monthly import failed: {exc}') from exc

        self.stdout.write(f'Source: {csv_path}')
        self.stdout.write(f"Rows read: {stats['rows_read']:,}")
        self.stdout.write(f"Valid cell-month rows submitted: {stats['rows_submitted']:,}")
        self.stdout.write(f"Unmatched cell names: {stats['unmatched_cells']:,}")
        self.stdout.write(f"Invalid month values: {stats['invalid_dates']:,}")
