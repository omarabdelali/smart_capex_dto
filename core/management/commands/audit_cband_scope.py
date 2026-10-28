from django.core.management.base import BaseCommand
from services.data_scope import audit_cband_sources


class Command(BaseCommand):
    help='Read-only audit of MAOS frequency-band/duplex and cell-plan C-band physical sites'

    def add_arguments(self,parser):
        parser.add_argument('--output',default='docs/verification/data_scope/cband_audit.json')

    def handle(self,*args,**options):
        self.stdout.write(str(audit_cband_sources(options['output'])))
