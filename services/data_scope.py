"""Source-audited C-band physical-site exclusions and ingestion safeguards."""
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path
import re
from django.conf import settings
from core.models import Site,Cell

POLICY_FILE='config/data_scope.json'
CBAND_LABELS={'42','43','B42','B43','BAND42','BAND43','LTE42','LTE43','CBAND','TDDCBAND','L3500','L3600'}
STANDARD_SOURCE='https://www.etsi.org/deliver/etsi_ts/136100_136199/136101/17.16.00_60/ts_136101v171600p.pdf'


def normalized(value):
    if value is None:
        return ''
    text=str(value).strip().upper()
    if text.endswith('.0'):
        text=text[:-2]
    return re.sub(r'[^A-Z0-9]','',text)


def explicit_cband(value):
    return normalized(value) in CBAND_LABELS


def tdd_cell(band,frequency=None,technology='4G'):
    return normalized(band)=='TDD' or explicit_cband(band)


def plan_cband(band,frequency=None,technology='4G'):
    if explicit_cband(band):
        return True
    try:
        # The existing cell-plan frequency column stores LTE EARFCN, not MHz.
        return normalized(technology) in ('4G','LTE') and normalized(band)=='TDD' and 41590<=float(frequency)<=45589
    except (ValueError,TypeError):
        return False


def scope_policy():
    path=Path(settings.BASE_DIR)/POLICY_FILE
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'enabled':False}


def filter_cellplan_frame(frame,policy=None):
    """Reject the whole co-located site group before any plan rows are inserted."""
    import numpy as np
    import pandas as pd
    from sklearn.cluster import DBSCAN
    p=policy if policy is not None else scope_policy()
    if not p.get('enabled'):
        return frame,{'excluded_rows':0,'excluded_source_sites':0}
    if p.get('scope')=='tdd_cells':
        names=set(p.get('excluded_cell_names',[]))
        mask=frame['band'].map(tdd_cell) | frame['cell_name'].astype(str).str.strip().isin(names)
        return frame.loc[~mask].copy(),{'excluded_rows':int(mask.sum()),'excluded_source_sites':0}
    ids=frame['site_id'].astype(str).str.replace(r'\.0$','',regex=True)
    names=frame['site_name'].astype(str).str.strip()
    banned=ids.isin(p.get('excluded_site_ids',[])) | names.isin(p.get('excluded_site_names',[]))
    direct=np.array([plan_cband(b,f,t) for b,f,t in zip(frame['band'],frame['frequency'],frame['technology'])])
    banned |= direct
    blocked=set(ids[banned])
    if {'latitude','longitude'}<=set(frame):
        rows=frame.assign(_scope_id=ids).groupby('_scope_id',sort=False).first()
        numeric=rows[['latitude','longitude']].apply(pd.to_numeric,errors='coerce')
        valid=np.isfinite(numeric).all(axis=1)
        coords=numeric.loc[valid]
        if len(coords):
            labels=DBSCAN(eps=50/6371000,min_samples=1,metric='haversine').fit_predict(np.radians(coords))
            infected={label for key,label in zip(coords.index,labels) if key in blocked}
            blocked.update(key for key,label in zip(coords.index,labels) if label in infected)
    keep=~ids.isin(blocked)
    return frame.loc[keep].copy(),{'excluded_rows':int((~keep).sum()),'excluded_source_sites':len(blocked),'excluded_site_ids':sorted(blocked)}


def filter_maos_chunk(chunk,policy=None):
    p=policy if policy is not None else scope_policy()
    if not p.get('enabled'):
        return chunk,0
    band=chunk.get('Frequency band')
    mask=band.map(explicit_cband) if band is not None else chunk['Cell Name'].map(lambda _:False)
    mask |= chunk['Cell Name'].astype(str).str.strip().isin(p.get('excluded_cell_names',[]))
    if p.get('scope')=='tdd_cells':
        if 'Cell FDD TDD Indication' in chunk:
            mask |= chunk['Cell FDD TDD Indication'].map(lambda value:normalized(value) in ('TDD','CELLTDD'))
        return chunk.loc[~mask].copy(),int(mask.sum())
    if 'eNodeB Name' in chunk:
        names=chunk['eNodeB Name'].astype(str).str.strip()
        mask |= names.isin(p.get('excluded_site_names',[])) | names.str.rsplit('_',n=1).str[0].isin(p.get('excluded_site_names',[]))
    return chunk.loc[~mask].copy(),int(mask.sum())


