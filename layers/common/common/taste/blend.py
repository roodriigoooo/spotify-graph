"""
Bayesian facet ensemble.

A single feature is a weak judge of taste; different facets (artist overlap, genre shape,
lyric themes) are near-independent perspectives, each individually valid. So we blend them
— but not with hand-waved 0.5/0.5 weights. Following Saner & Chen's ensemble, weights are
derived from each facet's validation loss and shrunk toward uniform so no single facet
dominates:

    w_f = softmax(-tau * loss_f)

Small `tau` -> nearly uniform (strong shrinkage); large `tau` -> trust the best facet more.
The per-facet scores AND their weights are surfaced to the UI — the blend is also the
explanation.
"""
import math
from typing import Dict, Mapping, Sequence

DEFAULT_TAU = 0.2


def facet_weights(losses: Mapping[str, float], tau: float = DEFAULT_TAU) -> Dict[str, float]:
    """
    Turn per-facet validation losses into normalized ensemble weights via softmax(-tau*loss).
    Lower loss -> higher weight. Empty input -> empty dict.
    """
    if not losses:
        return {}
    keys = list(losses.keys())
    raw = [math.exp(-tau * float(losses[k])) for k in keys]
    total = sum(raw)
    if total <= 0.0:
        return {k: 1.0 / len(keys) for k in keys}
    return {k: r / total for k, r in zip(keys, raw)}


def uniform_weights(keys: Sequence[str]) -> Dict[str, float]:
    if not keys:
        return {}
    w = 1.0 / len(keys)
    return {k: w for k in keys}


def blend(scores: Mapping[str, float], weights: Mapping[str, float]) -> float:
    """
    Weighted blend of facet scores. Only facets present in `scores` participate; their
    weights are renormalized so the result stays in the same [0, 1] range even when a
    facet is missing (e.g. lyric not ready yet).
    """
    present = [k for k in scores if scores[k] is not None]
    if not present:
        return 0.0
    w = {k: weights.get(k, 0.0) for k in present}
    wsum = sum(w.values())
    if wsum <= 0.0:
        w = uniform_weights(present)
        wsum = 1.0
    return sum(scores[k] * w[k] for k in present) / wsum
