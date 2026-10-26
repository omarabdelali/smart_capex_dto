"""Road calculations, topology proxy and persistence; no view/model logic."""
from collections import defaultdict
from datetime import date
import hashlib
import json
import logging

import geopandas as gpd
import numpy as np
from pyproj import Transformer
from shapely.geometry import Point
import shapely

from .road_loader import ROAD_FIELDS, road_config, prepare_roads

logger = logging.getLogger(__name__)
PROJECT = Transformer.from_crs('EPSG:4326', 'EPSG:32632', always_xy=True)


class RoadFeatureExtractor:
    def __init__(self, roads=None, config=None, manifest=None):
        self.config = config or road_config()
        self.manifest = manifest or prepare_roads()
        self.roads = roads if roads is not None else gpd.read_file(self.manifest['normalized_path'], layer='roads')
        if self.roads.crs is None or self.roads.crs.to_epsg() != 32632:
            raise ValueError('Road calculations require EPSG:32632')
        self.index = self.roads.sindex
        self.weights = self.config['class_weights']
        self.weights_version = hashlib.sha256(json.dumps(self.weights,sort_keys=True).encode()).hexdigest()

    def extract(self, latitude, longitude):
        x, y = PROJECT.transform(longitude, latitude)
        point = Point(x, y)
        radius = self.config['buffer_m']
        buffer = point.buffer(radius, resolution=64)
        values = dict.fromkeys(ROAD_FIELDS)
        values.update({
            'source': self.manifest['source'], 'buffer_m': radius,
            'osm_extract_date': self.manifest.get('osm_extract_date'),
            'source_hash': self.manifest['source_hash'],
            'method_version': self.config['method_version'], 'weights_version': self.weights_version,
            'coverage_status': 'no_source_roads_within_5km',
            'class_lengths_km': None,
        })
        covered = self.index.query(point.buffer(self.config['coverage_radius_m']), predicate='intersects')
        if not len(covered):
            return values
        nearby = self.roads.iloc[self.index.query(buffer, predicate='intersects')]
        selected = nearby.loc[nearby.highway.isin(set(self.weights)-{'unknown'})].copy()
        lengths = {}
        if not selected.empty:
            clipped = gpd.overlay(selected, gpd.GeoDataFrame(geometry=[buffer],crs=self.roads.crs),
                                  how='intersection', keep_geom_type=True)
            if not clipped.empty:
                lengths = (clipped.assign(km=clipped.length/1000).groupby('highway').km.sum()).to_dict()
        total = float(sum(lengths.values()))
        weighted = float(sum(self.weights[name]*length for name,length in lengths.items()))
        highway = float(sum(lengths.get(name,0) for name in ('motorway','trunk')))
        values.update({
            'road_km_total': total, 'road_km_weighted': weighted,
            'road_density_weighted_km_km2': weighted/(buffer.area/1e6),
            'highway_km': highway, 'highway_share': highway/total if total > 0 else None,
            'n_road_intersections': junction_count(selected, buffer),
            'dominant_road_class': sorted(lengths,key=lambda name:(-lengths[name],name))[0] if total else None,
            'coverage_status': 'nearby_osm_evidence', 'class_lengths_km': lengths,
        })
        return values


def junction_count(roads, buffer):
    """Degree >=3 planar junction proxy, NOT an original OSM-node count.

    Node original uncut local lines before counting; buffer boundaries cannot
    create junctions. Keep bridge/tunnel/layer groups separate. Coincident
    undirected edges count once. Rounding tolerance is 1 cm in UTM.
    """
    groups = defaultdict(list)
    for row in roads.itertuples():
        key = tuple(str(getattr(row,name,None)) for name in ('layer','bridge','tunnel'))
        groups[key].append(row.geometry)
    count = 0
    for geometries in groups.values():
        graph = defaultdict(set)
        merged = shapely.union_all(geometries)
        for line in shapely.get_parts(merged):
            if line.geom_type != 'LineString' or line.length <= .01:
                continue
            a, b = (tuple(round(float(v),2) for v in coord[:2]) for coord in (line.coords[0],line.coords[-1]))
            if a != b:
                graph[a].add(b)
                graph[b].add(a)
        count += sum(len(edges)>=3 and buffer.covers(Point(*node)) for node,edges in graph.items())
    return int(count)


def save_site_roads(site, extractor):
    from core.models import RoadFeatures
    values = extractor.extract(site.latitude, site.longitude)
    RoadFeatures.objects.update_or_create(site=site, defaults=values)
    return values


def backfill_roads(site_ids=None, progress_callback=None, source_path=None, extract_date=None):
    from core.models import Site
    extractor = RoadFeatureExtractor(manifest=prepare_roads(source_path, extract_date))
    sites = Site.objects.all().order_by('pk')
    if site_ids:
        sites = sites.filter(site_id__in=site_ids)
    result = {'total': sites.count(), 'computed': 0, 'null': 0, 'errors': 0, 'source': extractor.manifest}
    for index, site in enumerate(sites.iterator(),1):
        try:
            values = save_site_roads(site, extractor)
            result['null' if values['road_km_total'] is None else 'computed'] += 1
        except Exception:
            logger.exception('Road extraction failed for %s', site.site_id)
            result['errors'] += 1
        if progress_callback and (index == 1 or index % 25 == 0 or index == result['total']):
            progress_callback({'stage':'roads','processed':index,'total':result['total'],'current_site':site.site_id})
    return result


def road_similarity_values(road, as_of_date, allow_current=False):
    """Keep source metadata outside distance; do not invent historical roads."""
    if road is None:
        return dict.fromkeys(ROAD_FIELDS)
    known = road.osm_extract_date is not None and road.osm_extract_date < as_of_date
    if not allow_current and not known:
        return dict.fromkeys(ROAD_FIELDS)
    return {**{field:getattr(road,field) for field in ROAD_FIELDS},
            'road_context_signature': '|'.join(map(str,(road.source_hash,road.buffer_m,road.method_version,road.weights_version))),
            'road_context_note': 'Current road snapshot; historical availability unverified' if not known else 'Source available before cutoff'}


def refresh_road_provenance(source_path=None, extract_date=None):
    """Attest an unchanged source snapshot without recalculating measurements."""
    from core.models import RoadFeatures
    manifest = prepare_roads(source_path, extract_date)
    updated = RoadFeatures.objects.filter(source_hash=manifest['source_hash']).update(osm_extract_date=manifest['osm_extract_date'])
    return {'updated_rows':updated,'source':manifest}
