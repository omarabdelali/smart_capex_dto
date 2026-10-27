"""
Feature-related Django REST Framework serializers.
"""

from rest_framework import serializers
from django.db.models import Count, F, Q, Sum
from core.serializers.site_serializers import get_site_addition_data
from core.models import (
    GeometricFeatures,
    ClutterFeatures,
    SpatialFeatures,
    ANPFeatures,
    KPIFeatures,
    ConfigurationFeatures,
    ClusterFeatures,
    Site
)
from services.models.preprocessing.maos_aggregation import normalize_monthly_totals
from core.models import RoadFeatures
from core.models import UserContextFeatures
from services.models.features.maos_context import site_maos_payload


class UserContextFeaturesSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserContextFeatures
        exclude = ('id','site')


class RoadFeaturesSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoadFeatures
        exclude = ('id', 'site')


class GeometricFeaturesSerializer(serializers.ModelSerializer):
    """Serializer for geometric (DEM-based) features."""
    
    class Meta:
        model = GeometricFeatures
        fields = [
            'z_antenna_m',
            'terrain_slope_deg',
            'terrain_aspect_deg',
            'terrain_roughness_m', 'terrain_relief_class'
        ]


class ClutterFeaturesSerializer(serializers.ModelSerializer):
    """Serializer for clutter (land cover) features."""
    
    class Meta:
        model = ClutterFeatures
        fields = [
            'dominant_clutter',
            'clutter_entropy_2km',
            'pct_building_area_1km',
            'avg_building_height_m'
        ]


class SpatialFeaturesSerializer(serializers.ModelSerializer):
    """Serializer for spatial (neighbor-based) features."""
    
    class Meta:
        model = SpatialFeatures
        fields = [
            'dist_nearest_site_m',
            'n_sites_1km',
            'n_sites_2km',
            'n_sites_3km',
            'n_2g_sites_2km',
            'n_3g_sites_2km',
            'n_4g_sites_2km',
            'neighbor_avg_antenna_height_m'
        ]


class ANPFeaturesSerializer(serializers.ModelSerializer):
    """Serializer for Angular Neighborhood Profile features."""
    
    # Angular bins for polar chart visualization
    angular_bins = serializers.SerializerMethodField()
    
    class Meta:
        model = ANPFeatures
        fields = [
            'n_tier1', 'n_tier2', 't1_to_t2_ratio', 't1_nearest_m', 't2_nearest_m',
            'max_empty_arc_deg',
            'n_empty_bins',
            'dominant_sector_deg',
            'dominant_sector_count',
            'angular_uniformity',
            'edge_score',
            'bearing_stddev_deg',
            'avg_neighbor_dist_t1_m',
            'avg_neighbor_dist_t2_m',
            'coverage_asymmetry',
            'angular_bins'  # Formatted for Chart.js
        ]

    def get_angular_bins(self, obj):
        from services.models.features.neighborhood import angular_bins
        return angular_bins(obj.site)


class KPIFeaturesSerializer(serializers.ModelSerializer):
    """Serializer for persisted MAOS-derived pre-launch KPI features."""

    class Meta:
        model = KPIFeatures
        fields = [
            'coverage_ratio_pre', 'coverage_gap_pre', 'avg_prb_pre', 'avg_rrc_pre',
            'avg_throughput_pre', 'avg_latency_pre', 'dl_traffic_pre_gb_day',
            'traffic_density_mbb_pre', 'traffic_density_fwa_pre',
            'traffic_density_box_pre', 'traffic_ratio_pre', 'gap_score_pre'
        ]


class ConfigurationFeaturesSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConfigurationFeatures
        exclude = ('id', 'site', 'created_at', 'total_capacity_after_mbps')


class ClusterFeaturesSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClusterFeatures
        exclude = ('id', 'site', 'created_at')


