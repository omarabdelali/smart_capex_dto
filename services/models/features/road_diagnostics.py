"""Read-only redundancy diagnostics; no unsupported claims of predictive gain."""
from datetime import date
import json
from pathlib import Path

import numpy as np
import pandas as pd
from core.models import RoadFeatures, Site, Cell
from .road_loader import ROAD_NUMERIC, ROOT


def road_diagnostics():
    context = {
        'pct_building_area_1km':'site__clutter_features__pct_building_area_1km',
        'dist_nearest_site_m':'site__spatial_features__dist_nearest_site_m',
        'n_sites_2km':'site__spatial_features__n_sites_2km',
        'clutter_entropy_2km':'site__clutter_features__clutter_entropy_2km',
    }
    rows = list(RoadFeatures.objects.values(*ROAD_NUMERIC,*context.values()))
    frame = pd.DataFrame(rows,columns=[*ROAD_NUMERIC,*context.values()]).rename(columns={v:k for k,v in context.items()})
    correlations = []
    for road in ROAD_NUMERIC:
        for feature in context:
            pair = frame[[road,feature]].dropna()
            usable = len(pair)>2 and pair[road].nunique()>1 and pair[feature].nunique()>1
            correlations.append({'road':road,'context':feature,'n':len(pair),
                                 'pearson':float(pair.corr().iloc[0,1]) if usable else None,
                                 'spearman':float(pair.corr(method='spearman').iloc[0,1]) if usable else None})
    complete = frame.dropna()
    vif = []
    for feature in complete.columns:
        target = complete[feature].to_numpy(dtype=float)
        others = complete.drop(columns=feature).to_numpy(dtype=float)
        total = np.sum((target-target.mean())**2) if len(target) else 0
        if total <= 0:
            vif.append({'feature':feature,'vif':None,'status':'no_variation_or_no_complete_rows'})
            continue
        # Standardization improves conditioning; no missing values are imputed.
        std = others.std(axis=0)
        others = (others[:,std>0]-others[:,std>0].mean(axis=0))/std[std>0]
        design = np.column_stack([np.ones(len(target)),others])
        residual = np.sum((target-design@np.linalg.lstsq(design,target,rcond=None)[0])**2)
        ratio = residual/total
        vif.append({'feature':feature,'vif':float(1/ratio) if ratio>1e-10 else None,
                    'status':'finite' if ratio>1e-10 else 'perfect_collinearity'})
    return {
        'date':date.today().isoformat(),'rows':len(frame),'vif_complete_rows':len(complete),
        'correlations':correlations,'vif':vif,
        'recommendation':'Keep roads optional. Weighted length and weighted density are algebraically redundant at a fixed buffer; prefer selecting density alone. Predictive value is not established.',
        'ablation':{
            'status':'blocked_for_time_valid_accuracy_claims',
            'reason':'The local OSM snapshot is dated 2026-10-22 and historical road snapshots are absent. This snapshot postdates the historical launch pool; assigning these roads to earlier events would leak later geography. Current-context retrieval is exploratory. No KPI errors are fabricated.',
            'whole_site_launches':Site.objects.filter(is_launched=True,launch_date__isnull=False).count(),
            'cell_addition_site_months':Cell.objects.filter(is_launched=True,launch_date__isnull=False).values('site_id','launch_date').distinct().count(),
            'conditions':['without_roads/equal_per_feature','with_roads/equal_per_feature','without_roads/equal_per_group','with_roads/equal_per_group'],
            'kpi_errors':{metric:None for metric in ('downlink_traffic','CQI','active_users','throughput','latency')},
        },
    }


def save_road_diagnostics():
    result = road_diagnostics()
    path = ROOT/'docs/verification/roads/diagnostics.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8')
    return str(path)
