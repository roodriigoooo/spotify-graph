"""
taste — overlapping echoes' v2 music-taste similarity engine.

A user is represented as a normalized, distributional object built from recency-weighted
play history (`UserTasteProfile`). Pairs are scored by a calibrated, explainable blend of
near-independent facets:

    artist overlap  ·  genre shape  ·  lyric themes (Word Mover's Distance over whitened
    per-track embeddings, or 2-Wasserstein between per-user Gaussians)

The request path is pure stdlib (Lambda-ready, WASM-portable). Heavy fitting lives in
`taste.fit` (numpy, offline).

Typical use:

    from taste import UserTasteProfile, EngineParams, score_pair
    result = score_pair(profile_a, profile_b, params)
    result["similarity"]   # calibrated percentile shown in the UI
    result["facets"]       # per-facet breakdown for the explanation panel
"""
from .facets import UserTasteProfile, artist_facet, genre_facet, lyric_facet
from .params import EngineParams
from .metric import score_pair
from .whitening import WhiteningParams, apply_whitening
from .calibration import PercentileCalibrator
from .blend import facet_weights, uniform_weights, blend
from .distributions import fit_diag_gaussian, gaussian_w2, gaussian_similarity
from .setmetric import wmd_similarity, wmd_distance, transport_plan, mean_max_alignment
from .aggregation import (
    recency_weight,
    recency_weighted_counts,
    genre_distribution,
    normalize,
    top_items,
    DEFAULT_HALF_LIFE_DAYS,
)

__all__ = [
    "UserTasteProfile", "EngineParams", "score_pair",
    "artist_facet", "genre_facet", "lyric_facet",
    "WhiteningParams", "apply_whitening", "PercentileCalibrator",
    "facet_weights", "uniform_weights", "blend",
    "fit_diag_gaussian", "gaussian_w2", "gaussian_similarity",
    "wmd_similarity", "wmd_distance", "transport_plan", "mean_max_alignment",
    "recency_weight", "recency_weighted_counts", "genre_distribution",
    "normalize", "top_items", "DEFAULT_HALF_LIFE_DAYS",
]
