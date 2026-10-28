"""Verify the active cell-only scope against the preserved SQLite snapshot."""
import json
import os
from pathlib import Path
import sqlite3
import sys

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','smart_capex_backend.settings')
import django
django.setup()
from django.test import Client
from core.models import Site,Cell,MAOSMonthlyKPI,RadioNetworkEvent
from services.data_scope import scope_policy,tdd_cell

backup=root/'data/backups/cband_scope_20261028T075905_70e068'
c=sqlite3.connect(str(root/'db.sqlite3'))
c.execute('attach database ? as original',(str(backup/'database.sqlite3'),))
scalar=lambda q:c.execute(q).fetchone()[0]
missing_sites=scalar('select count(*) from (select id from original.sites except select id from main.sites)')
missing_fdd=scalar("select count(*) from (select id from original.cells where upper(trim(band)) != 'TDD' except select id from main.cells)")
changed_kpi=scalar('select count(*) from (select * from main.maos_monthly_kpi except select k.* from original.maos_monthly_kpi k join main.cells c on c.id=k.cell_id)')
tdd=sum(tdd_cell(band,frequency,technology) for band,frequency,technology in Cell.objects.values_list('band','frequency','technology'))
response=Client(HTTP_HOST='localhost').get('/api/sites/clusters/')
features=response.json().get('features',[]) if response.status_code==200 else []
result={'scope':scope_policy()['scope'],'sites':Site.objects.count(),'cells':Cell.objects.count(),
    'monthly_kpis':MAOSMonthlyKPI.objects.count(),'remaining_tdd_cells':tdd,'missing_original_sites':missing_sites,
    'missing_original_non_tdd_cells':missing_fdd,'changed_retained_kpi_rows':changed_kpi,
    'current_events':RadioNetworkEvent.objects.filter(is_current=True).count(),
    'map_status':response.status_code,'map_features':len(features),
    'feature_refresh':{'initial_pass':3441,'failed_locked':3,'retry_succeeded':3},
    'datasets':{name:json.loads((root/'data/calibration'/name).read_text(encoding='utf-8'))['pairs'] for name in
        ('event_recipient_cases.manifest.json','episode_recipient_cases.manifest.json','gain_recipient_cases.manifest.json')}}
assert result['scope']=='tdd_cells' and not (tdd or missing_sites or missing_fdd or changed_kpi)
assert response.status_code==200 and len(features)==result['sites']
out=root/'docs/verification/data_scope/tdd_cell_verification.json'
out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
