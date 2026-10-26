from datetime import date
from types import SimpleNamespace
import geopandas as gpd
from shapely.geometry import LineString
from django.test import SimpleTestCase

from services.models.features.road_loader import ROAD_FIELDS, road_config
from services.models.features.road_features import RoadFeatureExtractor, PROJECT, road_similarity_values
from services.models.similarity.gower_distance import GowerDistance
from services.models.similarity.engine import rank_similar_cases
from services.models.similarity.weighting import pair_weights
from tempfile import TemporaryDirectory
from pathlib import Path
from zipfile import ZipFile
from unittest.mock import patch


class RoadCalculationTests(SimpleTestCase):
    def fixture(self, lines, classes, bridges=None):
        x,y = PROJECT.transform(9,35)
        roads = gpd.GeoDataFrame({
            'highway':classes, 'bridge': bridges or ['F']*len(lines),
            'tunnel':['F']*len(lines), 'layer':[0]*len(lines),
        }, geometry=[LineString([(x+a,y+b) for a,b in line]) for line in lines], crs=32632)
        return RoadFeatureExtractor(roads, manifest={'source':'test','source_hash':'hash','osm_extract_date':None})

    def test_weighted_length_and_junctions(self):
        extractor = self.fixture([[(-2000,0),(2000,0)],[(0,-2000),(0,2000)]], ['primary','residential'])
        values = extractor.extract(35,9)
        self.assertAlmostEqual(values['road_km_total'],4,places=5)
        self.assertAlmostEqual(values['road_km_weighted'],1.6,places=5)
        self.assertAlmostEqual(values['road_density_weighted_km_km2'],1.6/(3.1412772509),places=5)
        self.assertEqual(values['n_road_intersections'],1)
        self.assertEqual(values['dominant_road_class'],'primary')
        self.assertEqual(values['highway_share'],0)

    def test_grade_separated_crossing_is_not_a_junction(self):
        e = self.fixture([[(-2000,0),(2000,0)],[(0,-2000),(0,2000)]],['primary','secondary'],['F','T'])
        self.assertEqual(e.extract(35,9)['n_road_intersections'],0)

    def test_missing_vs_known_zero(self):
        e = self.fixture([[(3000,0),(3100,0)]],['track'])
        known = e.extract(35,9)
        self.assertEqual(known['road_km_total'],0)
        self.assertIsNone(known['highway_share'])
        self.assertIsNone(known['dominant_road_class'])
        e = self.fixture([[(10000,0),(10100,0)]],['primary'])
        unknown = e.extract(35,9)
        self.assertTrue(all(unknown[f] is None for f in ROAD_FIELDS))

    def test_highway_share(self):
        e = self.fixture([[(-2000,0),(2000,0)],[(0,-2000),(0,2000)]],['motorway','residential'])
        self.assertAlmostEqual(e.extract(35,9)['highway_share'],.5)

    def test_undated_snapshot_cannot_enter_historical_prediction(self):
        row = SimpleNamespace(**{f:1 for f in ROAD_FIELDS}, osm_extract_date=None,
                              source_hash='a', buffer_m=1000, method_version='v1', weights_version='w1')
        self.assertTrue(all(v is None for v in road_similarity_values(row,date(2025,1,1)).values()))
        self.assertEqual(road_similarity_values(row,date(2025,1,1),allow_current=True)['road_km_total'],1)

    def test_source_date_is_verified_against_matching_archive(self):
        from services.models.features.road_loader import prepare_roads
        with TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root/'data/geographic/osm'
            folder.mkdir(parents=True)
            source = folder/'tunisia.gpkg'
            gpd.GeoDataFrame({'osm_id':['1'],'fclass':['motorway_link']},geometry=[LineString([(9,35),(9.01,35)])],crs=4326).to_file(source,layer='gis_osm_roads_free')
            with ZipFile(folder/'tunisia-latest-free.gpkg.zip','w') as archive:
                archive.writestr('README','OpenStreetMap data as of 2026-10-22T20:21:33Z')
                archive.write(source,arcname='tunisia.gpkg')
            with patch('services.models.features.road_loader.ROOT',root):
                manifest = prepare_roads(source)
                self.assertEqual(manifest['osm_extract_date'],'2026-10-22')
                self.assertIn('verified',manifest['date_status'])
                normalized = gpd.read_file(manifest['normalized_path'],layer='roads')
                self.assertEqual(normalized.highway.iloc[0],'motorway')
                self.assertEqual(normalized.crs.to_epsg(),32632)
                with self.assertRaises(ValueError):
                    prepare_roads(source,extract_date='2026-01-01')


