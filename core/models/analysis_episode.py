"""Versioned analysis units; grouping logic lives in services."""
from django.db import models


class AnalysisEpisode(models.Model):
    episode_key=models.CharField(max_length=64,unique=True)
    site=models.ForeignKey('Site',on_delete=models.PROTECT,related_name='analysis_episodes')
    effective_date=models.DateField(db_index=True)
    event_type=models.CharField(max_length=32,db_index=True)
    action_signature=models.CharField(max_length=255)
    details=models.JSONField(default=dict)
    is_current=models.BooleanField(default=True)
    version=models.CharField(max_length=32,default='analysis-episode-v1')
    raw_events=models.ManyToManyField('RadioNetworkEvent',through='AnalysisEpisodeMember')

    class Meta:
        ordering=['effective_date','episode_key']
        constraints=[models.UniqueConstraint(fields=['site','effective_date'],condition=models.Q(is_current=True),name='unique_current_site_month_episode')]


class AnalysisEpisodeMember(models.Model):
    episode=models.ForeignKey(AnalysisEpisode,on_delete=models.PROTECT)
    raw_event=models.ForeignKey('RadioNetworkEvent',on_delete=models.PROTECT)

    class Meta:
        constraints=[models.UniqueConstraint(fields=['episode','raw_event'],name='unique_episode_raw_event')]
