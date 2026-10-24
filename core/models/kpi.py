"""
KPI models for Smart CAPEX.
Represents pre-launch KPIs and MAOS monthly KPI data.
"""

from django.db import models
from .site import Site, BaseModel
from .cell import Cell


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