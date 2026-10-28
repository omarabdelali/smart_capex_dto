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
    traffic_user_avg = models.FloatField(null=True, blank=True, default=None, help_text="L.Traffic.User.Avg")
    thrp_bits_dl = models.FloatField(null=True, blank=True, default=None, help_text="L.Thrp.bits.DL (bits)")
    thrp_bits_ul = models.FloatField(null=True, blank=True, default=None, help_text="Unavailable in current LTE report")
    
    # PRB utilization
    prb_util_dl_pct = models.FloatField(null=True, blank=True, default=None)
    prb_util_ul_pct = models.FloatField(null=True, blank=True, default=None)
    
    # User metrics
    rrc_conn_avg = models.FloatField(null=True, blank=True, default=None, help_text="Unavailable as an average in current LTE report")
    active_users_avg = models.FloatField(null=True, blank=True, default=None)
    queued_users_dl = models.FloatField(null=True, blank=True, default=None, help_text='FT_AVERAGE NUMBER OF UE QUEUED DL')
    queued_users_ul = models.FloatField(null=True, blank=True, default=None, help_text='FT_AVERAGE NUMBER OF UE QUEUED UL')
    border_user_avg = models.FloatField(null=True, blank=True, default=None, help_text='L.Traffic.User.BorderUE.Avg')
    border_user_max = models.FloatField(null=True, blank=True, default=None, help_text='L.Traffic.User.BorderUE.Max')
    lowlatency_user_avg = models.FloatField(null=True, blank=True, default=None, help_text='L.Traffic.User.LowLatency.Avg')
    
    # Quality metrics
    cqi_avg = models.FloatField(null=True, blank=True, default=None, help_text="Weighted mean from downlink CQI histogram")
    rsrp_avg_dbm = models.FloatField(null=True, blank=True, default=None, help_text="Unavailable as a downlink cell-level average in current LTE report")

    # Raw components retained so site and cluster summaries can aggregate
    # ratios and weighted averages correctly instead of averaging averages.
    prb_dl_used_avg = models.FloatField(null=True, blank=True, default=None)
    prb_dl_available = models.FloatField(null=True, blank=True, default=None)
    thrp_time_dl_ms = models.FloatField(null=True, blank=True, default=None)
    thrp_bits_dl_last_tti = models.FloatField(null=True, blank=True, default=None)
    dl_packet_delay_time_ms = models.FloatField(null=True, blank=True, default=None)
    dl_packet_delay_packets = models.FloatField(null=True, blank=True, default=None)
    dl_throughput_kbps = models.FloatField(null=True, blank=True, default=None)
    dl_packet_delay_ms = models.FloatField(null=True, blank=True, default=None)
    cell_unavail_duration_s = models.FloatField(null=True, blank=True, default=None)
    observation_duration_s = models.FloatField(null=True, blank=True, default=None)
    cell_availability_pct = models.FloatField(null=True, blank=True, default=None)
    cqi_weighted_sum = models.FloatField(null=True, blank=True, default=None)
    cqi_sample_count = models.FloatField(null=True, blank=True, default=None)
    
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
