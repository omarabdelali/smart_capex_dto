"""Independent current-snapshot and per-event virtual membership reconciliation."""
from collections import defaultdict,Counter
from datetime import date
from pathlib import Path
import json
import math
from statistics import median

from django.db.models import Max,Sum
from core.models import Site,MAOSMonthlyKPI,RadioNetworkEvent
from services.utils.geo_utils import haversine,compute_bearing
from services.models.features.neighborhood import neighborhood


def month_offset(month,delta):
    y,m=divmod(month.year*12+month.month-1+delta,12)
    return date(y,m+1,1)


def smaller_id(value):
    return (0,int(value)) if value.isdigit() else (1,value)


def run():
    sites=list(Site.objects.all())
    canonical={s.site_id:s for s in sites if s.site_id==s.canonical_site_id}
    raw_to_canonical={s.site_id:s.canonical_site_id for s in sites}
    groups=defaultdict(list)
    for site in sites:
        assert site.canonical_site_id in canonical
        groups[site.canonical_site_id].append(site)
        assert site.cluster_id==canonical[site.canonical_site_id].cluster_id
        assert site.tier_scheme==('extended' if site.cluster_id==-1 else 'standard')
    latest=MAOSMonthlyKPI.objects.aggregate(value=Max('month_date'))['value']
    cutoff=month_offset(latest,1)
    positive=defaultdict(set)
    for raw,month in MAOSMonthlyKPI.objects.filter(cell__technology='4G',thrp_bits_dl__gt=0).values_list('cell__site__site_id','month_date').distinct():
        positive[month].add(raw_to_canonical[raw])
    monthly={row['cell__site__site_id']:row['bits'] for row in MAOSMonthlyKPI.objects.filter(month_date=latest).values('cell__site__site_id').annotate(bits=Sum('thrp_bits_dl'))}
    eligible_cache={}

    def eligible(at):
        if at not in eligible_cache:
            keys=set().union(*(positive[month_offset(at,i)] for i in (-3,-2,-1)))
            eligible_cache[at]={key for key in keys if not any(s.launch_date and s.launch_date.replace(day=1)==at for s in groups[key])}
        return eligible_cache[at]

    def reference(origin,at):
        bins={};all_members=[]
        for key in eligible(at):
            if key==origin.canonical_site_id:
                continue
            peer=canonical[key]
            distance=haversine(origin.latitude,origin.longitude,peer.latitude,peer.longitude)
            if not 50<=distance<10000:
                continue
            bearing=round(compute_bearing(origin.latitude,origin.longitude,peer.latitude,peer.longitude)%360,6)%360
            bin_id=math.floor(bearing/30)%12
            order=(math.floor(distance+.5),smaller_id(key))
            candidate=(key,distance,bearing)
            all_members.append(candidate)
            if bin_id not in bins or order<bins[bin_id][0]:
                bins[bin_id]=(order,candidate)
        return {b:v[1] for b,v in bins.items()},all_members

    def total(members):
        values=[]
        for key,_,_ in members:
            measured=[monthly[s.site_id] for s in groups[key] if monthly.get(s.site_id) is not None]
            if not measured:
                return None
            values.append(sum(measured)/8e9)
        return sum(values) if values else None

    def close(actual,expected):
        assert (actual is None and expected is None) or (actual is not None and expected is not None and math.isclose(actual,expected,rel_tol=1e-10,abs_tol=1e-6)),(actual,expected)

    supports=Counter();checked=0
    for site in sites:
        assert site.vis_snapshot_kind=='current' and site.vis_snapshot_cutoff==cutoff
        if site.cluster_id!=-1:
            assert site.vis_members==[] and site.vis_n_members is None and site.vis_sampled_traffic_gb is None
            continue
        expected,all_members=reference(site,cutoff)
        actual={m['bin']:m for m in site.vis_members}
        assert {b:m['site_id'] for b,m in actual.items()}=={b:m[0] for b,m in expected.items()},site.site_id
        assert len(actual)==site.vis_n_members==site.vis_n_bins_filled and len(actual)<=12
        assert len({m['site_id'] for m in actual.values()})==len(actual)
        for bin_id,member in actual.items():
            close(member['distance_m'],expected[bin_id][1]);close(member['bearing_deg'],expected[bin_id][2])
            assert member['tier']==('tier1' if member['distance_m']<5000 else 'tier2')
        sample=total(expected.values())
        close(site.vis_sampled_traffic_gb,sample)
        close(site.vis_mean_traffic_per_member_gb,sample/len(actual) if sample is not None else None)
        close(site.traffic_all_sites_within_R,total(all_members))
        close(site.vis_median_dist_m,median(m[1] for m in expected.values()) if expected else None)
        close(site.vis_max_dist_m,max((m[1] for m in expected.values()),default=None))
        assert site.support_level==('isolated' if not actual else 'low' if len(actual)<=2 else 'ok')
        if site.site_id==site.canonical_site_id:
            supports[site.support_level]+=1
        checked+=1
    events=RadioNetworkEvent.objects.filter(is_current=True,site__cluster_id=-1).select_related('site')
    cache={};event_count=0
    for event in events:
        expected,_=reference(event.site,event.effective_date)
        actual=neighborhood(event.site,event.effective_date,cache)
        assert {m['bin']:m['site_id'] for m in actual['vis_members']}=={b:m[0] for b,m in expected.items()}
        assert actual['scopes']['cluster']==[] and actual['cluster_id']==-1
        event_count+=1
    report={'date':'2026-10-27','site_rows':len(sites),'canonical_locations':len(canonical),
        'noise_snapshot_rows_checked':checked,'noise_locations':sum(s.cluster_id==-1 for s in canonical.values()),
        'reassigned_noise_rows':sum(s.original_cluster_id==-1 and s.cluster_id!=-1 for s in sites),
        'support_by_noise_location':dict(supports),'event_cutoffs_checked':event_count,
        'cutoff':cutoff.isoformat(),'mismatches':0,'checks':['canonical labels and tier schemes',
            'current and event nearest-per-bin reference membership','radius/bearing/tie rules',
            'sample and complete traffic totals','NULL and true zero','stored snapshot provenance']}
    path=Path('docs/verification/noise_virtual_clusters/validation.json')
    path.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


run()
