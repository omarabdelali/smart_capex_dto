"""Local Geofabrik ingestion and reproducible road snapshot provenance."""
from datetime import date
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
from zipfile import ZipFile

import geopandas as gpd

ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = ROOT / 'config/road_context.json'
ROAD_NUMERIC = ('road_km_total', 'road_km_weighted', 'road_density_weighted_km_km2',
                'highway_km', 'highway_share', 'n_road_intersections')
ROAD_FIELDS = (*ROAD_NUMERIC, 'dominant_road_class')
ROAD_LABELS = {
    'road_km_total': ('Road length (1 km)', 'km'),
    'road_km_weighted': ('Weighted road length (1 km)', 'km'),
    'road_density_weighted_km_km2': ('Weighted road density (1 km)', 'km/km²'),
    'highway_km': ('Motorway + trunk length', 'km'),
    'highway_share': ('Motorway + trunk share', 'fraction'),
    'n_road_intersections': ('Estimated road junctions', 'junctions'),
    'dominant_road_class': ('Dominant road class', ''),
}


def road_config():
    return json.loads(CONFIG_PATH.read_text(encoding='utf-8'))


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024*1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def prepare_roads(source_path=None, extract_date=None):
    """Never downloads, replaces source data, or invents an extract date."""
    config = road_config()
    if extract_date:
        extract_date = date.fromisoformat(str(extract_date)).isoformat()
    source = Path(source_path or ROOT / config['source_path']).resolve()
    if not source.exists():
        raise FileNotFoundError(f'Local road source missing: {source}. Supply a local Geofabrik extract. URL: {config["download_url"]}')
    stamp = source.stat()
    return _prepare(str(source), stamp.st_size, stamp.st_mtime_ns, extract_date or config['extract_date'])


@lru_cache(maxsize=4)
def _prepare(source, size, modified, extract_date):
    config = road_config()
    digest = file_hash(source)
    archive = Path(source).parent/'tunisia-latest-free.gpkg.zip'
    verified_as_of = None
    if archive.exists():
        with ZipFile(archive) as packaged:
            if 'README' in packaged.namelist() and Path(source).name in packaged.namelist():
                readme = packaged.read('README').decode('utf-8')
                match = re.search(r'as of (\d{4}-\d{2}-\d{2}T[\d:]+Z)',readme)
                if match:
                    archived_hash = hashlib.sha256()
                    with packaged.open(Path(source).name) as member:
                        for chunk in iter(lambda:member.read(1024*1024),b''):
                            archived_hash.update(chunk)
                    if archived_hash.hexdigest() == digest:
                        verified_as_of = match.group(1)
                        if extract_date and extract_date != verified_as_of[:10]:
                            raise ValueError('Declared extract date conflicts with matching archive README')
                        extract_date = verified_as_of[:10]
    output = ROOT / 'data/geographic/osm' / f'roads_utm32_{digest[:12]}.gpkg'
    manifest_path = output.with_suffix('.json')
    if output.exists() and manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        if manifest.get('source_hash') == digest and verified_as_of:
            manifest.update(osm_extract_date=extract_date, data_as_of=verified_as_of,
                            date_status='verified matching-archive README; archive member SHA-256 matches source')
            manifest_path.write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')
        if manifest.get('source_hash') == digest and manifest.get('osm_extract_date') == extract_date:
            if file_hash(output) != manifest.get('normalized_hash'):
                raise ValueError(f'Normalized road file hash mismatch: {output}')
            return manifest
        # Different metadata must not silently relabel an existing snapshot.
        output = output.with_name(f'{output.stem}_{extract_date or "undated"}.gpkg')
        manifest_path = output.with_suffix('.json')
        if output.exists():
            raise ValueError(f'Unverified road output already exists: {output}')
    roads = gpd.read_file(source, layer=config['source_layer'])
    if roads.crs is None:
        raise ValueError('Road source has no CRS')
    roads = roads.rename(columns={'fclass': 'highway'})
    if 'highway' not in roads:
        raise ValueError('Road source requires highway/fclass classification')
    roads = roads.loc[roads.geometry.notna() & ~roads.geometry.is_empty].copy()
    roads['highway'] = roads['highway'].str.replace(r'_link$', '', regex=True)
    for column in ('lanes', 'maxspeed', 'bridge', 'tunnel', 'layer', 'osm_id'):
        if column not in roads:
            roads[column] = None
    roads = roads[['osm_id','highway','lanes','maxspeed','bridge','tunnel','layer','geometry']].to_crs('EPSG:32632')
    # Keep all source classes in this layer for the independent 5 km coverage
    # heuristic; the extractor restricts measured lengths to configured classes.
    roads = roads.drop_duplicates(subset=['osm_id','geometry'])
    roads.to_file(output, layer='roads', driver='GPKG', SPATIAL_INDEX='YES')
    manifest = {
        'source': 'OSM / Geofabrik Tunisia', 'source_path': source,
        'source_hash': digest, 'normalized_path': str(output),
        'normalized_hash': file_hash(output), 'osm_extract_date': extract_date,
        'data_as_of': verified_as_of,
        'date_status': 'verified matching-archive README' if verified_as_of else 'declared by operator' if extract_date else 'unknown; filesystem date is not extract date',
        'prepared_date': date.today().isoformat(), 'download_url': config['download_url'],
        'licence': 'ODbL 1.0', 'attribution': '© OpenStreetMap contributors; Geofabrik',
        'crs': 'EPSG:32632', 'source_road_count': len(roads),
        'class_weights': config['class_weights'], 'calibration_status': config['calibration_status'],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    return manifest
