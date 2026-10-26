"""Disposable local profile cache, invalidated by SQLite/source/code revisions.

This caches calculated profiles, not PCA training outcomes. It never changes
missingness or timing. Non-file databases bypass it until a revision service is
configured; test in-memory databases always bypass it.
"""
import hashlib
from pathlib import Path
from django.conf import settings
from django.core.cache.backends.filebased import FileBasedCache
from .feature_vector import build_site_similarity_vector


def profile_revision():
    database = settings.DATABASES['default']
    path = Path(str(database['NAME']))
    if 'sqlite' not in database['ENGINE'] or not path.is_file():
        return None
    roots = [path, Path(str(path) + '-wal')]
    base = Path(settings.BASE_DIR)
    roots += list((base / 'services').rglob('*.py')) + list((base / 'config').glob('*.json'))
    roots += [p for p in (base / 'data/geographic').rglob('*') if p.suffix.lower() in ('.tif', '.vrt', '.gpkg')]
    parts = []
    for item in sorted(roots):
        if item.is_file():
            info = item.stat()
            parts.append(f'{item}:{info.st_size}:{info.st_mtime_ns}')
    return hashlib.sha256('|'.join(parts).encode()).hexdigest()[:24]


def cache_backend():
    return FileBasedCache(str(Path(settings.BASE_DIR) / 'data/cache/similarity_profiles'),
                          {'TIMEOUT': 86400, 'OPTIONS': {'MAX_ENTRIES': 10000}})


def cache_key(site_id, cutoff, revision):
    return 'profile-v1:' + hashlib.sha256(f'{revision}:{site_id}:{cutoff}'.encode()).hexdigest()


def cached_profile(site, cutoff, snapshot_cache, revision):
    if revision:
        key = cache_key(site.site_id, cutoff, revision)
        cached = cache_backend().get(key)
        if cached is not None:
            return cached
    vector = build_site_similarity_vector(site, as_of_date=cutoff, snapshot_cache=snapshot_cache, allow_current_roads=True)
    if revision:
        cache_backend().set(key, vector)
    return vector
