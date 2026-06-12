import unittest

import _path  # noqa: F401
from taste.distributions import fit_diag_gaussian, gaussian_w2, gaussian_similarity


class TestDiagGaussian(unittest.TestCase):
    def test_fit_mean_and_var(self):
        vecs = [[0.0, 0.0], [2.0, 0.0], [4.0, 0.0]]
        mean, var = fit_diag_gaussian(vecs)
        self.assertAlmostEqual(mean[0], 2.0)
        self.assertAlmostEqual(mean[1], 0.0)
        # population variance of {0,2,4} = 8/3
        self.assertAlmostEqual(var[0], 8.0 / 3.0, places=6)

    def test_empty(self):
        self.assertEqual(fit_diag_gaussian([]), ([], []))

    def test_w2_identical_is_zero(self):
        g = ([1.0, 2.0], [0.5, 0.5])
        self.assertAlmostEqual(gaussian_w2(g, g), 0.0)

    def test_w2_grows_with_separation(self):
        g1 = ([0.0], [1.0])
        g2 = ([1.0], [1.0])
        g3 = ([5.0], [1.0])
        self.assertLess(gaussian_w2(g1, g2), gaussian_w2(g1, g3))

    def test_similarity_identical_is_one(self):
        g = ([1.0, 2.0], [0.5, 0.5])
        self.assertAlmostEqual(gaussian_similarity(g, g), 1.0)

    def test_similarity_decreases_with_distance(self):
        g1 = ([0.0], [1.0])
        g2 = ([3.0], [1.0])
        self.assertLess(gaussian_similarity(g1, g2), gaussian_similarity(g1, g1))


if __name__ == "__main__":
    unittest.main()
