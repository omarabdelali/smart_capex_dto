"""
Site model for Smart CAPEX.
Represents physical telecom sites aggregated from cells.
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