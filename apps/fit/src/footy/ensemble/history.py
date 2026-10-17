"""Rolling per-model RPS from logged predictions (architecture sections 8.3 and 8.7, ADR-046).

Each logged prediction stores every contributing model's own 1X2 forecast (``models_json``). Once
the result is known the RPS of each model can be recomputed from it. The ensemble weights of the
next fit are a softmax of these recent scores (``footy.ensemble.weights``).

Alignment rule: a prediction enters the history only if EVERY requested model forecast it. Without
that, the last-n windows of two models would cover different fixtures and the weights would compare
unequal samples (the review finding behind ``rps_history`` in the backtest, section 8.3).
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from footy.score.types import ScoredRow
from footy.scoring.metrics import rps_1x2


def _model_p(models: object, name: str) -> tuple[float, float, float] | None:
    if not isinstance(models, dict):
        return None
    entry = models.get(name)
    p = entry.get("p") if isinstance(entry, dict) else None
    if (
        not isinstance(p, list)
        or len(p) != 3
        or not all(isinstance(v, int | float) and 0.0 <= v <= 1.0 for v in p)
    ):
        return None
    return float(p[0]), float(p[1]), float(p[2])


def model_rps_series(rows: Sequence[ScoredRow], models: Sequence[str]) -> dict[str, list[float]]:
    """Per model, the 1X2 RPS of each scored prediction (oldest first) that all ``models``
    forecast. Every returned list has the same length and covers the same predictions."""
    series: dict[str, list[float]] = {m: [] for m in models}
    for row in rows:
        try:
            parsed = json.loads(row.models_json)
        except ValueError:
            continue
        forecasts = {m: _model_p(parsed, m) for m in models}
        if any(p is None for p in forecasts.values()):
            continue
        for name, p in forecasts.items():
            assert p is not None  # noqa: S101 (checked above)
            series[name].append(rps_1x2(p[0], p[1], p[2], row.goals_home, row.goals_away))
    return series
