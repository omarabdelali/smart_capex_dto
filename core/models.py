"""
Core Django models for Smart CAPEX Phase 1.
Implements all 56 Phase 1 features across Site, Cell, and feature tables.
See spec/smart_capex_data_catalog_phase1.md for feature definitions.
"""

from django.db import models
import os

# Check if we're using spatial backend
USE_GIS = os.environ.get('DB_ENGINE') == 'postgresql' or os.environ.get('USE_SPATIALITE') == 'true'

# Use appropriate models module
if USE_GIS:
    try:
        from django.contrib.gis.db import models as gis_models
        from django.contrib.gis.geos import Point
        BaseModel = gis_models.Model
        PointField = gis_models.PointField
    except Exception:
        # GDAL not installed, fallback to standard models
        BaseModel = models.Model
        PointField = lambda **kwargs: models.CharField(max_length=100, **{k: v for k, v in kwargs.items() if k != 'srid'})
else:
    BaseModel = models.Model
    # Fallback: store coordinates as text for standard SQLite
    PointField = lambda **kwargs: models.CharField(max_length=100, **{k: v for k, v in kwargs.items() if k != 'srid'})


class Site(BaseModel):
    """
    Represents a physical telecom site (aggregated from cells).
    One site can have multiple cells (different sectors/technologies).
    """
    site_id = models.CharField(max_length=50, unique=True, db_index=True)
    site_name = models.CharField(max_length=200)
    location = PointField(srid=4326)  # WGS84 (CharField for SQLite, PointField for PostGIS)
    latitude = models.FloatField()
    longitude = models.FloatField()
    
    # Will be populated after launch detection
    is_launched = models.BooleanField(default=False)
    launch_date = models.DateField(null=True, blank=True)
    
    # Clustering fields (populated after site deduplication and clustering)
    cluster_id = models.IntegerField(default=-1, help_text="Cluster ID from DBSCAN (-1 for noise/single-site clusters)")
    is_cluster_edge = models.BooleanField(default=False, help_text="True if site is on edge of cluster polygon")
    out_of_bounds = models.BooleanField(default=False, help_text="True if site is outside Tunisia boundaries")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'sites'
        indexes = [
            models.Index(fields=['site_id']),
            models.Index(fields=['is_launched']),
        ]
    
    def __str__(self):
        return f"{self.site_name} ({self.site_id})"


class Cell(models.Model):
    """
    Represents an individual cell (sector) from cell plan.
    Multiple cells aggregate to one site.
    """
    TECHNOLOGY_CHOICES = [
        ('2G', '2G/GSM'),
        ('3G', '3G/UMTS'),
        ('4G', '4G/LTE'),
    ]
    
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name='cells')
    cell_id = models.CharField(max_length=50, unique=True, db_index=True)
    cell_name = models.CharField(max_length=200)
    cgi = models.CharField(max_length=100, blank=True)
    
    # Technology and frequency
    technology = models.CharField(max_length=2, choices=TECHNOLOGY_CHOICES)
    frequency = models.FloatField(help_text="Frequency in MHz")
    band = models.CharField(max_length=50)
    bandwidth_mhz = models.FloatField(default=0)
    
    # Antenna configuration
    azimuth = models.FloatField(help_text="Degrees 0-360")
    antenna_height_m = models.FloatField(help_text="Antenna height above ground (10-55m)")
    
    # Launch status (from KPI-based detection)
    is_launched = models.BooleanField(default=False)
    launch_date = models.DateField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'cells'
        indexes = [
            models.Index(fields=['cell_id']),
            models.Index(fields=['site', 'technology']),
            models.Index(fields=['is_launched']),
        ]
    
    def __str__(self):
        return f"{self.cell_name} ({self.technology})"