class SiteWithFeaturesSerializer(serializers.ModelSerializer):
    """
    Comprehensive serializer for Site with all extracted features.
    
    Used for detailed site feature display in frontend popups.
    """
    
    # Nested feature serializers
    geometric = GeometricFeaturesSerializer(source='geometric_features', read_only=True)
    clutter = ClutterFeaturesSerializer(source='clutter_features', read_only=True)
    spatial = serializers.SerializerMethodField()
    anp = serializers.SerializerMethodField()
    kpi = serializers.SerializerMethodField()
    maos_monthly = serializers.SerializerMethodField()
    maos_cells = serializers.SerializerMethodField()
    maos_scopes = serializers.SerializerMethodField()
    user_context = UserContextFeaturesSerializer(source='user_context_features',read_only=True)
    configuration = serializers.SerializerMethodField()
    cluster_features = serializers.SerializerMethodField()
    cluster_prelaunch = serializers.SerializerMethodField()
    configuration_support = serializers.SerializerMethodField()
    population = serializers.SerializerMethodField()
    neighborhood = serializers.SerializerMethodField()
    roads = RoadFeaturesSerializer(source='road_features', read_only=True)
    
    # Cell info
    cell_count = serializers.SerializerMethodField()
    technologies = serializers.SerializerMethodField()
    added_cells = serializers.SerializerMethodField()
    cell_plan = serializers.SerializerMethodField()
    addition_events = serializers.SerializerMethodField()
    network_events = serializers.SerializerMethodField()
    matched_cells = serializers.SerializerMethodField()
    is_launched = serializers.SerializerMethodField()
    launch_date = serializers.SerializerMethodField()
    
    
    class Meta:
        model = Site
        fields = [
            'site_id',
            'site_name',
            'latitude',
            'longitude',
            'cluster_id', 'tier_scheme', 'canonical_site_id', 'neighborhood',
            'is_cluster_edge',
            'out_of_bounds',
            'is_launched',
            'launch_date',
            'cell_count',
            'technologies',
            'added_cells',
            'cell_plan',
            'addition_events',
            'network_events',
            'matched_cells',
            'geometric',
            'clutter',
            'spatial',
            'anp',
            'kpi',
            'maos_monthly',
            'maos_cells',
            'maos_scopes',
            'user_context',
            'configuration',
            'cluster_features',
            'cluster_prelaunch',
            'configuration_support',
            'population',
            'roads',
        ]
    
    def get_neighborhood(self,obj):
        from services.models.features.neighborhood import analysis_payload
        return analysis_payload(obj)[0]

    def get_spatial(self,obj):
        from services.models.features.neighborhood import popup_spatial
        return popup_spatial(obj)

    def get_anp(self,obj):
        from services.models.features.neighborhood import popup_anp
        return popup_anp(obj)

    def get_cell_count(self, obj):
        """Get number of cells at this site."""
        return sum(1 for _ in obj.cells.all())

    def get_population(self, obj):
        from services.models.features.population import population_features
        from services.models.features.neighborhood import scheme
        return population_features(obj.latitude,obj.longitude,tier_scheme=scheme(obj))
    
    def get_technologies(self, obj):
        """Get list of technologies at this site."""
        return sorted({cell.technology for cell in obj.cells.all()})

    def get_added_cells(self, obj):
        return get_site_addition_data(obj)['added_cells']

    def get_cell_plan(self, obj):
        """Project event labels onto the original cell-plan configuration rows."""
        additions = {
            item['cell_id']: item
            for item in get_site_addition_data(obj)['added_cells']
        }
        return [
            {
                'cell_id': cell.cell_id,
                'cell_name': cell.cell_name,
                'technology': cell.technology,
                'cgi': cell.cgi,
                'frequency_mhz': cell.frequency,
                'band': cell.band,
                'bandwidth_mhz': cell.bandwidth_mhz,
                'azimuth_deg': cell.azimuth,
                'antenna_height_m': cell.antenna_height_m,
                'cluster_id': obj.cluster_id,
                'is_added': cell.cell_id in additions,
                'event_type': additions.get(cell.cell_id, {}).get('event_type'),
                'launch_date': additions.get(cell.cell_id, {}).get('launch_date'),
                'effective_activation_month': cell.effective_activation_month,
                'activation_evidence': cell.activation_evidence,
                'group_effective_date': additions.get(cell.cell_id, {}).get('group_effective_date'),
            }
            for cell in obj.cells.all()
        ]

    def get_network_events(self, obj):
        return get_site_addition_data(obj)['network_events']

    def get_addition_events(self, obj):
        return get_site_addition_data(obj)['events']

    def get_is_launched(self, obj):
        return bool(get_site_addition_data(obj)['events'])

    def get_launch_date(self, obj):
        events = get_site_addition_data(obj)['events']
        return min((event['launch_date'] for event in events), default=None)

    def get_matched_cells(self, obj):
        term = (self.context.get('search_term') or '').casefold()
        if not term:
            return []
        return [
            {'cell_name': cell.cell_name, 'technology': cell.technology}
            for cell in obj.cells.all()
            if term in cell.cell_name.casefold()
        ]

    def get_kpi(self, obj):
        """Return persisted pre-launch KPI values when available."""
        try:
            return KPIFeaturesSerializer(obj.kpi_features).data
        except KPIFeatures.DoesNotExist:
            return None

    def get_maos_monthly(self, obj):
        return site_maos_payload(obj, get_site_addition_data(obj)['added_cells'])['scopes']['site']['records']

    def get_maos_cells(self, obj):
        return site_maos_payload(obj, get_site_addition_data(obj)['added_cells'])['cells']

    def get_maos_scopes(self, obj):
        return site_maos_payload(obj, get_site_addition_data(obj)['added_cells'])['scopes']

    def get_configuration(self, obj):
        try:
            return ConfigurationFeaturesSerializer(obj.config_features).data
        except ConfigurationFeatures.DoesNotExist:
            return None

    def get_cluster_features(self, obj):
        from services.models.features.approved_context import popup_context
        return popup_context(obj)['cluster_context']

    def get_cluster_prelaunch(self, obj):
        from services.models.features.approved_context import popup_context
        return popup_context(obj)['cluster_prelaunch']

    def get_configuration_support(self, obj):
        from services.models.features.approved_context import popup_context
        return popup_context(obj)['configuration_support']
