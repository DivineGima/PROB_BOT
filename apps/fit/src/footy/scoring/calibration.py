"""Calibration bins (architecture section 8.7): for a stream of (forecast probability, did it
happen) pairs, the mean forecast and the observed frequency inside equal-width probability bins."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class CalibrationBin:
    low: float
    high: float
    n: int
    mean_forecast: float
    observed_frequency: float

    def as_dict(self) -> dict[str, object]:
        return {
            "low": self.low,
            "high": self.high,
            "n": self.n,
            "mean_forecast": self.mean_forecast,
            "observed_frequency": self.observed_frequency,
        }


def calibration_bins(pairs: Iterable[tuple[float, bool]], n_bins: int = 10) -> list[CalibrationBin]:
    """Bin [k/n, (k+1)/n); exactly 1.0 goes in the last bin. Empty bins are omitted."""
    if n_bins < 1:
        raise ValueError("n_bins must be at least 1")
    sums = [0.0] * n_bins
    hits = [0] * n_bins
    counts = [0] * n_bins
    for p, happened in pairs:
        if not 0.0 <= p <= 1.0:
            raise ValueError(f"forecast probability {p!r} is outside 0..1")
        k = min(int(p * n_bins), n_bins - 1)
        counts[k] += 1
        sums[k] += p
        hits[k] += 1 if happened else 0
    return [
        CalibrationBin(
            k / n_bins, (k + 1) / n_bins, counts[k], sums[k] / counts[k], hits[k] / counts[k]
        )
        for k in range(n_bins)
        if counts[k]
    ]
