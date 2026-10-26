"""
Cell model for Smart CAPEX.
Represents individual cells (sectors) from cell plan.
"""

from django.db import models
from .site import Site


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
    effective_activation_month = models.DateField(null=True, blank=True)
    activation_evidence = models.CharField(max_length=32, default='no_positive_traffic')
    
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
