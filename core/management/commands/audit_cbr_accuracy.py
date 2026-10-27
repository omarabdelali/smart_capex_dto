from django.core.management.base import BaseCommand
from services.models.prediction.accuracy_audit import audit_accuracy


class Command(BaseCommand):
    help='Compare saved rolling CBR forecasts with pre-event persistence/trend/seasonal baselines'
    def handle(self,*args,**options):
        report=audit_accuracy()
        for row in report['comparisons']:
            if row['horizon']==1:
                self.stdout.write(str({k:v for k,v in row.items() if k in ('metric','baseline','cbr_skill_mae','cbr_bias')}))
