from datetime import date
from unittest.mock import patch
from django.test import SimpleTestCase
from services.models.prediction.cbr_impact import (
    _baseline_scope, _cohort_observed, _group_series, _prediction_values,
)


class CBRCohortTests(SimpleTestCase):
    def history(self):
        return {site: {date(2025,month,1): {'traffic_bits': value*8e9}
                       for month,value in zip((1,2,3), values)}
                for site,values in [('a',(1,100,100)), ('b',(100,1,100))]}

    def test_sum_uses_sum_of_recipient_medians(self):
        self.assertEqual(_baseline_scope(['a','b'], date(2025,4,1), self.history(), 'downlink_traffic_gb'), 200)

    def test_nonadditive_observation_matches_mean_site_change_definition(self):
        data = {'a': {date(2025,4,1): {'cqi_weighted_total': 100, 'cqi_sample_count': 100}},
                'b': {date(2025,4,1): {'cqi_weighted_total': 15, 'cqi_sample_count': 1}}}
        value, count = _cohort_observed(['a','b'], date(2025,4,1), data, 'cqi_avg')
        self.assertEqual(value, 8)
        self.assertEqual(count, 2)

    def test_missing_recipient_produces_gap_not_partial_total(self):
        data = self.history()
        data['a'][date(2025,4,1)] = {'traffic_bits': 150*8e9}
        with patch('services.models.prediction.cbr_impact._predict_delta', return_value=(2,-3,3,2)):
            points = _group_series('tier1', ['a','b'], date(2025,4,1), data, {}, [])['downlink_traffic_gb']
        point = next(p for p in points if p['offset']==0)
        self.assertIsNone(point['observed'])
        self.assertEqual(point['observed_sites'], 1)
        self.assertEqual(point['eligible_sites'], 2)
        self.assertEqual(point['predicted'], 204)

    def test_absolute_prediction_and_interval_respect_physical_bounds(self):
        self.assertEqual(_prediction_values(100,-200,-300,-100,'downlink_traffic_gb'), (0,-100,0,0))
        self.assertEqual(_prediction_values(14,4,2,6,'cqi_avg'), (15,1,15,15))
