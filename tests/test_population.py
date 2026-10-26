"""Numerical and HTTP checks for population integration; no database writes."""
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np
import rasterio
from PIL import Image
from pyproj import Transformer
from rasterio.transform import from_origin
from django.test import SimpleTestCase, RequestFactory

from services.models.features.population import _catchment, _render_tile
from services.models.similarity.gower_distance import GowerDistance
from services.models.similarity.engine import rank_similar_cases
from core.views.population_views import tile


class PopulationTests(SimpleTestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'population.tif'
        self.x, self.y = Transformer.from_crs('EPSG:4326', 'EPSG:32632', always_xy=True).transform(9, 35)

    def write_grid(self, value):
        with rasterio.open(self.path, 'w', driver='GTiff', width=60, height=60,
                           count=1, dtype='float32', crs='EPSG:32632', nodata=-200,
                           transform=from_origin(self.x-3000, self.y+3000, 100, 100)) as dst:
            dst.write(np.full((60,60), value, dtype=np.float32), 1)

    def test_fractional_overlap_preserves_uniform_density(self):
        self.write_grid(10)  # Ten residents per 0.01 km² = 1,000/km².
        result = _catchment(str(self.path), 1, 35, 9)
        self.assertAlmostEqual(result['population_density_1km_per_km2'], 1000, places=6)

    def test_zero_is_measured_and_nodata_is_unknown(self):
        self.write_grid(0)
        self.assertEqual(_catchment(str(self.path), 2, 35, 9)['population_density_1km_per_km2'], 0)
        self.write_grid(-200)
        self.assertIsNone(_catchment(str(self.path), 3, 35, 9)['population_density_1km_per_km2'])

    def test_population_changes_ranking(self):
        key = 'population_density_1km_per_km2'
        self.assertIn(key, GowerDistance.NUMERIC_FEATURES)
        result = rank_similar_cases({key: 1000}, [{key: 900}, {key: 10000}], k=2, selected_features=[key])
        self.assertEqual(result['cases'][0]['candidate_index'], 0)
        self.assertGreater(result['cases'][0]['weight'], result['cases'][1]['weight'])

    def test_coastal_water_does_not_hide_calculated_population(self):
        self.write_grid(10)
        with rasterio.open(self.path, 'r+') as src:
            data = src.read(1)
            data[:,30:] = -200
            src.write(data, 1)
        def water(crs, grid, shape):
            # Right-hand half is independently confirmed water.
            mask = np.zeros(shape, dtype=bool)
            for col in range(shape[1]):
                mask[:,col] = (grid * (col+0.5, 0))[0] > self.x
            return mask
        with patch('services.models.features.population.water_cells', side_effect=water):
            result = _catchment(str(self.path), 20, 35, 9)
        self.assertEqual(result['status'], 'calculated')
        self.assertAlmostEqual(result['land_coverage'], 1, places=4)
        self.assertAlmostEqual(result['population_density_1km_per_km2'], 500, places=4)

    def test_partial_land_reports_mapped_count_without_inventing_residents(self):
        self.write_grid(10)
        with rasterio.open(self.path, 'r+') as src:
            data = src.read(1)
            data[:,30:] = -200
            src.write(data, 1)
        with patch('services.models.features.population.water_cells', side_effect=lambda crs, grid, shape: np.zeros(shape, dtype=bool)):
            result = _catchment(str(self.path), 21, 35, 9)
        self.assertEqual(result['status'], 'incomplete_land_coverage')
        self.assertAlmostEqual(result['land_coverage'], .5, places=4)
        self.assertGreater(result['population_total'], 0)
        self.assertEqual(result['population_total'], result['observed_population'])

    def test_tier_population_is_counted_in_separate_catchments(self):
        # A uniform source makes the annulus/disk population ratio testable.
        with rasterio.open(self.path, 'w', driver='GTiff', width=160, height=160,
                           count=1, dtype='float32', crs='EPSG:32632', nodata=-200,
                           transform=from_origin(self.x-8000, self.y+8000, 100, 100)) as dst:
            dst.write(np.full((160,160), 10, dtype=np.float32), 1)
        t1 = _catchment(str(self.path), 10, 35, 9, radius=2000)
        t2 = _catchment(str(self.path), 10, 35, 9, radius=5000, inner_radius=2000)
        self.assertAlmostEqual(t2['population_total']/t1['population_total'], (25-4)/4, places=4)
        for key in ('population_tier1', 'population_tier2'):
            self.assertIn(key, GowerDistance.NUMERIC_FEATURES)
            ranked = rank_similar_cases({key: 100}, [{key: 110}, {key: 9000}], k=2, selected_features=[key])
            self.assertEqual(ranked['cases'][0]['candidate_index'], 0)

    def test_tile_outside_coverage_is_transparent_png(self):
        self.write_grid(10)
        png = _render_tile(str(self.path), 4, 4, 0, 0)
        image = Image.open(BytesIO(png))
        self.assertEqual(image.size, (256,256))
        self.assertEqual(np.asarray(image)[:,:,3].max(), 0)

    def test_populated_tile_has_visible_pixels(self):
        import math
        self.write_grid(10)
        zoom = 12
        x = int((9 + 180) / 360 * 2**zoom)
        y = int((1 - math.asinh(math.tan(math.radians(35))) / math.pi) / 2 * 2**zoom)
        png = _render_tile(str(self.path), 5, zoom, x, y)
        self.assertGreater(np.asarray(Image.open(BytesIO(png)))[:,:,3].max(), 0)

    def test_invalid_tile_rejected_and_missing_raster_reported(self):
        request = RequestFactory().get('/population/test')
        self.assertEqual(tile(request, 19, 0, 0).status_code, 400)
        with patch('core.views.population_views.population_tile', side_effect=FileNotFoundError):
            self.assertEqual(tile(request, 12, 1, 1).status_code, 503)
