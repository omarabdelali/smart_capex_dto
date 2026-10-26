"""Independent raw-data checks for the user-approved context formulas."""
import json
from datetime import date
from pathlib import Path
from django.db.models import Sum, Q
from core.models import Site, Cell, MAOSMonthlyKPI, ConfigurationFeatures, GeometricFeatures, SpatialFeatures
from services.models.similarity.feature_vector import build_site_similarity_vector
from services.models.features.approved_context import ground_elevation
from services.models.preprocessing.network_events import bandwidth_from_prb

site=Site.objects.prefetch_related('cells','network_events').select_related('clutter_features').get(site_id='6306')
cutoff=date(2023,12,1)
vector=build_site_similarity_vector(site)
active=list(MAOSMonthlyKPI.objects.filter(cell__site=site,month_date__lte=cutoff,thrp_bits_dl__gt=0)
            .values_list('cell_id',flat=True).distinct())
cells=list(Cell.objects.filter(pk__in=active))
sectors={round((cell.azimuth%360)/5)%72 for cell in cells}
assert vector['sector_count_after']==len(sectors)
assert vector['cells_per_sector_after']==len(cells)/len(sectors)
latest={}
for pk,prbs in MAOSMonthlyKPI.objects.filter(cell_id__in=active,month_date__lte=cutoff,
        prb_dl_available__gte=0).order_by('month_date').values_list('cell_id','prb_dl_available'):
    latest[pk]=prbs
assert abs(vector['total_prb_available']-sum(latest.values()))<1e-8
bandwidths=[bandwidth_from_prb(latest.get(cell.pk)) for cell in cells]
expected_bandwidth=sum(bandwidths) if all(bw is not None for bw in bandwidths) else None
assert vector['total_bw_after_mhz']==expected_bandwidth
members=Site.objects.filter(cluster_id=site.cluster_id) if site.cluster_id!=-1 else Site.objects.filter(pk=site.pk)
rows=MAOSMonthlyKPI.objects.filter(cell__site__in=members,month_date=date(2023,11,1))
prb_pair=Q(prb_dl_used_avg__isnull=False,prb_dl_available__gt=0)
totals=rows.aggregate(users=Sum('active_users_avg'),traffic=Sum('thrp_bits_dl'),
    used=Sum('prb_dl_used_avg',filter=prb_pair),available=Sum('prb_dl_available',filter=prb_pair))
assert abs(vector['avg_users']-totals['users'])<1e-9
assert abs(vector['avg_traffic_dl_gb']-totals['traffic']/8e9)<1e-9
assert abs(vector['avg_prb_util_pct']-100*totals['used']/totals['available'])<1e-9
assert vector['cluster_id']==site.cluster_id
ground=ground_elevation(site.latitude,site.longitude)
assert abs(vector['z_antenna_m']-(ground+site.clutter_features.avg_building_height_m+25))<1e-8
assert vector['population_tier1']>0 and vector['population_tier2']>0
report={'site_id':site.site_id,'event_date':cutoff.isoformat(),'mismatches':0,
    'values':{key:vector.get(key) for key in ('sector_count_after','cells_per_sector_after','antenna_height_m',
        'total_prb_available','total_bw_after_mhz','z_antenna_m','neighbor_avg_antenna_height_m',
        'terrain_relief_class','dominant_clutter','population_tier1','population_tier2','avg_users',
        'avg_traffic_dl_gb','avg_prb_util_pct','avg_cqi','cluster_id')},
    'configuration_support':vector['post_event_configuration_support'],
    'cluster_support':vector['cluster_prelaunch_support'],
    'persisted_counts':{'prb_capacity':ConfigurationFeatures.objects.filter(total_prb_available__isnull=False).count(),
        'bandwidth':ConfigurationFeatures.objects.filter(total_bw_after_mhz__isnull=False).count(),
        'sectors':ConfigurationFeatures.objects.filter(sector_count_after__isnull=False).count(),
        'terrain_relief':GeometricFeatures.objects.filter(terrain_relief_class__isnull=False).count(),
        'neighbor_absolute_elevation':SpatialFeatures.objects.filter(neighbor_avg_antenna_height_m__isnull=False).count()}}
output=Path('docs/verification/approved_context')
output.mkdir(parents=True,exist_ok=True)
(output/'data-audit.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
