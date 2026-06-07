import unittest

import _path  # noqa: F401
from taste.calibration import PercentileCalibrator


class TestCalibration(unittest.TestCase):
    def setUp(self):
        self.calib = PercentileCalibrator.fit([i / 100.0 for i in range(101)])

    def test_median_is_half(self):
        self.assertAlmostEqual(self.calib.to_percentile(0.5), 0.5, delta=0.02)

    def test_monotonic(self):
        self.assertLess(self.calib.to_percentile(0.2), self.calib.to_percentile(0.8))

    def test_extremes(self):
        self.assertLessEqual(self.calib.to_percentile(-1.0), 0.01)
        self.assertGreaterEqual(self.calib.to_percentile(2.0), 0.99)

    def test_empty_is_passthrough(self):
        self.assertEqual(PercentileCalibrator().to_percentile(0.42), 0.42)

    def test_dict_round_trip(self):
        d = self.calib.to_dict()
        restored = PercentileCalibrator.from_dict(d)
        self.assertEqual(restored.sorted_samples, self.calib.sorted_samples)


if __name__ == "__main__":
    unittest.main()