class ConfigurationFeatures(BaseModel):
    """
    Configuration features (Section 3: 10 features).
    Represents site configuration at launch time.
    """
    EVENT_TYPE_CHOICES = [
        ('NEW_SITE', 'New Site'),
        ('TECH_ADD', 'Technology Addition'),
        ('BAND_ADD', 'Band Addition'),
        ('SECTOR_ADD', 'Sector Addition'),
        ('CAPACITY_ADD', 'Capacity Addition'),
        ('TECH_SUNSET', 'Technology Sunset'),
    ]
    
    site = models.OneToOneField(Site, on_delete=models.CASCADE, related_name='config_features')
    
    # 3.1 event_type
    event_type = models.CharField(max_length=20, choices=EVENT_TYPE_CHOICES)
    
    # 3.2 tech_added
    tech_added = models.CharField(max_length=2, blank=True, choices=Cell.TECHNOLOGY_CHOICES)
    
    # 3.3 tech_before (binary vector stored as JSON: [2G, 3G, 4G])
    has_2g_before = models.BooleanField(default=False)
    has_3g_before = models.BooleanField(default=False)
    has_4g_before = models.BooleanField(default=False)
    
    # 3.4 tech_after
    has_2g_after = models.BooleanField(default=False)
    has_3g_after = models.BooleanField(default=False)
    has_4g_after = models.BooleanField(default=False)
    
    # 3.5 bands_added (stored as comma-separated)
    bands_added = models.CharField(max_length=200, blank=True)
    
    # 3.6 sector_count_after
    sector_count_after = models.IntegerField(default=0)
    
    # 3.7 cells_per_sector_after
    cells_per_sector_after = models.FloatField(default=0)
    
    # 3.8 antenna_height_m (average across sectors)
    antenna_height_m = models.FloatField(default=0)
    
    # 3.9 total_bw_after_mhz
    total_bw_after_mhz = models.FloatField(default=0)
    
    # 3.10 total_capacity_after_mbps
    total_capacity_after_mbps = models.FloatField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'configuration_features'
    
    def __str__(self):
        return f"Config: {self.site.site_name} ({self.event_type})"


class GeometricFeatures(BaseModel):
    """
    Geometry features (Section 4: 4 features).
    DEM-derived terrain characteristics.
    """
    site = models.OneToOneField(Site, on_delete=models.CASCADE, related_name='geometric_features')
    
    # 4.1 z_antenna_m (DEM elevation + antenna height)
    z_antenna_m = models.FloatField(help_text="Antenna elevation above sea level (30-200m)")
    
    # 4.2 terrain_slope_deg
    terrain_slope_deg = models.FloatField(help_text="Median terrain slope in 200m buffer (0-25°)")
    
    # 4.3 terrain_roughness_m
    terrain_roughness_m = models.FloatField(help_text="Terrain elevation std dev in 1km buffer (0-40m)")
    
    # 4.4 terrain_aspect_deg
    terrain_aspect_deg = models.FloatField(help_text="Direction of terrain slope (0-360°)")
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'geometric_features'
    
    def __str__(self):
        return f"Geometry: {self.site.site_name}"


class ClutterFeatures(BaseModel):
    """
    Clutter/topology features (Section 5: 4 features).
    Land cover and building characteristics.
    """
    CLUTTER_CHOICES = [
        ('urban', 'Urban'),
        ('suburban', 'Suburban'),
        ('rural', 'Rural'),
        ('water', 'Water'),
        ('forest', 'Forest'),
    ]
    
    site = models.OneToOneField(Site, on_delete=models.CASCADE, related_name='clutter_features')
    
    # 5.1 dominant_clutter
    dominant_clutter = models.CharField(max_length=20, choices=CLUTTER_CHOICES)
    
    # 5.2 clutter_entropy_2km
    clutter_entropy_2km = models.FloatField(help_text="Land use diversity (0-1.5)")
    
    # 5.3 pct_building_area_1km
    pct_building_area_1km = models.FloatField(help_text="Building coverage percentage (0-90%)")
    
    # 5.4 avg_building_height_m
    avg_building_height_m = models.FloatField(help_text="Average building height (0-40m)")
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'clutter_features'
    
    def __str__(self):
        return f"Clutter: {self.site.site_name} ({self.dominant_clutter})"


