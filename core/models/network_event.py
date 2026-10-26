"""Persisted operational events; detection and dating live in services."""
from django.db import models


class RadioNetworkEvent(models.Model):
    event_key = models.CharField(max_length=64, unique=True)
    site = models.ForeignKey('Site', on_delete=models.CASCADE, related_name='network_events')
    event_type = models.CharField(max_length=32, db_index=True)
    effective_date = models.DateField(db_index=True)
    configuration_date = models.DateField(null=True, blank=True)
    previous_bandwidth_mhz = models.FloatField(null=True, blank=True)
    new_bandwidth_mhz = models.FloatField(null=True, blank=True)
    details = models.JSONField(default=dict)
    is_current = models.BooleanField(default=True)
    detector_version = models.CharField(max_length=40)

    class Meta:
        db_table = 'radio_network_events'
        ordering = ['effective_date', 'event_key']
