import unittest

import numpy as np

import _path  # noqa: F401
from taste.whitening import WhiteningParams, apply_whitening
from taste.fit import fit_whitening


class TestWhiteningApply(unittest.TestCase):
    def test_identity_passthrough(self):
        self.assertEqual(WhiteningParams().apply([1.0, 2.0, 3.0]), [1.0, 2.0, 3.0])

    def test_known_transform(self):
        p = WhiteningParams(mean=[0.0, 0.0], components=[[1.0, 0.0], [0.0, 2.0]])
        self.assertEqual(p.apply([3.0, 4.0]), [3.0, 8.0])

    def test_centering(self):
        p = WhiteningParams(mean=[1.0, 1.0], components=[[1.0, 0.0], [0.0, 1.0]])
        self.assertEqual(p.apply([3.0, 5.0]), [2.0, 4.0])

    def test_dict_round_trip(self):
        p = WhiteningParams(mean=[0.5], components=[[2.0]])
        q = WhiteningParams.from_dict(p.to_dict())
        self.assertEqual(q.mean, p.mean)
        self.assertEqual(q.components, p.components)


class TestWhiteningFit(unittest.TestCase):
    def test_full_whiten_produces_unit_variance(self):
        rng = np.random.default_rng(0)
        # correlated, differently-scaled gaussian blob
        cov = np.array([[4.0, 1.5], [1.5, 1.0]])
        X = rng.multivariate_normal([0, 0], cov, size=400)
        params = fit_whitening(X.tolist(), remove_top=0, whiten=True)
        W = np.array([params.apply(x) for x in X.tolist()])
        # full whitening: whitened coordinates have ~unit variance per dimension
        for v in W.var(axis=0):
            self.assertAlmostEqual(v, 1.0, delta=0.2)

    def test_full_whiten_remove_top_drops_a_dimension(self):
        rng = np.random.default_rng(1)
        X = rng.normal(size=(200, 6))
        params = fit_whitening(X.tolist(), remove_top=1, whiten=True)
        # one fewer output dimension than input when the top component is removed
        self.assertEqual(len(params.components), 5)

    def test_abtt_projects_out_top_direction(self):
        # default (all-but-the-top): a strong common direction is removed, dimensionality kept
        rng = np.random.default_rng(2)
        common = np.zeros(8); common[0] = 1.0
        X = np.array([6.0 * common + rng.normal(scale=0.3, size=8) for _ in range(300)])
        params = fit_whitening(X.tolist(), remove_top=1)  # whiten=False
        self.assertEqual(len(params.components), 8)        # square: dimensionality preserved
        # after projecting out the top direction, residual energy along it is ~0
        projections = [params.apply(x)[0] for x in X.tolist()]
        self.assertLess(float(np.var(projections)), 0.05)


if __name__ == "__main__":
    unittest.main()
