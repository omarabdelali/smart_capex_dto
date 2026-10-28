from django.core.management.base import BaseCommand,CommandError
from services.data_scope_cleanup import prepare_scope_cleanup,rebuild_retained_scope
import json


class Command(BaseCommand):
    help='Apply the source-audited C-band physical-site removal with backup and complete derived-data rebuild'

    def add_arguments(self,parser):
        parser.add_argument('--audit',default='docs/verification/data_scope/cband_audit.json')
        parser.add_argument('--apply',action='store_true')
        parser.add_argument('--resume-backup',help='Resume a partially installed cleanup from its verified backup')
        parser.add_argument('--installed-plan-hash',help='SHA-256 of the already installed filtered plan')

    def handle(self,*args,**options):
        raise CommandError('Whole-site exclusion was superseded by the approved TDD cell-only scope; use remove_tdd_cells instead.')