def source_hash(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(4*1024*1024),b''):
            digest.update(chunk)
    return digest.hexdigest()


def row_excluded(site_id=None,site_name=None,band=None,cell_name=None,policy=None):
    p=policy if policy is not None else scope_policy()
    if not p.get('enabled'):
        return False
    return (str(site_id) in p.get('excluded_site_ids',[]) or str(site_name) in p.get('excluded_site_names',[])
        or str(cell_name) in p.get('excluded_cell_names',[]) or explicit_cband(band))


def audit_cband_sources(output):
    """Inspect both source columns; never treat channel numbers as MHz."""
    import pandas as pd
    sites=list(Site.objects.values('id','site_id','site_name','canonical_site_id'))
    cells=list(Cell.objects.values('id','site_id','cell_id','cell_name','band','frequency','technology'))
    by_pk={s['id']:s for s in sites}
    by_name=defaultdict(set)
    for s in sites:
        by_name[s['site_name']].add(s['id'])
    by_cell=defaultdict(list)
    for c in cells:
        by_cell[c['cell_name']].append(c)
    evidence=defaultdict(set);source_cells=set();frequencies=defaultdict(set);reports=[];unmapped=set()
    for path in sorted((Path(settings.BASE_DIR)/'data/maos').glob('**/*.csv')):
        report={'path':str(path.relative_to(settings.BASE_DIR)),'rows':0,'band_duplex_counts':Counter(),'cband_rows':0}
        columns={'Frequency band','Cell FDD TDD Indication','Cell Name','eNodeB Name','Downlink EARFCN'}
        for chunk in pd.read_csv(path,skiprows=6,usecols=lambda c:c.strip() in columns,dtype=str,
                                 keep_default_na=False,chunksize=100000):
            chunk.columns=chunk.columns.str.strip()
            report['rows']+=len(chunk)
            for (band,duplex),count in chunk.groupby(['Frequency band','Cell FDD TDD Indication'],dropna=False).size().items():
                report['band_duplex_counts'][f'{band}|{duplex}']+=int(count)
            selected=chunk[chunk['Frequency band'].map(explicit_cband)]
            report['cband_rows']+=len(selected)
            for row in selected.drop_duplicates().to_dict('records'):
                name=row.get('Cell Name','').strip();node=row.get('eNodeB Name','').strip()
                source_cells.add(name)
                if normalized(row.get('Cell FDD TDD Indication')) in ('CELLTDD','TDD'):
                    try:
                        frequencies[float(row['Downlink EARFCN'])].add(normalized(row['Frequency band']))
                    except (ValueError,KeyError):
                        pass
                matches={c['site_id'] for c in by_cell.get(name,[])}
                # This identifies a site, not a guessed cell-level KPI crosswalk.
                node_root=node.rsplit('_',1)[0]
                if not matches:
                    named=set(by_name.get(node,[])) | set(by_name.get(node_root,[]))
                    identities={by_pk[pk]['canonical_site_id'] or by_pk[pk]['site_id'] for pk in named}
                    if len(identities)==1:
                        matches=named
                if not matches:
                    unmapped.add((name,node,row['Frequency band']))
                for pk in matches:
                    evidence[pk].add(f"MAOS:{row['Frequency band']}:{row.get('Cell FDD TDD Indication','')}")
        report['band_duplex_counts']=dict(report['band_duplex_counts'])
        report['sha256']=source_hash(path)
        reports.append(report)
    plan=Path(settings.CELLPLAN_DIR)/'Cell_Plan_Data_21102026.xlsx'
    frame=pd.read_excel(plan,usecols=lambda c:str(c).strip().lower().replace(' ','_') in {'site_id','site_name','cell_name','band','frequency','technology','latitude','longitude'})
    frame.columns=frame.columns.str.strip().str.lower().str.replace(' ','_')
    plan_bands={str(k):int(v) for k,v in frame['band'].value_counts(dropna=False).items()}
    for c in cells:
        matched=plan_cband(c['band'],c['frequency'],c['technology'])
        if c['technology']=='4G' and normalized(c['band'])=='TDD':
            matched |= bool(frequencies.get(c['frequency']))
        if matched:
            evidence[c['site_id']].add(f"cell_plan:{c['band']}:channel={c['frequency']}")
    # Apply the same physical closure to the complete source plan, including
    # records that were never loaded into the database. A source-only C-band
    # cell may share a physical location with an active database site.
    seed_ids={by_pk[pk]['site_id'] for pk in evidence}
    while True:
        seed_pks={s['id'] for s in sites if s['site_id'] in seed_ids}
        safe_names={s['site_name'] for s in sites if set(by_name[s['site_name']])<=seed_pks}
        _, source_scope=filter_cellplan_frame(frame, {'enabled':True,'excluded_site_ids':list(seed_ids),
            'excluded_site_names':list(safe_names)})
        source_ids=set(source_scope['excluded_site_ids'])
        identities={s['canonical_site_id'] or s['site_id'] for s in sites if s['site_id'] in source_ids}
        expanded=seed_ids | {s['site_id'] for s in sites if (s['canonical_site_id'] or s['site_id']) in identities}
        if expanded==seed_ids:
            break
        seed_ids=expanded
    for site in sites:
        if site['site_id'] in seed_ids:
            evidence[site['id']].add('co-located with C-band source-plan site')
    canonical={by_pk[pk]['canonical_site_id'] or by_pk[pk]['site_id'] for pk in evidence}
    target=[s for s in sites if (s['canonical_site_id'] or s['site_id']) in canonical]
    target_pks={s['id'] for s in target}
    target_cellnames={c['cell_name'] for c in cells if c['site_id'] in target_pks}
    target_ids={s['site_id'] for s in target}
    target_names={s['site_name'] for s in target if set(by_name[s['site_name']])<=target_pks}
    for s in target:
        s['evidence']=sorted(evidence.get(s['id'],{'co-located alias of an excluded physical site'}))
    impact={}
    from django.apps import apps
    from core.models import RadioNetworkEvent,AnalysisEpisode,AnalysisEpisodeMember,MAOSMonthlyKPI
    for model in apps.get_app_config('core').get_models():
        field=next((f for f in model._meta.fields if f.name=='site' and getattr(f.remote_field,'model',None) is Site),None)
        if field:
            impact[model.__name__]=model.objects.filter(site_id__in=target_pks).count()
    impact['Cell']=Cell.objects.filter(site_id__in=target_pks).count()
    impact['MAOSMonthlyKPI']=MAOSMonthlyKPI.objects.filter(cell__site_id__in=target_pks).count()
    episode_ids=set(AnalysisEpisode.objects.filter(site_id__in=target_pks).values_list('pk',flat=True))
    impact['AnalysisEpisodeMember']=AnalysisEpisodeMember.objects.filter(episode_id__in=episode_ids).count()
    result={'version':'exclude-cband-physical-sites-v1','scope':'whole_physical_site','standard_source':STANDARD_SOURCE,'source_reports':reports,
        'cell_plan':{'path':str(plan.relative_to(settings.BASE_DIR)),'sha256':source_hash(plan),'bands':plan_bands},
        'source_cband_earfcns':{str(k):sorted(v) for k,v in sorted(frequencies.items())},
        'physical_sites_to_remove':len(canonical),'site_rows_to_remove':len(target),'site_rows_to_keep':len(sites)-len(target),
        'mixed_source_site_rows':sum(any(c['band']=='TDD' or explicit_cband(c['band']) for c in cells if c['site_id']==s['id']) and any(c['band']!='TDD' and not explicit_cband(c['band']) for c in cells if c['site_id']==s['id']) for s in target),
        'sites':target,'impact':impact,'unmapped_cband_source_cells':sorted(unmapped),
        'policy':{'enabled':True,'scope':'whole_physical_site','excluded_site_ids':sorted(target_ids),
            'excluded_site_names':sorted(target_names),'excluded_cell_names':sorted(target_cellnames|source_cells),
            'cband_earfcns':sorted(frequencies),'source_reports':[r['path'] for r in reports]}}
    path=Path(output);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,indent=2),encoding='utf-8')
    return {k:v for k,v in result.items() if k not in ('sites','policy','unmapped_cband_source_cells')}
