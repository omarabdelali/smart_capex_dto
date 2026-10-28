from django.core.management.base import BaseCommand, CommandError
from services.tdd_scope_cleanup import apply_tdd_cell_scope
from services.data_scope_cleanup import rebuild_retained_scope
import json


class Command(BaseCommand):
    help='Restore the audited original inventory and remove TDD cells while retaining physical sites.'

    def add_arguments(self,parser):
        parser.add_argument('--backup',required=True)
        parser.add_argument('--apply',action='store_true')

    def handle(self,*args,**options):
        if not options['apply']:
            raise CommandError('Use --apply to perform the authorized cell-only TDD removal.')
        result=apply_tdd_cell_scope(options['backup'],self.stdout.write)
        self.stdout.write(json.dumps(result,indent=2))
        result=rebuild_retained_scope(result,self.stdout.write)
        self.stdout.write(json.dumps(result,indent=2))