class SpatialFeatures(BaseModel):
    """
    Legacy spatial context features (Section 6.1-6.8: 8 features).
    Neighbor counts and distances.
    """
    site = models.OneToOneField(Site, on_delete=models.CASCADE, related_name='spatial_features')
    
    # 6.1 dist_nearest_site_m
    dist_nearest_site_m = models.FloatField(help_text="Distance to nearest site (50-2950m)")
    
    # 6.2 n_sites_1km
    n_sites_1km = models.IntegerField(default=0, help_text="Sites within 1km (0-10)")
    
    # 6.3 n_sites_2km
    n_sites_2km = models.IntegerField(default=0, help_text="Sites within 2km (0-25)")
    
    # 6.4 n_sites_3km
    n_sites_3km = models.IntegerField(default=0, help_text="Sites within 3km (0-50)")
    
    # 6.5 n_2g_sites_2km
    n_2g_sites_2km = models.IntegerField(default=0, help_text="2G sites within 2km")
    
    # 6.6 n_3g_sites_2km
    n_3g_sites_2km = models.IntegerField(default=0, help_text="3G sites within 2km")
    
    # 6.7 n_4g_sites_2km
    n_4g_sites_2km = models.IntegerField(default=0, help_text="4G sites within 2km")
    
    # 6.8 neighbor_avg_antenna_height_m
    neighbor_avg_antenna_height_m = models.FloatField(default=0, help_text="Mean antenna height of neighbors (10-55m)")
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'spatial_features'
    
    def __str__(self):
        return f"Spatial: {self.site.site_name}"


class ANPFeatures(BaseModel):
    """
    Angular Neighborhood Profile features (Section 6.9-6.23: 15 features).
    Key innovation for edge vs infill classification using 360° rotation.
    """
    site = models.OneToOneField(Site, on_delete=models.CASCADE, related_name='anp_features')
    
    # 6.9 n_tier1 (neighbors within 2km)
    n_tier1 = models.IntegerField(default=0)
    
    # 6.10 n_tier2 (neighbors 2-5km)
    n_tier2 = models.IntegerField(default=0)
    
    # 6.11 t1_to_t2_ratio
    t1_to_t2_ratio = models.FloatField(default=0)
    
    # 6.12 t1_nearest_m (nearest in tier1)
    t1_nearest_m = models.FloatField(default=0)
    
    # 6.13 t2_nearest_m (nearest in tier2)
    t2_nearest_m = models.FloatField(default=0)
    
    # 6.14 angular_uniformity (0-1, 1=perfectly uniform)
    angular_uniformity = models.FloatField(default=0)
    
    # 6.15 max_empty_arc_deg (largest gap with no neighbors)
    max_empty_arc_deg = models.FloatField(default=0)
    
    # 6.16 n_empty_bins (12 bins of 30°, count with 0 neighbors)
    n_empty_bins = models.IntegerField(default=0)
    
    # 6.17 dominant_sector_deg (30° bin with most neighbors)
    dominant_sector_deg = models.FloatField(default=0)
    
    # 6.18 dominant_sector_count
    dominant_sector_count = models.IntegerField(default=0)
    
    # 6.19 edge_score (0-1, higher = edge site)
    edge_score = models.FloatField(default=0, help_text="Composite edge/infill score")
    
    # 6.20 bearing_stddev_deg (angular spread of tier1 neighbors)
    bearing_stddev_deg = models.FloatField(default=0)
    
    # 6.21 avg_neighbor_dist_t1_m
    avg_neighbor_dist_t1_m = models.FloatField(default=0)
    
    # 6.22 avg_neighbor_dist_t2_m
    avg_neighbor_dist_t2_m = models.FloatField(default=0)
    
    # 6.23 coverage_asymmetry (0-1, difference between max/min quadrant densities)
    coverage_asymmetry = models.FloatField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'anp_features'
    
    def __str__(self):
        return f"ANP: {self.site.site_name} (edge={self.edge_score:.2f})"


