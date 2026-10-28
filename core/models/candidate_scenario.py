import uuid
from django.db import models


class CandidateScenario(models.Model):
    """Saved planning exercise; never part of the operational site inventory."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    inputs = models.JSONField(default=dict)
    features = models.JSONField(default=dict)
    result = models.JSONField(default=dict)
    status = models.CharField(max_length=20, default='calculating')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
