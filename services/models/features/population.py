"""GHSL population catchments and map tiles at the source's native precision."""
from functools import lru_cache
from io import BytesIO
from pathlib import Path
import logging
import math

import numpy as np
import rasterio
from PIL import Image
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from rasterio.warp import reproject
from rasterio.windows import Window, from_bounds as window_from_bounds
from rasterio.vrt import WarpedVRT
from shapely.geometry import Point
from shapely.ops import transform

logger = logging.getLogger(__name__)
POPULATION_PATH = Path(__file__).resolve().parents[3] / 'data/geographic/ghsl/ghs_pop_e2025_r2023a_54009_100_v1_0_tun.tif'
POPULATION_FIELDS = ('population_density_1km_per_km2', 'population_tier1', 'population_tier2')
WORLDCOVER_PATH = POPULATION_PATH.parents[1] / 'worldcover/esa_worldcover_v200.vrt'


def water_cells(crs, grid, shape):
    """Identify water independently; never assume every missing POP cell is sea."""
    if not WORLDCOVER_PATH.exists():
        return np.zeros(shape, dtype=bool)
    try:
        with rasterio.open(WORLDCOVER_PATH) as cover:
            with WarpedVRT(cover, crs=crs, transform=grid, width=shape[1], height=shape[0],
                           resampling=Resampling.mode, nodata=0) as aligned:
                return aligned.read(1) == 80
    except rasterio.errors.RasterioError:
        logger.warning('Water classification unavailable; retaining mapped population with coverage metadata')
        return np.zeros(shape, dtype=bool)


def population_features(latitude, longitude, tier_scheme='standard'):
    try:
        version = (POPULATION_PATH.stat().st_mtime_ns,
                   WORLDCOVER_PATH.stat().st_mtime_ns if WORLDCOVER_PATH.exists() else None)
        args = (str(POPULATION_PATH), version, float(latitude), float(longitude))
        density = _catchment(*args)
        inner,outer = (5000,10000) if tier_scheme=='extended' else (2000,5000)
        tier1 = _catchment(*args, radius=inner)
        tier2 = _catchment(*args, radius=outer, inner_radius=inner)
        return {'population_density_1km_per_km2': density['population_density_1km_per_km2'],
                'population_tier1': tier1['population_total'],
                'population_tier2': tier2['population_total'],
                'quality': {name: {key: result.get(key) for key in ('coverage', 'land_coverage', 'water_pct', 'status', 'observed_population')}
                            for name, result in [('density_1km', density), ('tier1', tier1), ('tier2', tier2)]}}
    except (OSError, ValueError, rasterio.errors.RasterioError):
        logger.exception('Population catchment unavailable')
        return dict.fromkeys(POPULATION_FIELDS)


@lru_cache(maxsize=8192)
def _catchment(path, version, latitude, longitude, radius=1000, inner_radius=0):
    """Area-weight mapped counts and disclose uncovered land without filling it."""
    to_local = Transformer.from_crs('EPSG:4326', 'EPSG:32632', always_xy=True)
    x, y = to_local.transform(longitude, latitude)
    with rasterio.open(path) as src:
        to_source = Transformer.from_crs('EPSG:32632', src.crs, always_xy=True)
        local = Point(x, y).buffer(radius, resolution=64)
        if inner_radius:
            local = local.difference(Point(x, y).buffer(inner_radius, resolution=64))
        circle = transform(to_source.transform, local)
        bounds = window_from_bounds(*circle.bounds, transform=src.transform)
        left, top = max(0, math.floor(bounds.col_off)), max(0, math.floor(bounds.row_off))
        right = min(src.width, math.ceil(bounds.col_off + bounds.width))
        bottom = min(src.height, math.ceil(bounds.row_off + bounds.height))
        if right <= left or bottom <= top:
            return {'population_density_1km_per_km2': None, 'population_total': None, 'coverage': 0,
                    'status': 'outside_raster'}
        window = Window(left, top, right-left, bottom-top)
        data = src.read(1, window=window, masked=True)
        grid = src.window_transform(window)
        cell_area = abs(grid.a * grid.e)
        # Vectorized intersections keep the 5 km ring practical during ranking.
        import shapely
        valid = ~np.ma.getmaskarray(data) & np.isfinite(data.data) & (data.data >= 0)
        rows, cols = np.indices(data.shape)
        rows, cols = rows.ravel(), cols.ravel()
        x0, y0 = grid * (cols, rows)
        x1, y1 = grid * (cols+1, rows+1)
        cells = shapely.box(np.minimum(x0,x1), np.minimum(y0,y1), np.maximum(x0,x1), np.maximum(y0,y1))
        areas = shapely.area(shapely.intersection(cells, circle))
        water = water_cells(src.crs, grid, data.shape).ravel()
        measured = valid.ravel()
        valid_area = float(areas[measured].sum())
        population = float(np.sum(data.data.ravel()[measured] * areas[measured] / cell_area))
        water_area = float(areas[water].sum())
        known_area = float(areas[measured | water].sum())
        land_area = max(0, circle.area-water_area)
        measured_land = float(areas[measured & ~water].sum())
        coverage = known_area/circle.area
        land_coverage = measured_land/land_area if land_area > 1 else 1.0
        complete = coverage >= 0.9 and land_coverage >= 0.9
        # Density is per complete geometric catchment (including known water),
        # not per shrinking set of populated pixels.
        supported = valid_area > 0 or (complete and water_area > 0)
        density = population / (circle.area / 1e6) if supported else None
        return {'population_density_1km_per_km2': density,
                'population_total': population if supported else None, 'coverage': coverage,
                'land_coverage': land_coverage, 'water_pct': water_area/circle.area*100,
                'observed_population': population,
                'status': 'calculated' if complete else 'incomplete_land_coverage'}


@lru_cache(maxsize=256)
def _render_tile(path, version, z, x, y):
    extent = 20037508.342789244
    span = 2 * extent / (2 ** z)
    bounds = (-extent+x*span, extent-(y+1)*span, -extent+(x+1)*span, extent-y*span)
    target = np.full((256,256), np.nan, dtype=np.float32)
    with rasterio.open(path) as src:
        reproject(source=rasterio.band(src, 1), destination=target,
                  src_transform=src.transform, src_crs=src.crs, src_nodata=src.nodata,
                  dst_transform=from_bounds(*bounds, 256, 256), dst_crs='EPSG:3857',
                  dst_nodata=np.nan,
                  resampling=Resampling.average if z < 11 else Resampling.nearest)
        density = target * (1e6 / abs(src.transform.a * src.transform.e))
    valid = np.isfinite(density) & (density > 0)
    # Fixed discrete breaks, shared with the map legend (people/km²).
    colors = np.array([[255,255,178], [254,204,92], [227,26,28], [128,0,38]], dtype=np.uint8)
    bins = np.digitize(np.where(valid, density, 0), [100,1000,10000])
    rgba = np.zeros((256,256,4), dtype=np.uint8)
    rgba[:,:,:3] = colors[bins]
    rgba[:,:,3] = np.where(valid, 210, 0).astype(np.uint8)
    output = BytesIO()
    Image.fromarray(rgba).save(output, format='PNG')
    return output.getvalue()


def population_tile(z, x, y):
    return _render_tile(str(POPULATION_PATH), POPULATION_PATH.stat().st_mtime_ns, z, x, y)