class RoadWeightTests(SimpleTestCase):
    def setUp(self):
        self.gower = GowerDistance()
        self.query = {'road_km_total':10,'highway_km':5,'n_sites_2km':10,'n_sites_1km':4,
                      'population_tier1':100,'road_context_signature':'same'}
        self.case = {**self.query,'road_km_total':100}

    def test_unselected_roads_contribute_nothing(self):
        a = rank_similar_cases(self.query,[self.case],selected_features=['n_sites_2km'])['cases'][0]
        self.assertNotIn('road_km_total',a['feature_weights'])
        self.assertEqual(a['distance'],0)

    def test_group_weights_are_normalized_over_available_selected_features(self):
        weights = pair_weights(self.gower,self.query,self.case,['n_sites_2km','n_sites_1km','population_tier1','pre_cqi_avg'],'equal_per_group')
        self.assertAlmostEqual(sum(weights.values()),1)
        self.assertEqual(weights['population_tier1'],.5)
        self.assertEqual(weights['n_sites_2km'],.25)
        self.assertNotIn('pre_cqi_avg',weights)

    def test_road_group_cannot_dominate_either_mode(self):
        for mode in ('equal_per_feature','equal_per_group'):
            weights = pair_weights(self.gower,self.query,self.case,list(self.gower.NUMERIC_FEATURES),mode)
            self.assertAlmostEqual(sum(weights.values()),1)
            self.assertLessEqual(sum(w for f,w in weights.items() if f in ROAD_FIELDS),.050000001)

    def test_mismatched_context_has_no_road_weight(self):
        weights = pair_weights(self.gower,self.query,{**self.case,'road_context_signature':'different'},['road_km_total','n_sites_2km'],'equal_per_group')
        self.assertNotIn('road_km_total',weights)

    def test_roads_only_does_not_become_full_weight(self):
        self.assertEqual(pair_weights(self.gower,self.query,self.case,['road_km_total'],'equal_per_group'),{})


from django.test import TestCase
from unittest.mock import patch
from types import SimpleNamespace
from core.models import Site, RoadFeatures


class RoadPipelineTests(TestCase):
    def test_feature_pipeline_persists_roads_and_reports_site_progress(self):
        from services.models.features.pipeline import FeatureExtractionPipeline
        site = Site.objects.create(site_id='fixture',site_name='fixture',latitude=35,longitude=9,location='')
        extractor = RoadCalculationTests().fixture([[(-2000,0),(2000,0)]],['primary'])
        module = 'services.models.features.pipeline.'
        with patch(module+'GeometricFeatureExtractor') as geometry, patch(module+'ClutterFeatureExtractor') as clutter, patch(module+'RoadFeatureExtractor',return_value=extractor):
            geometry.return_value.extract_features.return_value = SimpleNamespace(success=True)
            geometry.return_value.to_dict.return_value = {'z_antenna_m':1,'terrain_slope_deg':1,'terrain_roughness_m':1,'terrain_aspect_deg':1}
            clutter.return_value.extract_features.return_value = SimpleNamespace(success=True)
            clutter.return_value.to_dict.return_value = {'dominant_clutter':'rural','clutter_entropy_2km':1,'pct_building_area_1km':0,'avg_building_height_m':0}
            progress = []
            result = FeatureExtractionPipeline().extract_and_save_features(skip_existing=False,progress_callback=progress.append)
        self.assertEqual(result['successful'],1)
        self.assertEqual(result['road_computed'],1)
        self.assertAlmostEqual(RoadFeatures.objects.get(site=site).road_km_total,2)
        self.assertEqual(progress[-1]['processed'],1)
