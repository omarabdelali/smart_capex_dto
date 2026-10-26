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
            'terrain_roughness_m'
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
        from services.utils.geo_utils import compute_bearing, haversine

        origin_lat = obj.site.latitude
        origin_lon = obj.site.longitude
        bins = [0] * 12
        neighbor_coords = Site.objects.exclude(pk=obj.site_id).values_list('latitude', 'longitude')
        for latitude, longitude in neighbor_coords:
            if haversine(origin_lat, origin_lon, latitude, longitude) <= 5000:
                bearing = compute_bearing(origin_lat, origin_lon, latitude, longitude)
                bins[int(bearing // 30) % 12] += 1
        return bins


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
        exclude = ('id', 'site', 'created_at')


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
    spatial = SpatialFeaturesSerializer(source='spatial_features', read_only=True)
    anp = ANPFeaturesSerializer(source='anp_features', read_only=True)
    kpi = serializers.SerializerMethodField()
    maos_monthly = serializers.SerializerMethodField()
    maos_cells = serializers.SerializerMethodField()
    configuration = serializers.SerializerMethodField()
    cluster_features = serializers.SerializerMethodField()
    population = serializers.SerializerMethodField()
    roads = RoadFeaturesSerializer(source='road_features', read_only=True)
    
    # Cell info
    cell_count = serializers.SerializerMethodField()
    technologies = serializers.SerializerMethodField()
    added_cells = serializers.SerializerMethodField()
    cell_plan = serializers.SerializerMethodField()
    addition_events = serializers.SerializerMethodField()
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
            'cluster_id',
            'is_cluster_edge',
            'out_of_bounds',
            'is_launched',
            'launch_date',
            'cell_count',
            'technologies',
            'added_cells',
            'cell_plan',
            'addition_events',
            'matched_cells',
            'geometric',
            'clutter',
            'spatial',
            'anp',
            'kpi',
            'maos_monthly',
            'maos_cells',
            'configuration',
            'cluster_features',
            'population',
            'roads',
        ]
    
    def get_cell_count(self, obj):
        """Get number of cells at this site."""
        return sum(1 for _ in obj.cells.all())

    def get_population(self, obj):
        from services.models.features.population import population_features
        return population_features(obj.latitude, obj.longitude)
    
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
                'is_added': cell.cell_id in additions,
                'event_type': additions.get(cell.cell_id, {}).get('event_type'),
                'launch_date': additions.get(cell.cell_id, {}).get('launch_date'),
            }
            for cell in obj.cells.all()
        ]

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
        """Aggregate imported cell counters into a site-level monthly series."""
        from core.models import MAOSMonthlyKPI
        rows = MAOSMonthlyKPI.objects.filter(cell__site=obj).values('month_date').annotate(
            traffic_users=Sum('traffic_user_avg'), active_users=Sum('active_users_avg'),
            traffic_bits=Sum('thrp_bits_dl'),
            dl_bits=Sum('thrp_bits_dl', filter=Q(thrp_time_dl_ms__isnull=False, thrp_bits_dl_last_tti__isnull=False, thrp_bits_dl__gte=F('thrp_bits_dl_last_tti'))),
            dl_last_tti_bits=Sum('thrp_bits_dl_last_tti', filter=Q(thrp_time_dl_ms__isnull=False, thrp_bits_dl__gte=F('thrp_bits_dl_last_tti'))),
            dl_time_ms=Sum('thrp_time_dl_ms', filter=Q(thrp_time_dl_ms__isnull=False, thrp_bits_dl_last_tti__isnull=False, thrp_bits_dl__gte=F('thrp_bits_dl_last_tti'))),
            prb_used=Sum('prb_dl_used_avg', filter=Q(prb_dl_used_avg__isnull=False, prb_dl_available__gt=0)),
            prb_available=Sum('prb_dl_available', filter=Q(prb_dl_used_avg__isnull=False, prb_dl_available__gt=0)),
            delay_time_ms=Sum('dl_packet_delay_time_ms', filter=Q(dl_packet_delay_time_ms__isnull=False, dl_packet_delay_packets__gt=0)),
            delay_packets=Sum('dl_packet_delay_packets', filter=Q(dl_packet_delay_time_ms__isnull=False, dl_packet_delay_packets__gt=0)),
            unavailable_s=Sum('cell_unavail_duration_s', filter=Q(cell_unavail_duration_s__isnull=False, observation_duration_s__gt=0)),
            observation_s=Sum('observation_duration_s', filter=Q(cell_unavail_duration_s__isnull=False, observation_duration_s__gt=0)),
            cqi_weighted_total=Sum('cqi_weighted_sum', filter=Q(cqi_weighted_sum__isnull=False, cqi_sample_count__gt=0)),
            cqi_sample_count=Sum('cqi_sample_count', filter=Q(cqi_weighted_sum__isnull=False, cqi_sample_count__gt=0)),
            reporting_cells=Count('cell_id', distinct=True),
        ).order_by('month_date')
        return [
            {'month': row['month_date'].strftime('%Y-%m'), **normalize_monthly_totals(row)}
            for row in rows
        ]

    def get_maos_cells(self, obj):
        """Return monthly KPI series per cell so added sectors can be inspected."""
        from core.models import MAOSMonthlyKPI
        added_by_name = {item['cell_name']: item for item in get_site_addition_data(obj)['added_cells']}
        rows = MAOSMonthlyKPI.objects.filter(cell__site=obj).values(
            'cell__cell_name', 'cell__technology', 'month_date', 'traffic_user_avg',
            'active_users_avg', 'prb_util_dl_pct', 'prb_util_ul_pct', 'rrc_conn_avg',
            'cqi_avg', 'rsrp_avg_dbm', 'thrp_bits_dl', 'thrp_bits_ul', 'dl_throughput_kbps',
            'dl_packet_delay_ms', 'cell_availability_pct',
        ).order_by('cell__cell_name', 'month_date')
        series = {}
        for row in rows.iterator(chunk_size=2_000):
            name = row['cell__cell_name']
            entry = series.setdefault(name, {
                'cell_name': name,
                'technology': row['cell__technology'],
                'is_added': name in added_by_name,
                'launch_date': added_by_name.get(name, {}).get('launch_date'),
                'records': [],
            })
            entry['records'].append({
                'month': row['month_date'].strftime('%Y-%m'),
                'traffic_user_avg': row['traffic_user_avg'],
                'active_users_avg': row['active_users_avg'],
                'prb_util_dl_pct': row['prb_util_dl_pct'],
                'prb_util_ul_pct': row['prb_util_ul_pct'],
                'rrc_conn_avg': row['rrc_conn_avg'],
                'cqi_avg': row['cqi_avg'],
                'rsrp_avg_dbm': row['rsrp_avg_dbm'],
                'thrp_dl_gb': row['thrp_bits_dl'] / 8_000_000_000 if row['thrp_bits_dl'] is not None else None,
                'thrp_ul_gb': None,
                'dl_throughput_kbps': row['dl_throughput_kbps'],
                'dl_packet_delay_ms': row['dl_packet_delay_ms'],
                'cell_availability_pct': row['cell_availability_pct'],
            })
        return list(series.values())

    def get_configuration(self, obj):
        try:
            return ConfigurationFeaturesSerializer(obj.config_features).data
        except ConfigurationFeatures.DoesNotExist:
            return None

    def get_cluster_features(self, obj):
        try:
            return ClusterFeaturesSerializer(obj.cluster_features).data
        except ClusterFeatures.DoesNotExist:
            return None
