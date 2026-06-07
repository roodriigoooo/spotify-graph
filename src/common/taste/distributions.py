"""
A user as a *distribution*, not a point.

The content-based-similarity literature's best classical methods model each song as a
Gaussian / GMM over its frame features and compare the distributions (Aucouturier & Pachet;
the GMM-supervector line). We do the same one level up: model a user as a diagonal Gaussian
over their (whitened) per-track embedding cloud, and compare two users in closed form with
the 2-Wasserstein distance between diagonal Gaussians:

    W2(N1, N2)^2 = ||m1 - m2||^2 + ||sqrt(v1) - sqrt(v2)||^2

This captures both *where* a user's taste sits (mean) and *how spread* it is (variance) —
an eclectic listener and a narrow one differ even with the same mean. Pure stdlib.
"""
import math
from typing import List, Sequence, Tuple

DiagGaussian = Tuple[List[float], List[float]]  # (mean, variance)

_VAR_FLOOR = 1e-6


def fit_diag_gaussian(vectors: Sequence[Sequence[float]]) -> DiagGaussian:
    """Maximum-likelihood diagonal Gaussian (per-dimension mean & variance) over a cloud."""
    n = len(vectors)
    if n == 0:
        return ([], [])
    dim = len(vectors[0])
    mean = [0.0] * dim
    for v in vectors:
        for i in range(dim):
            mean[i] += v[i]
    mean = [m / n for m in mean]
    var = [0.0] * dim
    for v in vectors:
        for i in range(dim):
            d = v[i] - mean[i]
            var[i] += d * d
    var = [max(_VAR_FLOOR, s / n) for s in var]
    return (mean, var)


def gaussian_w2(g1: DiagGaussian, g2: DiagGaussian) -> float:
    """2-Wasserstein distance between two diagonal Gaussians (closed form)."""
    m1, v1 = g1
    m2, v2 = g2
    if not m1 or not m2:
        return float("inf")
    mean_term = sum((a - b) ** 2 for a, b in zip(m1, m2))
    std_term = sum((math.sqrt(a) - math.sqrt(b)) ** 2 for a, b in zip(v1, v2))
    return math.sqrt(mean_term + std_term)


def gaussian_similarity(g1: DiagGaussian, g2: DiagGaussian, scale: float = 1.0) -> float:
    """Map W2 distance to a similarity in (0, 1] via exp(-W2 / scale)."""
    d = gaussian_w2(g1, g2)
    if math.isinf(d):
        return 0.0
    return math.exp(-d / max(scale, 1e-9))
