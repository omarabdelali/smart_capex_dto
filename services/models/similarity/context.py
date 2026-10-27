"""Shared candidate preparation with a short-lived, explicitly identified fit cache."""
from django.core.cache import cache
from django.db.models import Q
from core.models import Site
from datetime import date
from services.models.preprocessing.network_events import effective_event_date
from .historical import event_labels
from .hierarchical_filter import HierarchicalFilter
from .profile_cache import cached_profile, profile_revision


def profile_cutoff(site, current_as_of):
    return (effective_event_date(site) or current_as_of or date.today()).replace(day=1)


def candidate_context(query_site, query_vector, current_as_of):
    candidate_queryset = Site.objects.filter(
            Q(is_launched=True, launch_date__isnull=False)
            | Q(cells__is_launched=True, cells__launch_date__isnull=False)
        ).exclude(pk=query_site.pk).distinct()
    candidate_queryset = candidate_queryset.filter(cluster_id=-1) if query_site.cluster_id==-1 else candidate_queryset.exclude(cluster_id=-1)
    if query_site.canonical_site_id:
        candidate_queryset = candidate_queryset.exclude(canonical_site_id=query_site.canonical_site_id)
    all_candidate_count = candidate_queryset.count()

    # Hierarchical filtering must use reconstructed vectors, never current
    # persisted configuration before the historical vectors are built.
    if query_vector.get('event_type') in ('NEW_SITE','SITE_ADDED'):
        launches = candidate_queryset.filter(is_launched=True, launch_date__isnull=False)
        if launches.count() >= 3:
            candidate_queryset = launches

    candidates = list(candidate_queryset.select_related(
        'config_features', 'geometric_features', 'clutter_features',
        'spatial_features', 'anp_features', 'cluster_features', 'prelaunch_kpi', 'road_features', 'user_context_features',
    ).prefetch_related('cells','network_events').order_by('site_id'))
    labels = []
    for site in candidates:
        cutoff = profile_cutoff(site, current_as_of)
        labels.append({'site_id': site.site_id, 'tier_scheme':'extended' if site.cluster_id==-1 else 'standard',
            'event_type': 'SITE_ADDED' if site.is_launched and site.launch_date and site.launch_date.replace(day=1) == cutoff else None,
            **event_labels(site, cutoff)})
    indices = HierarchicalFilter().filter_cases(query_vector, labels)
    candidates = [candidates[i] for i in indices]
    revision = profile_revision()
    vector_key = 'similarity-vectors-v3:' + str(current_as_of) + ':' + str(query_site.site_id) + ':' + str(revision)
    cached = cache.get(vector_key) if revision else None
    if cached is not None:
        by_id = {row['site_id']: row for row in cached}
        if all(site.site_id in by_id for site in candidates):
            return candidates, [by_id[site.site_id] for site in candidates], all_candidate_count
    snapshot_cache = {}
    candidate_vectors = [
        cached_profile(site, profile_cutoff(site, current_as_of), snapshot_cache, revision)
        for site in candidates
    ]
    if revision:
        cache.set(vector_key, candidate_vectors, timeout=300)
    return candidates, candidate_vectors, all_candidate_count
