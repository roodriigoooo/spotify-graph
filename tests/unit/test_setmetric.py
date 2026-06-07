import unittest

import _path  # noqa: F401
from taste.setmetric import (
    sinkhorn,
    transport_plan,
    cosine_cost_matrix,
    wmd_similarity,
    wmd_distance,
    mean_max_alignment,
)


class TestSinkhorn(unittest.TestCase):
    def test_identical_sets_near_zero_distance(self):
        A = [[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]]
        d = wmd_distance(A, A, eps=0.05, iters=200)
        self.assertLess(d, 0.05)

    def test_identical_sets_high_similarity(self):
        A = [[1.0, 0.0], [0.0, 1.0]]
        self.assertGreater(wmd_similarity(A, A, eps=0.05, iters=200), 0.9)

    def test_transport_plan_conserves_mass(self):
        A = [[1.0, 0.0], [0.0, 1.0]]
        B = [[1.0, 0.1], [0.1, 1.0], [0.5, 0.5]]
        a = [0.5, 0.5]
        b = [1 / 3, 1 / 3, 1 / 3]
        C = cosine_cost_matrix(A, B)
        T = transport_plan(a, b, C, eps=0.05, iters=300)
        total = sum(sum(row) for row in T)
        self.assertAlmostEqual(total, 1.0, places=2)
        for i, row in enumerate(T):
            self.assertAlmostEqual(sum(row), a[i], places=2)

    def test_orthogonal_less_than_identical(self):
        A = [[1.0, 0.0], [1.0, 0.0]]
        B = [[0.0, 1.0], [0.0, 1.0]]
        self.assertLess(wmd_similarity(A, B), wmd_similarity(A, A))

    def test_empty_sets(self):
        self.assertEqual(wmd_similarity([], [[1.0]]), 0.0)


class TestMeanMaxAlignment(unittest.TestCase):
    def test_identical_is_one(self):
        A = [[1.0, 0.0], [0.0, 1.0]]
        self.assertAlmostEqual(mean_max_alignment(A, A), 1.0, places=6)

    def test_large_set_falls_back(self):
        # > max_set triggers the alignment fallback rather than Sinkhorn
        A = [[1.0, 0.0]] * 50
        B = [[1.0, 0.0]] * 50
        self.assertGreater(wmd_similarity(A, B, max_set=40), 0.9)


if __name__ == "__main__":
    unittest.main()
