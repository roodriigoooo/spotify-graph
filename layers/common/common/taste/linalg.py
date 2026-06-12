"""
Tiny pure-Python linear-algebra helpers.

Deliberately dependency-free (no numpy). The request-path engine must deploy to Lambda
without extra layers and port cleanly to the Rust/WASM kernel, so every hot-path
operation lives here in plain Python. Vectors are ``list[float]``; matrices are
``list[list[float]]`` (row-major).
"""
import math
from typing import List, Sequence

Vector = List[float]
Matrix = List[List[float]]


def dot(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def norm(a: Sequence[float]) -> float:
    return math.sqrt(dot(a, a))


def add(a: Sequence[float], b: Sequence[float]) -> Vector:
    return [x + y for x, y in zip(a, b)]


def sub(a: Sequence[float], b: Sequence[float]) -> Vector:
    return [x - y for x, y in zip(a, b)]


def scale(a: Sequence[float], s: float) -> Vector:
    return [x * s for x in a]


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity in [-1, 1]; 0.0 if either vector is degenerate."""
    na, nb = norm(a), norm(b)
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot(a, b) / (na * nb)


def cosine_distance(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine distance in [0, 2]."""
    return 1.0 - cosine(a, b)


def mean_vector(vectors: Sequence[Sequence[float]]) -> Vector:
    if not vectors:
        return []
    dim = len(vectors[0])
    acc = [0.0] * dim
    for v in vectors:
        for i, x in enumerate(v):
            acc[i] += x
    n = len(vectors)
    return [x / n for x in acc]


def matvec(matrix: Matrix, vec: Sequence[float]) -> Vector:
    """Matrix-vector product. ``matrix`` is row-major; result has len == #rows."""
    return [dot(row, vec) for row in matrix]


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if x < lo else hi if x > hi else x


def l2_normalize(a: Sequence[float]) -> Vector:
    n = norm(a)
    if n == 0.0:
        return list(a)
    return [x / n for x in a]
