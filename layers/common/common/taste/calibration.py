"""
Calibration — make the number honest.

A raw blended score of 0.4 is meaningless on its own. We calibrate against the empirical
distribution of *all* pairwise scores in the population, so the value we show is a
percentile: "73% match" literally means "more similar than 73% of random pairs". This
gives every edge a comparable, interpretable meaning across modes.

Fitting just stores a sorted sample of raw scores (offline); applying is a binary search.
Pure stdlib.
"""
import bisect
from dataclasses import dataclass, field
from typing import List, Sequence


@dataclass
class PercentileCalibrator:
    """Maps a raw score to its percentile against a stored sample of population scores."""
    sorted_samples: List[float] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.sorted_samples

    def to_percentile(self, score: float) -> float:
        """Fraction of the sample below `score`, in [0, 1]. Empty calibrator is a no-op."""
        if self.is_empty:
            return score
        idx = bisect.bisect_right(self.sorted_samples, score)
        return idx / len(self.sorted_samples)

    def to_dict(self) -> dict:
        return {"sorted_samples": self.sorted_samples}

    @classmethod
    def from_dict(cls, d: dict) -> "PercentileCalibrator":
        if not d:
            return cls()
        return cls(sorted_samples=sorted(float(x) for x in d.get("sorted_samples", [])))

    @classmethod
    def fit(cls, scores: Sequence[float]) -> "PercentileCalibrator":
        return cls(sorted_samples=sorted(float(x) for x in scores))
