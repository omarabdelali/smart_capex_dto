"""Persisted analysis choices; validation, defaults and permissions live in services."""
import uuid
from django.conf import settings
from django.db import models


class AnalysisProfile(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    owner=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.PROTECT,related_name='analysis_profiles')
    browser_owner=models.UUIDField(null=True,blank=True,db_index=True)
    name=models.CharField(max_length=120)
    description=models.TextField(blank=True)
    purpose=models.CharField(max_length=12,default='both')
    event_type=models.CharField(max_length=40,default='ANY')
    tier_scheme=models.CharField(max_length=12,default='ANY')
    technology=models.CharField(max_length=16,default='ANY')
    is_shared=models.BooleanField(default=False)
    is_active=models.BooleanField(default=True)
    settings=models.JSONField(default=dict)
    revision=models.PositiveIntegerField(default=1)
    schema_version=models.CharField(max_length=30,default='analysis-profile-v1')
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)

    class Meta:
        ordering=['name','id']


class AnalysisProfileRevision(models.Model):
    profile=models.ForeignKey(AnalysisProfile,on_delete=models.PROTECT,related_name='revisions')
    revision=models.PositiveIntegerField()
    snapshot=models.JSONField()
    changed_by=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.PROTECT)
    browser_actor=models.UUIDField(null=True,blank=True)
    created_at=models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints=[models.UniqueConstraint(fields=['profile','revision'],name='unique_analysis_profile_revision')]


class AnalysisProfileDefault(models.Model):
    scope_key=models.CharField(max_length=64)
    user=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.PROTECT)
    purpose=models.CharField(max_length=12)
    scenario_key=models.CharField(max_length=160)
    profile=models.ForeignKey(AnalysisProfile,on_delete=models.PROTECT,related_name='default_assignments')
    updated_at=models.DateTimeField(auto_now=True)

    class Meta:
        constraints=[models.UniqueConstraint(fields=['scope_key','purpose','scenario_key'],name='unique_analysis_profile_default')]


class AnalysisSetup(models.Model):
    id=models.PositiveSmallIntegerField(primary_key=True,default=1)
    completed=models.BooleanField(default=False)
