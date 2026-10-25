from django.db import models


class FeatureSyncJob(models.Model):
    MODE_CHOICES = [('features', 'Features only'), ('full', 'Full sync')]
    STATUS_CHOICES = [('queued', 'Queued'), ('running', 'Running'), ('succeeded', 'Succeeded'), ('failed', 'Failed')]

    mode = models.CharField(max_length=16, choices=MODE_CHOICES)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='queued', db_index=True)
    stage = models.CharField(max_length=32, default='queued')
    processed = models.PositiveIntegerField(default=0)
    total = models.PositiveIntegerField(default=0)
    current_site = models.CharField(max_length=100, blank=True, default='')
    result = models.JSONField(null=True, blank=True)
    error = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'feature_sync_jobs'
        ordering = ['-created_at']
