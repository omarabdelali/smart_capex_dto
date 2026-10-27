from django.core.management.base import BaseCommand
from services.models.similarity.reference_builder import build_reference


class Command(BaseCommand):
    help='Freeze a deterministic historical event-profile reference; never run implicitly during search'

    def add_arguments(self,parser):
        parser.add_argument('--per-type',type=int,default=12)

    def handle(self,*args,**options):
        result=build_reference(options['per_type'],self.stdout.write)
        self.stdout.write(str(result))