class PreLaunchKPI(BaseModel):
    """
    Pre-launch state features (Section 7: 9 KPI features for Phase 1).
    Computed from MAOS data 30 days before launch.
    """
    site = models.OneToOneField(Site, on_delete=models.CASCADE, related_name='prelaunch_kpi')
    
    # 7.1 avg_traffic_dl_gb (30d before launch)
    avg_traffic_dl_gb = models.FloatField(default=0)
    
    # 7.2 avg_traffic_ul_gb
    avg_traffic_ul_gb = models.FloatField(default=0)
    
    # 7.3 avg_users
    avg_users = models.FloatField(default=0)
    
    # 7.4 avg_prb_util_pct (PRB utilization)
    avg_prb_util_pct = models.FloatField(default=0)
    
    # 7.5 peak_hour_traffic_gb
    peak_hour_traffic_gb = models.FloatField(default=0)
    
    # 7.6 peak_hour_users
    peak_hour_users = models.FloatField(default=0)
    
    # 7.7 avg_cqi (Channel Quality Indicator)
    avg_cqi = models.FloatField(default=0)
    
    # 7.8 avg_rsrp_dbm (Reference Signal Received Power)
    avg_rsrp_dbm = models.FloatField(default=0)
    
    # 7.9 congestion_hours_per_day
    congestion_hours_per_day = models.FloatField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'prelaunch_kpi'
    
    def __str__(self):
        return f"PreLaunch KPI: {self.site.site_name}"


class ClusterFeatures(BaseModel):
    """
    Cluster context features (Section 8: 6 features).
    Characteristics of the site's neighborhood cluster.
    """
    site = models.OneToOneField(Site, on_delete=models.CASCADE, related_name='cluster_features')
    
    # 8.1 cluster_id (from clustering algorithm)
    cluster_id = models.IntegerField(default=0)
    
    # 8.2 cluster_size (number of sites in cluster)
    cluster_size = models.IntegerField(default=0)
    
    # 8.3 cluster_density_sites_per_km2
    cluster_density_sites_per_km2 = models.FloatField(default=0)
    
    # 8.4 cluster_avg_traffic_gb
    cluster_avg_traffic_gb = models.FloatField(default=0)
    
    # 8.5 cluster_avg_users
    cluster_avg_users = models.FloatField(default=0)
    
    # 8.6 dist_to_cluster_centroid_m
    dist_to_cluster_centroid_m = models.FloatField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'cluster_features'
    
    def __str__(self):
        return f"Cluster: {self.site.site_name} (cluster_id={self.cluster_id})"


class MAOSMonthlyKPI(BaseModel):
    """
    Huawei MAOS monthly KPI data for launch detection.
    Stores monthly aggregated counters per cell.
    """
    cell = models.ForeignKey(Cell, on_delete=models.CASCADE, related_name='monthly_kpis')
    month_date = models.DateField(db_index=True, help_text="First day of the month")
    
    # Traffic counters
    traffic_user_avg = models.FloatField(default=0, help_text="L.Traffic.User.Avg")
    thrp_bits_dl = models.FloatField(default=0, help_text="L.Thrp.bits.DL (bits)")
    thrp_bits_ul = models.FloatField(default=0, help_text="L.Thrp.bits.UL (bits)")
    
    # PRB utilization
    prb_util_dl_pct = models.FloatField(default=0)
    prb_util_ul_pct = models.FloatField(default=0)
    
    # User metrics
    rrc_conn_avg = models.FloatField(default=0, help_text="Average RRC connections")
    active_users_avg = models.FloatField(default=0)
    
    # Quality metrics
    cqi_avg = models.FloatField(default=0, help_text="Channel Quality Indicator")
    rsrp_avg_dbm = models.FloatField(default=0, help_text="RSRP in dBm")
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'maos_monthly_kpi'
        unique_together = [['cell', 'month_date']]
        indexes = [
            models.Index(fields=['cell', 'month_date']),
            models.Index(fields=['month_date']),
        ]
    
    def __str__(self):
        return f"{self.cell.cell_name} - {self.month_date.strftime('%Y-%m')}"
