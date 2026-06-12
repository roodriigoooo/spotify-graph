"""
Offline fitting (numpy) — the only part that isn't pure stdlib.

Run this off the request path (a batch job / scheduled Lambda with a numpy layer) to learn
the population-level parameters, then store the resulting `EngineParams` blob. The request
path never imports this module.

Fits:
  - whitening (PCA whitening with optional "all-but-the-top" component removal)
  - percentile calibrator (from a sample of raw pairwise scores)
  - facet ensemble weights (from per-facet validation losses)
"""
from typing import Dict, Mapping, Optional, Sequence

import numpy as np

from .whitening import WhiteningParams
from .calibration import PercentileCalibrator
from .blend import facet_weights, DEFAULT_TAU


def fit_whitening(vectors: Sequence[Sequence[float]],
                  n_components: Optional[int] = None,
                  remove_top: int = 1,
                  whiten: bool = False) -> WhiteningParams:
    """
    Fit a post-processing transform that de-anisotropizes an embedding population.

    Two modes:

      - **all-but-the-top (default, `whiten=False`)** — Mu & Viswanath's fix: center the
        vectors and *project out* the top `remove_top` principal directions (the dominant
        common direction that inflates every cosine), keeping all remaining axes at their
        natural scale. This is the right default: it strips the anisotropy without
        amplifying low-variance noise directions, so genuine signal survives.

      - **full PCA-whitening (`whiten=True`)** — additionally rescale each kept axis to unit
        variance and (optionally) reduce dimensionality to `n_components`. Stronger
        isotropy, but it equalizes signal and noise — only use when the residual dimensions
        are all meaningful.

    Args:
        vectors: the embedding population (n x d).
        n_components: kept axes for `whiten=True` (default: all remaining).
        remove_top: number of leading principal components to drop.
        whiten: rescale to unit variance (True) vs. project-out only (False).

    Returns:
        WhiteningParams whose `apply` maps a raw embedding into the de-anisotropized space.
    """
    X = np.asarray(vectors, dtype=np.float64)
    if X.ndim != 2 or X.shape[0] < 2:
        return WhiteningParams()
    d = X.shape[1]
    mean = X.mean(axis=0)
    Xc = X - mean
    # covariance eigendecomposition (symmetric -> eigh), descending eigenvalues
    cov = (Xc.T @ Xc) / (X.shape[0] - 1)
    eigvals, eigvecs = np.linalg.eigh(cov)
    order = np.argsort(eigvals)[::-1]
    eigvals, eigvecs = eigvals[order], eigvecs[:, order]

    if whiten:
        start = max(0, remove_top)
        end = d if n_components is None else min(d, start + n_components)
        keep = slice(start, end)
        vals = np.clip(eigvals[keep], 1e-12, None)
        vecs = eigvecs[:, keep]                    # d x k
        W = (vecs / np.sqrt(vals)).T               # k x d, rows scaled by 1/sqrt(eigenvalue)
    else:
        # all-but-the-top: W = I - U_top U_top^T  (project out the common direction(s))
        U = eigvecs[:, :max(0, remove_top)]        # d x r
        W = np.eye(d) - U @ U.T                    # d x d, no rescaling
    return WhiteningParams(mean=mean.tolist(), components=W.tolist())


def fit_calibration(raw_scores: Sequence[float], max_samples: int = 4096) -> PercentileCalibrator:
    """Build a percentile calibrator from a sample of raw pairwise scores."""
    arr = np.asarray(list(raw_scores), dtype=np.float64)
    if arr.size > max_samples:
        idx = np.linspace(0, arr.size - 1, max_samples).astype(int)
        arr = np.sort(arr)[idx]
    return PercentileCalibrator.fit(arr.tolist())


def fit_facet_weights(losses: Mapping[str, float], tau: float = DEFAULT_TAU) -> Dict[str, float]:
    """Ensemble weights from per-facet validation losses (softmax(-tau*loss))."""
    return facet_weights(losses, tau)
