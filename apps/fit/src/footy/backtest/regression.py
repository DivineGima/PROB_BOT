"""Backtest regression check (architecture sections 9.3 and 14, ADR-046). Pure.

Compares a finished backtest with the previous COMPARABLE one: same models, same test length and
the same half-life and shrinkage. A model whose overall 1X2 RPS got worse by more than the
tolerance is reported as regressed. The check is informational: the monthly ``backtest.yml`` run
shows red and an alert event is written, but nothing is blocked.

The windows slide (the test period always ends at the newest stored result), so small differences
are normal; the tolerance is a starting value, unvalidated.
"""

from __future__ import annotations

import math
from collections.abc import Mapping

from footy.config import BACKTEST_REGRESSION_TOLERANCE


def _rps(summary: Mapping[str, object], name: str) -> float | None:
    result = summary.get("result")
    models = result.get("models") if isinstance(result, dict) else None
    entry = models.get(name) if isinstance(models, dict) else None
    overall = entry.get("overall") if isinstance(entry, dict) else None
    value = overall.get("rps_1x2") if isinstance(overall, dict) else None
    return float(value) if isinstance(value, int | float) and math.isfinite(value) else None


def _fit_setting(summary: Mapping[str, object], key: str) -> float | None:
    result = summary.get("result")
    fit = result.get("fit_config") if isinstance(result, dict) else None
    value = fit.get(key) if isinstance(fit, dict) else None
    return float(value) if isinstance(value, int | float) else None


def compare_with_previous(
    previous: Mapping[str, object] | None,
    current: Mapping[str, object],
    *,
    tolerance: float = BACKTEST_REGRESSION_TOLERANCE,
) -> dict[str, object]:
    """``previous`` and ``current`` are backtest job summaries (``job_runs.summary_json``)."""
    out: dict[str, object] = {"tolerance": tolerance, "comparable": False, "regressed": []}
    if not previous:
        out["reason"] = "no previous backtest"
        return out
    for key in ("models", "test_days"):
        if previous.get(key) != current.get(key):
            out["reason"] = f"the previous backtest used different {key}"
            return out
    for key in ("half_life_days", "shrink_team"):
        before, now = _fit_setting(previous, key), _fit_setting(current, key)
        if before is None or now is None or not math.isclose(before, now):
            out["reason"] = f"the previous backtest used a different {key}"
            return out

    models = current.get("models")
    names = [str(m) for m in models] if isinstance(models, list) else []
    if len(names) > 1:
        names.append("ensemble")
    changes: dict[str, dict[str, float]] = {}
    regressed: list[str] = []
    for name in names:
        before_rps, now_rps = _rps(previous, name), _rps(current, name)
        if before_rps is None or now_rps is None:
            continue
        delta = now_rps - before_rps
        changes[name] = {"previous": before_rps, "current": now_rps, "delta": delta}
        if delta > tolerance:
            regressed.append(name)
    out.update(
        {
            "comparable": True,
            "changes": changes,
            "regressed": regressed,
            "previous_data_cutoff": previous.get("data_cutoff"),
        }
    )
    return out
