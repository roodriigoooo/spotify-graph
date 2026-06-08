"""
Facets — the near-independent perspectives on taste.

Each facet returns a similarity in [0, 1] for a pair of users. They are deliberately few
and validated (the literature finds most features add noise): artist overlap, genre shape,
lyric themes. Keeping them separate is what lets the UI explain *why* two people match.

A `UserTasteProfile` is the normalized, distributional object the rest of the system speaks
in. It is built once per user (offline / on ingest) from recency-weighted play history.
"""
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .linalg import cosine, l2_normalize, clamp
from .setmetric import wmd_similarity
from .distributions import DiagGaussian, gaussian_similarity


@dataclass
class UserTasteProfile:
    user_id: str = ""
    # recency-weighted artistId -> weight (cold-start artist facet)
    artist_weights: Dict[str, float] = field(default_factory=dict)
    # normalized genre -> probability
    genre_dist: Dict[str, float] = field(default_factory=dict)
    # whitened per-track lyric embeddings + their recency weights (mass for WMD)
    track_embeddings: List[List[float]] = field(default_factory=list)
    track_weights: List[float] = field(default_factory=list)
    # diagonal Gaussian (mean, var) over track_embeddings, for the distribution facet
    gaussian: Optional[DiagGaussian] = None
    # optional learned artist embeddings (artist2vec); None during cold-start
    artist_vectors: Optional[Dict[str, List[float]]] = None


def _weighted_jaccard(a: Dict[str, float], b: Dict[str, float]) -> float:
    keys = set(a) | set(b)
    if not keys:
        return 0.0
    inter = sum(min(a.get(k, 0.0), b.get(k, 0.0)) for k in keys)
    union = sum(max(a.get(k, 0.0), b.get(k, 0.0)) for k in keys)
    return inter / union if union > 0.0 else 0.0


def _sparse_cosine(a: Dict[str, float], b: Dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(a[k] * b[k] for k in a if k in b)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na > 0.0 and nb > 0.0 else 0.0


def _artist_vector(profile: UserTasteProfile) -> Optional[List[float]]:
    """Recency-weighted sum of artist2vec vectors -> a single dense taste-in-artist-space vector."""
    if not profile.artist_vectors or not profile.artist_weights:
        return None
    acc: Optional[List[float]] = None
    for artist_id, w in profile.artist_weights.items():
        vec = profile.artist_vectors.get(artist_id)
        if vec is None:
            continue
        if acc is None:
            acc = [0.0] * len(vec)
        for i, x in enumerate(vec):
            acc[i] += w * x
    return l2_normalize(acc) if acc is not None else None


def artist_facet(a: UserTasteProfile, b: UserTasteProfile) -> float:
    """
    Artist overlap. If learned artist embeddings are present (artist2vec), compare in that
    dense space so adjacent-but-different artists (e.g. bandmates) still draw close.
    Otherwise fall back to weighted Jaccard over raw artist ids (cold-start baseline).
    """
    va, vb = _artist_vector(a), _artist_vector(b)
    if va is not None and vb is not None:
        return clamp(cosine(va, vb))
    return _weighted_jaccard(a.artist_weights, b.artist_weights)


def genre_facet(a: UserTasteProfile, b: UserTasteProfile) -> float:
    """Cosine between recency-weighted genre distributions."""
    return clamp(_sparse_cosine(a.genre_dist, b.genre_dist))


def lyric_facet(a: UserTasteProfile, b: UserTasteProfile, params) -> Optional[float]:
    """
    Lyric-theme similarity over whitened per-track embeddings. Returns None when either
    user has no lyric data yet (so the facet is simply dropped from the blend).

    Two modes (params.lyric_mode):
      - "wmd"      : Word Mover's Distance between the two track-embedding sets (default)
      - "gaussian" : 2-Wasserstein between per-user diagonal Gaussians
    """
    if not a.track_embeddings or not b.track_embeddings:
        return None
    if params.lyric_mode == "gaussian" and a.gaussian and b.gaussian:
        return clamp(gaussian_similarity(a.gaussian, b.gaussian, params.gaussian_scale))
    return clamp(wmd_similarity(
        a.track_embeddings, b.track_embeddings, a.track_weights, b.track_weights,
        eps=params.sinkhorn_eps, iters=params.sinkhorn_iters,
    ))
