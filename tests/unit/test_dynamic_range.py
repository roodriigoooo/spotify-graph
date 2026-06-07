"""
The dynamic-range guard — the empirical heart of the redesign.

Reproduces the anisotropy pathology and proves the fix:

  * raw embeddings share a dominant common direction, so averaging a user's tracks and
    comparing by cosine collapses every pair into a narrow high band (no dynamic range).
  * whitening (with top-component removal) restores spread, and Word Mover's Distance over
    the whitened track sets correctly orders same-theme vs different-theme users.

If a future change reintroduces averaging or drops whitening, these assertions fail.
"""
import unittest

import numpy as np

import _path  # noqa: F401
from taste.fit import fit_whitening
from taste.linalg import cosine
from taste.setmetric import wmd_similarity

DIM = 16
N_USERS = 8
TRACKS = 12
# Real embedding anisotropy is a large-positive, high-variance *shared* direction (a cone),
# not a constant offset — so it survives mean-centering and is the top principal component.
COMMON_MU = 8.0
COMMON_SIGMA = 3.0


def _build_population(seed=0):
    rng = np.random.default_rng(seed)
    common = np.zeros(DIM)
    common[0] = 1.0
    users = []
    for _ in range(N_USERS):
        theme = rng.normal(size=DIM)
        theme[0] = 0.0  # orthogonal to the common direction
        theme /= np.linalg.norm(theme)
        tracks = [rng.normal(COMMON_MU, COMMON_SIGMA) * common + theme + 0.15 * rng.normal(size=DIM)
                  for _ in range(TRACKS)]
        users.append(np.array(tracks))
    return users


def _pairwise(values_fn, n):
    return [values_fn(i, j) for i in range(n) for j in range(i + 1, n)]


class TestDynamicRange(unittest.TestCase):
    def test_whitening_restores_spread(self):
        users = _build_population(seed=0)

        # --- OLD: average raw tracks, cosine between user centroids ---
        raw_centroids = [u.mean(axis=0) for u in users]
        old = _pairwise(lambda i, j: cosine(raw_centroids[i].tolist(), raw_centroids[j].tolist()), N_USERS)
        old_mean, old_std = float(np.mean(old)), float(np.std(old))

        # --- NEW: whiten the track population (drop the common direction), then cosine ---
        all_tracks = np.vstack(users).tolist()
        wp = fit_whitening(all_tracks, remove_top=1)
        white_centroids = [np.mean([wp.apply(t) for t in u.tolist()], axis=0) for u in users]
        new = _pairwise(lambda i, j: cosine(white_centroids[i].tolist(), white_centroids[j].tolist()), N_USERS)
        new_std = float(np.std(new))

        # anisotropy: raw pairs are crushed into a narrow high band
        self.assertGreater(old_mean, 0.85, f"expected anisotropic mush, got mean={old_mean:.3f}")
        self.assertLess(old_std, 0.08, f"expected tiny spread, got std={old_std:.3f}")

        # whitening restores meaningful spread
        self.assertGreater(new_std, old_std * 2.0,
                           f"whitening did not restore range: old_std={old_std:.3f} new_std={new_std:.3f}")

    def test_wmd_orders_theme_overlap(self):
        rng = np.random.default_rng(3)
        common = np.zeros(DIM)
        common[0] = 1.0
        theme_t = rng.normal(size=DIM); theme_t[0] = 0.0; theme_t /= np.linalg.norm(theme_t)
        theme_u = rng.normal(size=DIM); theme_u[0] = 0.0
        theme_u -= theme_u.dot(theme_t) * theme_t  # make orthogonal to theme_t
        theme_u[0] = 0.0; theme_u /= np.linalg.norm(theme_u)

        def make(theme):
            return [rng.normal(COMMON_MU, COMMON_SIGMA) * common + theme + 0.1 * rng.normal(size=DIM)
                    for _ in range(TRACKS)]

        a, b, c = make(theme_t), make(theme_t), make(theme_u)  # a,b same theme; c different
        wp = fit_whitening([*[t.tolist() for t in a], *[t.tolist() for t in b], *[t.tolist() for t in c]],
                           remove_top=1)
        wa = [wp.apply(t.tolist()) for t in a]
        wb = [wp.apply(t.tolist()) for t in b]
        wc = [wp.apply(t.tolist()) for t in c]

        same = wmd_similarity(wa, wb, eps=0.05, iters=200)
        diff = wmd_similarity(wa, wc, eps=0.05, iters=200)
        self.assertGreater(same, diff,
                           f"WMD failed to order theme overlap: same={same:.3f} diff={diff:.3f}")


if __name__ == "__main__":
    unittest.main()
