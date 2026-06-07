"""
Whitening — the fix that makes cosine mean something again.

Off-the-shelf sentence/lyric embeddings are badly *anisotropic*: they pile into a narrow
cone, so two unrelated texts still score ~0.9–0.99 cosine. Averaging a user's lyrics into
one vector and comparing by cosine therefore has almost no dynamic range — everyone looks
identical. Whitening removes the shared common direction(s) and rescales the axes so the
space is isotropic and cosine is geometrically honest again.

Fitting (eigendecomposition over the track-embedding population) happens offline in
`fit.py` with numpy. This module only *applies* a fitted transform, in pure stdlib, so it
runs on the request path and ports to WASM.

    whitened(x) = W · (x - mean)

where rows of W are (optionally top-k) principal directions scaled by 1/sqrt(eigenvalue).
Setting `remove_top` during fit drops the dominant component(s) — the "all-but-the-top"
trick — which is what kills the anisotropy.
"""
from dataclasses import dataclass, field
from typing import List, Sequence

from .linalg import sub, matvec


@dataclass
class WhiteningParams:
    """Fitted whitening transform. `components` is row-major (k x d)."""
    mean: List[float] = field(default_factory=list)
    components: List[List[float]] = field(default_factory=list)

    @property
    def is_identity(self) -> bool:
        return not self.components or not self.mean

    def apply(self, vec: Sequence[float]) -> List[float]:
        """Center then project: returns a k-dim whitened vector. Identity passes through."""
        if self.is_identity:
            return list(vec)
        return matvec(self.components, sub(vec, self.mean))

    def to_dict(self) -> dict:
        return {"mean": self.mean, "components": self.components}

    @classmethod
    def from_dict(cls, d: dict) -> "WhiteningParams":
        if not d:
            return cls()
        return cls(mean=[float(x) for x in d.get("mean", [])],
                   components=[[float(x) for x in row] for row in d.get("components", [])])


def apply_whitening(vectors: Sequence[Sequence[float]], params: WhiteningParams) -> List[List[float]]:
    """Whiten a batch of vectors."""
    return [params.apply(v) for v in vectors]
