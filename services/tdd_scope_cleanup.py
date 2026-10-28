"""Restore the original inventory and apply the approved cell-only TDD scope."""
import json
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import pandas as pd
from django.conf import settings
from django.core.cache import cache
from django.db import connection, transaction
from core.models import Site, Cell, MAOSMonthlyKPI, RadioNetworkEvent, AnalysisEpisode, AnalysisEpisodeMember
from .data_scope import source_hash, tdd_cell
from .data_scope_cleanup import inside_workspace, curate_plan, curate_maos


def apply_tdd_cell_scope(backup_path, progress=print):
    root=Path(settings.BASE_DIR)
    backup=inside_workspace(root/backup_path)
    audit=json.loads((backup/'audit.json').read_text(encoding='utf-8'))
    plan=backup/'inputs'/audit['cell_plan']['path']
    frame=pd.read_excel(plan)
    frame.columns=frame.columns.str.strip().str.lower().str.replace(' ','_')
    names=set(frame.loc[frame['band'].map(tdd_cell),'cell_name'].astype(str).str.strip())
    original_db=backup/'database.sqlite3'
    with sqlite3.connect(str(original_db)) as db:
        names.update(row[0] for row in db.execute('select cell_name from cells where upper(trim(band)) = ?',('TDD',)))
    policy={'enabled':True,'scope':'tdd_cells','excluded_cell_names':sorted(names),
        'excluded_site_ids':[],'excluded_site_names':[],
        'source_backup':str(backup.relative_to(root)), 'updated_at':datetime.now(timezone.utc).isoformat()}
    prepared=[]
    for source in [audit['cell_plan'],*audit['source_reports']]:
        archive=inside_workspace(backup/'inputs'/source['path'])
        if source_hash(archive)!=source['sha256']:
            raise ValueError(f'Original source backup does not match audit: {archive}')
        target=inside_workspace(root/source['path'])
        temporary=inside_workspace(target.with_name(target.name+'.tdd-cells.tmp'))
        progress(f'Preparing cell-only filtered source: {target.name}')
        info=curate_plan(archive,temporary,policy) if target.suffix.lower()=='.xlsx' else curate_maos(archive,temporary,policy)
        prepared.append((target,temporary,info))
    # Install inputs before restoring the snapshot; all originals remain in backup.
    for target,temporary,info in prepared:
        temporary.replace(target)
        progress(f'Installed {target.name}: {info}')
    connection.close()
    database_path=inside_workspace(connection.settings_dict['NAME'])
    with sqlite3.connect(str(original_db)) as original,sqlite3.connect(str(database_path)) as target:
        original.backup(target)
    connection.close()
    (root/'config/data_scope.json').write_text(json.dumps(policy,indent=2),encoding='utf-8')
    with transaction.atomic():
        # All detections are derived from the cell inventory; regenerate them so
        # old event payloads cannot retain removed cell identities.
        members=AnalysisEpisodeMember.objects.all().delete()[0]
        episodes=AnalysisEpisode.objects.all().delete()[0]
        events=RadioNetworkEvent.objects.all().delete()[0]
        cells=list(Cell.objects.all().values_list('pk','cell_name','band','frequency','technology'))
        excluded=[pk for pk,name,band,frequency,tech in cells if name in names or tdd_cell(band,frequency,tech)]
        deleted,details=Cell.objects.filter(pk__in=excluded).delete()
    cache.clear()
    from services.models.similarity.profile_cache import cache_backend
    backend=cache_backend();inside_workspace(backend._dir);backend.clear()
    result={'version':'exclude-tdd-cells-v1','scope':'tdd_cells','backup':str(backup.relative_to(root)),
        'site_rows_retained':Site.objects.count(),'cell_rows_removed':len(excluded),'deleted_records':details,
        'deleted_derived_event_records':{'episode_members':members,'episodes':episodes,'events':events},
        'remaining_cells':Cell.objects.count(),'remaining_kpis':MAOSMonthlyKPI.objects.count(),
        'sources':[{**info,'path':str(target.relative_to(root))} for target,_,info in prepared],
        'rebuild_status':'pending'}
    path=backup/'tdd_cell_removal.json';path.write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result
