"""Ensemble weights (architecture section 8.3, ADR-020). Pure functions.

For each model ``m`` that fitted tonight, ``mean_rps[m]`` is its mean 1X2 RPS over the most recent
``recent`` scored predictions. Raw weight ``exp(-kappa * mean_rps[m])``, normalised, is ``w_rps``.
With ``n`` scored predictions available::

    w = n / (n + shrink_n) * w_rps + shrink_n / (n + shrink_n) * w_prior

The specification shrinks toward equal weights ``1/M``. Until scored predictions exist the initial
weights "come from the walk-forward backtest", so ``w_prior`` is the backtest-derived softmax when
one is available and equal weights otherwise; with no backtest this is exactly the specification.
``kappa``, ``recent`` and ``shrink_n`` are starting values (unvalidated). Failed models are simply
absent from ``models``; the weights always sum to 1 over the models that fitted.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from footy.config import ENSEMBLE_KAPPA, ENSEMBLE_RECENT, ENSEMBLE_SHRINK_N

METHOD_EQUAL = "equal"
METHOD_BACKTEST = "backtest_prior"
METHOD_ROLLING = "rolling_rps"


@dataclass(frozen=True)
class EnsembleWeights:
    weights: dict[str, float]
    method: str
    n_scored: int
    kappa: float

    def as_dict(self) -> dict[str, object]:
        return {
            "weights": dict(self.weights),
            "method": self.method,
            "n_scored": self.n_scored,
            "kappa": self.kappa,
            "recent": ENSEMBLE_RECENT,
            "shrink_n": ENSEMBLE_SHRINK_N,
        }


def softmax_weights(
    mean_rps: Mapping[str, float], kappa: float = ENSEMBLE_KAPPA
) -> dict[str, float]:
    """``exp(-kappa * rps)`` normalised; a lower RPS gets a larger weight."""
    if not mean_rps:
        raise ValueError("need at least one model")
    if kappa < 0 or not math.isfinite(kappa):
        raise ValueError("kappa must be finite and non-negative")
    for name, value in mean_rps.items():
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"mean RPS of {name!r} is not a finite non-negative number")
    best = min(mean_rps.values())  # shift for numerical stability; the ratios do not change
    raw = {m: math.exp(-kappa * (v - best)) for m, v in mean_rps.items()}
    total = sum(raw.values())
    return {m: v / total for m, v in raw.items()}


def equal_weights(models: Sequence[str]) -> dict[str, float]:
    if not models:
        raise ValueError("need at least one model")
    return {m: 1.0 / len(models) for m in models}


def mean_recent_rps(
    history: Mapping[str, Sequence[float]], recent: int = ENSEMBLE_RECENT
) -> dict[str, float]:
    """Mean of the last ``recent`` values of each model's RPS series."""
    out: dict[str, float] = {}
    for model, series in history.items():
        window = list(series)[-recent:]
        if window:
            out[model] = sum(window) / len(window)
    return out


def ensemble_weights(
    models: Sequence[str],
    *,
    history: Mapping[str, Sequence[float]] | None = None,
    prior_rps: Mapping[str, float] | None = None,
    kappa: float = ENSEMBLE_KAPPA,
    recent: int = ENSEMBLE_RECENT,
    shrink_n: int = ENSEMBLE_SHRINK_N,
) -> EnsembleWeights:
    """Weights over ``models`` (those that fitted tonight).

    ``history``: per-model series of 1X2 RPS of scored predictions, aligned (same predictions for
    every model); ``prior_rps``: per-model mean RPS from the walk-forward backtest.
    """
    names = list(models)
    if not names:
        raise ValueError("no model fitted: there is nothing to weight")
    prior: dict[str, float]
    method = METHOD_EQUAL
    if prior_rps and all(m in prior_rps for m in names):
        prior = softmax_weights({m: prior_rps[m] for m in names}, kappa)
        method = METHOD_BACKTEST
    else:
        prior = equal_weights(names)

    n = 0
    if history and all(m in history and len(history[m]) > 0 for m in names):
        n = min(len(history[m]) for m in names)
        n = min(n, recent)
    if n == 0:
        return EnsembleWeights(prior, method, 0, kappa)

    aligned = {m: list(history[m])[-n:] for m in names}  # type: ignore[index]
    w_rps = softmax_weights({m: sum(s) / n for m, s in aligned.items()}, kappa)
    keep = n / (n + shrink_n)
    mixed = {m: keep * w_rps[m] + (1.0 - keep) * prior[m] for m in names}
    total = sum(mixed.values())
    return EnsembleWeights({m: v / total for m, v in mixed.items()}, METHOD_ROLLING, n, kappa)


def prior_from_backtest(
    summary: Mapping[str, object] | None, models: Sequence[str]
) -> dict[str, float]:
    """Mean 1X2 RPS per model from a stored backtest summary (``job_runs.summary_json``), or an
    empty dict when the summary is missing or does not cover every model."""
    if not summary:
        return {}
    result = summary.get("result")
    entries = result.get("models") if isinstance(result, dict) else None
    if not isinstance(entries, dict):
        return {}
    out: dict[str, float] = {}
    for m in models:
        entry = entries.get(m)
        overall = entry.get("overall") if isinstance(entry, dict) else None
        value = overall.get("rps_1x2") if isinstance(overall, dict) else None
        if isinstance(value, int | float) and math.isfinite(value):
            out[m] = float(value)
    return out if len(out) == len(models) else {}
