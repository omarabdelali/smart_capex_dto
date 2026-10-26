"""
Django admin configuration for Smart CAPEX models.
"""

from django.contrib import admin
from .models import RoadFeatures

@admin.register(RoadFeatures)
class RoadFeaturesAdmin(admin.ModelAdmin):
    list_display = ['site', 'road_km_total', 'dominant_road_class', 'coverage_status', 'buffer_m']
    list_filter = ['coverage_status', 'dominant_road_class']
from .models import (
    Site, Cell, ConfigurationFeatures, GeometricFeatures,
    ClutterFeatures, SpatialFeatures, ANPFeatures,
    PreLaunchKPI, ClusterFeatures, MAOSMonthlyKPI
)


@admin.register(Site)
class SiteAdmin(admin.ModelAdmin):
    list_display = ['site_id', 'site_name', 'latitude', 'longitude', 'is_launched', 'launch_date']
    list_filter = ['is_launched', 'launch_date']
    search_fields = ['site_id', 'site_name']
    ordering = ['site_name']


@admin.register(Cell)
class CellAdmin(admin.ModelAdmin):
    list_display = ['cell_id', 'cell_name', 'site', 'technology', 'frequency', 'azimuth', 'is_launched']
    list_filter = ['technology', 'is_launched', 'band']
    search_fields = ['cell_id', 'cell_name', 'site__site_name']
    ordering = ['cell_name']


@admin.register(ConfigurationFeatures)
class ConfigurationFeaturesAdmin(admin.ModelAdmin):
    list_display = ['site', 'event_type', 'tech_added', 'sector_count_after', 'antenna_height_m']
    list_filter = ['event_type', 'tech_added']
    search_fields = ['site__site_name']


@admin.register(GeometricFeatures)
class GeometricFeaturesAdmin(admin.ModelAdmin):
    list_display = ['site', 'z_antenna_m', 'terrain_slope_deg', 'terrain_roughness_m']
    search_fields = ['site__site_name']


@admin.register(ClutterFeatures)
class ClutterFeaturesAdmin(admin.ModelAdmin):
    list_display = ['site', 'dominant_clutter', 'clutter_entropy_2km', 'pct_building_area_1km']
    list_filter = ['dominant_clutter']
    search_fields = ['site__site_name']


@admin.register(SpatialFeatures)
class SpatialFeaturesAdmin(admin.ModelAdmin):
    list_display = ['site', 'dist_nearest_site_m', 'n_sites_1km', 'n_sites_2km', 'n_sites_3km']
    search_fields = ['site__site_name']


@admin.register(ANPFeatures)
class ANPFeaturesAdmin(admin.ModelAdmin):
    list_display = ['site', 'edge_score', 'n_tier1', 'n_tier2', 'max_empty_arc_deg', 'angular_uniformity']
    search_fields = ['site__site_name']
    ordering = ['-edge_score']


@admin.register(PreLaunchKPI)
class PreLaunchKPIAdmin(admin.ModelAdmin):
    list_display = ['site', 'avg_traffic_dl_gb', 'avg_users', 'avg_prb_util_pct']
    search_fields = ['site__site_name']


@admin.register(ClusterFeatures)
class ClusterFeaturesAdmin(admin.ModelAdmin):
    list_display = ['site', 'cluster_id', 'cluster_size', 'cluster_density_sites_per_km2']
    list_filter = ['cluster_id']
    search_fields = ['site__site_name']


@admin.register(MAOSMonthlyKPI)
class MAOSMonthlyKPIAdmin(admin.ModelAdmin):
    list_display = ['cell', 'month_date', 'traffic_user_avg', 'thrp_bits_dl', 'active_users_avg']
    list_filter = ['month_date']
    search_fields = ['cell__cell_name']
    ordering = ['-month_date']
