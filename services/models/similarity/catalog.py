"""Shared similarity field metadata; identifiers and aliases are display-only."""
from .gower_distance import GowerDistance
from services.models.features.road_loader import ROAD_FIELDS, ROAD_LABELS
from services.models.features.maos_context import USER_CONTEXT_LABELS

PROFILE_FIELDS = (
    'pre_dl_traffic_gb_day', 'pre_active_users', 'pre_traffic_users',
    'pre_prb_util_dl_pct', 'pre_cqi_avg', 'pre_dl_throughput_kbps',
    'pre_dl_packet_delay_ms', 'pre_cell_availability_pct',
    'pre_traffic_trend_3m_pct', 'pre_prb_trend_3m_pct',
)
SIMILARITY_FIELDS = GowerDistance.NUMERIC_FEATURES + GowerDistance.CATEGORICAL_FEATURES
POPULATION_LABELS = {
    'population_density_1km_per_km2': ('Population density (1 km)', 'people/km²'),
    'population_tier1': ('Tier 1 population (0–2 km)', 'people'),
    'population_tier2': ('Tier 2 population (2–5 km)', 'people'),
}
CONTEXT_LABELS = {
    'avg_building_height_m':('Building height estimate (land-cover class prior)','m'),
    'total_prb_available':('Site LTE PRB capacity','PRBs'),
    'total_capacity_after_mbps':('Legacy Mbps capacity (use PRB capacity)','Mbps'),
    'neighbor_avg_antenna_height_m':('Mean neighbor absolute antenna elevation (2 km)','m ASL'),
    'z_antenna_m':('Antenna absolute elevation','m ASL'),
    'terrain_relief_class':('Terrain relief class (DEM slope; optional prior)',''),
    'avg_users':('Cluster active users - previous month (sum)','users'),
    'cluster_avg_users':('Cluster active users (display alias)','users'),
    'avg_traffic_dl_gb':('Cluster DL traffic - previous month','GB/month'),
    'avg_prb_util_pct':('Cluster DL PRB utilization - previous month','%'),
    'avg_cqi':('Cluster weighted CQI - previous month',''),
    'cluster_pre_dl_throughput_kbps':('Cluster DL throughput - previous month','kbit/s'),
    'cluster_pre_dl_packet_delay_ms':('Cluster latency - previous month','ms'),
    'cluster_pre_cell_availability_pct':('Cluster availability - previous month','%'),
    'pre_dl_traffic_gb_day':('Site DL traffic/day - preceding 3-month median','GB/day'),
    'pre_active_users':('Site active users - preceding 3-month median','users'),
    'pre_traffic_users':('Site traffic users - preceding 3-month median','users'),
}
DISPLAY_ONLY = {'cluster_id','cluster_avg_users'}
OPTIONAL = set(ROAD_FIELDS) | DISPLAY_ONLY | {'terrain_relief_class'}

