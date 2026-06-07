"""
EngineParams — the small, serializable bundle of fitted parameters.

Everything the request-path scorer needs that was learned offline: the whitening transform,
the percentile calibrator, the per-facet ensemble weights, and a few scalars. Round-trips
to a plain dict for storage in DynamoDB / S3 / JSON.
"""
from dataclasses import dataclass, field
from typing import Dict, Optional

from .whitening import WhiteningParams
from .calibration import PercentileCalibrator
from .aggregation import DEFAULT_HALF_LIFE_DAYS


@dataclass
class EngineParams:
    whitening: WhiteningParams = field(default_factory=WhiteningParams)
    calibrator: PercentileCalibrator = field(default_factory=PercentileCalibrator)
    weights: Optional[Dict[str, float]] = None          # None -> uniform over present facets
    half_life_days: float = DEFAULT_HALF_LIFE_DAYS
    lyric_mode: str = "wmd"                              # "wmd" | "gaussian"
    gaussian_scale: float = 1.0
    sinkhorn_eps: float = 0.1
    sinkhorn_iters: int = 50

    def to_dict(self) -> dict:
        return {
            "whitening": self.whitening.to_dict(),
            "calibrator": self.calibrator.to_dict(),
            "weights": self.weights,
            "half_life_days": self.half_life_days,
            "lyric_mode": self.lyric_mode,
            "gaussian_scale": self.gaussian_scale,
            "sinkhorn_eps": self.sinkhorn_eps,
            "sinkhorn_iters": self.sinkhorn_iters,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "EngineParams":
        d = d or {}
        weights = d.get("weights")
        return cls(
            whitening=WhiteningParams.from_dict(d.get("whitening", {})),
            calibrator=PercentileCalibrator.from_dict(d.get("calibrator", {})),
            weights={k: float(v) for k, v in weights.items()} if weights else None,
            half_life_days=float(d.get("half_life_days", DEFAULT_HALF_LIFE_DAYS)),
            lyric_mode=d.get("lyric_mode", "wmd"),
            gaussian_scale=float(d.get("gaussian_scale", 1.0)),
            sinkhorn_eps=float(d.get("sinkhorn_eps", 0.1)),
            sinkhorn_iters=int(d.get("sinkhorn_iters", 50)),
        )
