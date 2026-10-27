import numpy as np
import shapely
from shapely.geometry import Point
from django.test import SimpleTestCase
from services.models.features.population import intersection_areas


class PopulationIntersectionTests(SimpleTestCase):
    def test_prepared_pixel_areas_match_exact_full_overlay_for_circle_and_ring(self):
        x,y=np.meshgrid(np.arange(-6,6),np.arange(-6,6))
        cells=shapely.box(x.ravel(),y.ravel(),x.ravel()+1,y.ravel()+1)
        circle=Point(.3,.2).buffer(5,resolution=64)
        for shape in (circle,circle.difference(Point(.3,.2).buffer(2,resolution=64))):
            expected=shapely.area(shapely.intersection(cells,shape))
            np.testing.assert_allclose(intersection_areas(cells,shape,1.),expected,rtol=1e-12,atol=1e-12)
