"""
Set / optimal-transport similarity — Word Mover's Distance.

Instead of crushing a user's tracks into one averaged vector, keep the *set* of per-track
embeddings and compare two sets by how much "mass" has to move to turn one into the other.
This is the Earth Mover's Distance over embeddings — Kusner et al.'s Word Mover's Distance.
It preserves *which* themes overlap, which averaging throws away.

We solve the entropic-regularized transport with Sinkhorn iterations (cheap, differentiable,
GPU-/loop-friendly) — fine here since a user has ≤ ~50 tracks. For large sets we fall back
to a BERTScore-style mean-of-max alignment.

Pure stdlib so it runs on the request path and ports to the Rust/WASM kernel.
"""
import math
from typing import List, Optional, Sequence

from .linalg import cosine, clamp

Vector = List[float]


def _normalize_mass(weights: Optional[Sequence[float]], n: int) -> List[float]:
    if not weights:
        return [1.0 / n] * n
    total = float(sum(weights))
    if total <= 0.0:
        return [1.0 / n] * n
    return [w / total for w in weights]


def cosine_cost_matrix(A: Sequence[Vector], B: Sequence[Vector]) -> List[List[float]]:
    """Pairwise cosine *distance* (1 - cos) in [0, 2]; rows index A, cols index B."""
    return [[1.0 - cosine(a, b) for b in B] for a in A]


def sinkhorn(a: Sequence[float], b: Sequence[float], cost: Sequence[Sequence[float]],
             eps: float = 0.1, iters: int = 50) -> float:
    """
    Entropic optimal transport cost between distributions `a` and `b` under `cost`.

    Returns <T, C>, the transported cost of the converged plan T. `a`, `b` must each sum
    to 1 and match the cost matrix dimensions.
    """
    n, m = len(a), len(b)
    if n == 0 or m == 0:
        return 0.0
    K = [[math.exp(-cost[i][j] / eps) for j in range(m)] for i in range(n)]
    u = [1.0] * n
    v = [1.0] * m
    for _ in range(iters):
        for i in range(n):
            s = 0.0
            for j in range(m):
                s += K[i][j] * v[j]
            u[i] = (a[i] / s) if s > 1e-300 else 0.0
        for j in range(m):
            s = 0.0
            for i in range(n):
                s += K[i][j] * u[i]
            v[j] = (b[j] / s) if s > 1e-300 else 0.0
    cost_total = 0.0
    for i in range(n):
        for j in range(m):
            cost_total += u[i] * K[i][j] * v[j] * cost[i][j]
    return cost_total


def transport_plan(a: Sequence[float], b: Sequence[float], cost: Sequence[Sequence[float]],
                   eps: float = 0.1, iters: int = 50) -> List[List[float]]:
    """The converged coupling matrix T (for visualizing what aligned with what)."""
    n, m = len(a), len(b)
    K = [[math.exp(-cost[i][j] / eps) for j in range(m)] for i in range(n)]
    u = [1.0] * n
    v = [1.0] * m
    for _ in range(iters):
        for i in range(n):
            s = sum(K[i][j] * v[j] for j in range(m))
            u[i] = (a[i] / s) if s > 1e-300 else 0.0
        for j in range(m):
            s = sum(K[i][j] * u[i] for i in range(n))
            v[j] = (b[j] / s) if s > 1e-300 else 0.0
    return [[u[i] * K[i][j] * v[j] for j in range(m)] for i in range(n)]


def wmd_distance(A: Sequence[Vector], B: Sequence[Vector],
                 wa: Optional[Sequence[float]] = None, wb: Optional[Sequence[float]] = None,
                 eps: float = 0.1, iters: int = 50) -> float:
    """Word Mover's Distance between two embedding sets (uses cosine ground cost)."""
    if not A or not B:
        return 1.0
    a = _normalize_mass(wa, len(A))
    b = _normalize_mass(wb, len(B))
    C = cosine_cost_matrix(A, B)
    return sinkhorn(a, b, C, eps, iters)


def mean_max_alignment(A: Sequence[Vector], B: Sequence[Vector]) -> float:
    """
    BERTScore-style soft set similarity in [0, 1]: F1 of precision (each a's best b) and
    recall (each b's best a). Cheap fallback when the sets are too large for Sinkhorn.
    """
    if not A or not B:
        return 0.0
    prec = sum(clamp(max(cosine(a, b) for b in B)) for a in A) / len(A)
    rec = sum(clamp(max(cosine(a, b) for a in A)) for b in B) / len(B)
    if prec + rec == 0.0:
        return 0.0
    return 2.0 * prec * rec / (prec + rec)


def wmd_similarity(A: Sequence[Vector], B: Sequence[Vector],
                   wa: Optional[Sequence[float]] = None, wb: Optional[Sequence[float]] = None,
                   max_set: int = 40, eps: float = 0.1, iters: int = 50) -> float:
    """
    Similarity in [0, 1] from WMD. Cosine ground cost is in [0, 2], so we map the
    transported distance d -> clamp(1 - d/2). Large sets use the alignment fallback.
    """
    if not A or not B:
        return 0.0
    if len(A) > max_set or len(B) > max_set:
        return mean_max_alignment(A, B)
    d = wmd_distance(A, B, wa, wb, eps, iters)
    return clamp(1.0 - 0.5 * d)
