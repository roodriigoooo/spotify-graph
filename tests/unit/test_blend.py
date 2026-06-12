import unittest

import _path  # noqa: F401
from taste.blend import facet_weights, uniform_weights, blend


class TestFacetWeights(unittest.TestCase):
    def test_lower_loss_gets_more_weight(self):
        w = facet_weights({"a": 0.1, "b": 0.9})
        self.assertGreater(w["a"], w["b"])

    def test_weights_sum_to_one(self):
        w = facet_weights({"a": 0.1, "b": 0.9, "c": 0.5})
        self.assertAlmostEqual(sum(w.values()), 1.0)

    def test_small_tau_approaches_uniform(self):
        w = facet_weights({"a": 0.0, "b": 10.0}, tau=0.001)
        self.assertAlmostEqual(w["a"], 0.5, delta=0.02)

    def test_empty(self):
        self.assertEqual(facet_weights({}), {})


class TestBlend(unittest.TestCase):
    def test_uniform_average(self):
        self.assertAlmostEqual(blend({"a": 0.8, "b": 0.4}, uniform_weights(["a", "b"])), 0.6)

    def test_missing_facet_renormalizes(self):
        # lyric weight present but facet absent -> remaining weight renormalized
        weights = {"artist": 0.3, "genre": 0.3, "lyric": 0.4}
        self.assertAlmostEqual(blend({"artist": 1.0}, weights), 1.0)

    def test_respects_weighting(self):
        score = blend({"a": 1.0, "b": 0.0}, {"a": 0.9, "b": 0.1})
        self.assertAlmostEqual(score, 0.9)

    def test_no_facets_is_zero(self):
        self.assertEqual(blend({}, {"a": 1.0}), 0.0)


if __name__ == "__main__":
    unittest.main()
