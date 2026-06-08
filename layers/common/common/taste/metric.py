"""
score_pair — the one function the rest of the app calls.

Given two `UserTasteProfile`s and the fitted `EngineParams`, compute every facet, blend
them with the ensemble weights, and calibrate to a percentile. Returns the blended score
*and* the per-facet breakdown + weights — everything the edge-breakdown UI needs to explain
the match. This is intentionally the whole public surface: data in, honest number + reasons
out.
"""
from typing import Dict

from .facets import UserTasteProfile, artist_facet, genre_facet, lyric_facet
from .blend import blend, uniform_weights
from .params import EngineParams


def score_pair(a: UserTasteProfile, b: UserTasteProfile, params: EngineParams = None) -> Dict:
    """
    Returns:
        {
          "facets":     {facet: score in [0,1]},   # only facets that applied
          "weights":    {facet: weight},           # weights actually used
          "blended":    raw blended score in [0,1],
          "similarity": calibrated percentile in [0,1],   # what the UI shows
        }
    """
    params = params or EngineParams()

    facets: Dict[str, float] = {
        "artist": artist_facet(a, b),
        "genre": genre_facet(a, b),
    }
    ly = lyric_facet(a, b, params)
    if ly is not None:
        facets["lyric"] = ly

    weights = params.weights or uniform_weights(list(facets))
    raw = blend(facets, weights)
    similarity = (params.calibrator.to_percentile(raw)
                  if params.calibrator and not params.calibrator.is_empty else raw)

    used = {k: weights.get(k, 0.0) for k in facets}
    return {"facets": facets, "weights": used, "blended": raw, "similarity": similarity}
