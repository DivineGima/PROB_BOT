"""Metrics for the weekly report (architecture sections 8.7 and 9.2, ADR-046). Pure functions.

Over all scored predictions: the ensemble's scores, the league-frequency baseline's scores on the
same fixtures, their paired difference with a percentile-bootstrap interval, per-model and
per-competition RPS, calibration bins for the three 1X2 outcomes and each over line, and the
omission rate by reason. Everything is JSON-safe so it can be stored in ``calibration_snapshots``.

The interval is information, not a claim of significance: the predictions are few, correlated within
a matchday, and the thresholds behind them are unvalidated.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence

import numpy as np

from footy.config import REPORT_TARGET_SCORED
from footy.models.grid import OVER_LINES, GridError, Markets
from footy.repo.predictions import ReportRow
from footy.scoring.calibration import calibration_bins
from footy.scoring.metrics import HOME, brier_over, outcome_1x2, rps_1x2, rps_totals

BOOTSTRAP_SEED = 20261017
BOOTSTRAP_RESAMPLES = 2000
CI_LEVEL = 0.95
CALIBRATION_BINS = 10


def paired_bootstrap_ci(
    differences: Sequence[float],
    *,
    n_boot: int = BOOTSTRAP_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
    level: float = CI_LEVEL,
) -> tuple[float, float] | None:
    """Percentile bootstrap interval of the mean of ``differences``; None below 2 values.
    Deterministic for a given seed."""
    n = len(differences)
    if n < 2:
        return None
    values = np.asarray(differences, dtype=np.float64)
    rng = np.random.default_rng(seed)
    means = values[rng.integers(0, n, size=(n_boot, n))].mean(axis=1)
    low, high = np.quantile(means, [(1.0 - level) / 2.0, 1.0 - (1.0 - level) / 2.0])
    return float(low), float(high)


def _model_forecasts(models_json: str) -> dict[str, tuple[float, float, float]]:
    try:
        parsed = json.loads(models_json)
    except ValueError:
        return {}
    out: dict[str, tuple[float, float, float]] = {}
    if isinstance(parsed, dict):
        for name, entry in parsed.items():
            p = entry.get("p") if isinstance(entry, dict) else None
            if isinstance(p, list) and len(p) == 3 and all(isinstance(v, int | float) for v in p):
                out[str(name)] = (float(p[0]), float(p[1]), float(p[2]))
    return out


def _baseline(row: ReportRow) -> Markets | None:
    try:
        return Markets.from_dict(json.loads(row.baseline_json))
    except (ValueError, GridError):
        return None


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def compute_metrics(
    rows: Sequence[ReportRow],
    *,
    omissions: Mapping[str, int],
    published_total: int,
    pending: int,
    n_boot: int = BOOTSTRAP_RESAMPLES,
) -> dict[str, object]:
    n = len(rows)
    out: dict[str, object] = {
        "n_scored": n,
        "n_pending": pending,
        "target": REPORT_TARGET_SCORED,
        "progress": n / REPORT_TARGET_SCORED,
    }
    omitted = sum(omissions.values())
    seen = published_total + omitted
    out["omissions"] = {
        "published": published_total,
        "omitted": omitted,
        "rate": omitted / seen if seen else None,
        "by_reason": dict(sorted(omissions.items())),
    }
    if n == 0:
        return out

    out["window_from"] = min(r.match_date for r in rows)
    out["window_to"] = max(r.match_date for r in rows)
    out["ensemble"] = {
        "rps_1x2": _mean([r.rps_1x2 for r in rows]),
        "rps_totals": _mean([r.rps_totals for r in rows]),
        "logloss_1x2": _mean([r.logloss_1x2 for r in rows]),
        "brier_overs": [
            _mean([brier_over(r.overs[k], r.goals_home, r.goals_away, line) for r in rows])
            for k, line in enumerate(OVER_LINES)
        ],
    }

    # -- baseline, paired on the same fixtures ----------
    diffs: list[float] = []
    diffs_totals: list[float] = []
    ens_paired: list[float] = []
    base_paired: list[float] = []
    base_paired_totals: list[float] = []
    by_comp: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: {"ens": [], "base": [], "ens_paired": []}
    )
    for r in rows:
        by_comp[r.comp_code]["ens"].append(r.rps_1x2)
        base = _baseline(r)
        if base is None:
            continue
        b = rps_1x2(base.p_home, base.p_draw, base.p_away, r.goals_home, r.goals_away)
        bt = rps_totals(base.total_pmf, r.goals_home, r.goals_away)
        diffs.append(r.rps_1x2 - b)
        diffs_totals.append(r.rps_totals - bt)
        ens_paired.append(r.rps_1x2)
        base_paired.append(b)
        base_paired_totals.append(bt)
        by_comp[r.comp_code]["base"].append(b)
        by_comp[r.comp_code]["ens_paired"].append(r.rps_1x2)

    ci = paired_bootstrap_ci(diffs, n_boot=n_boot)
    out["baseline"] = {
        "n": len(diffs),
        "rps_1x2": _mean(base_paired),
        "rps_totals": _mean(base_paired_totals),
    }
    out["paired"] = {
        "n": len(diffs),
        "ensemble_rps_1x2": _mean(ens_paired),
        "baseline_rps_1x2": _mean(base_paired),
        "mean_diff_rps_1x2": _mean(diffs),  # negative: the ensemble is better
        "mean_diff_rps_totals": _mean(diffs_totals),
        "ci_low": ci[0] if ci else None,
        "ci_high": ci[1] if ci else None,
        "level": CI_LEVEL,
        "n_boot": n_boot,
        "seed": BOOTSTRAP_SEED,
    }

    # -- per model and per competition ----------
    per_model: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        for name, p in _model_forecasts(r.models_json).items():
            per_model[name].append(rps_1x2(p[0], p[1], p[2], r.goals_home, r.goals_away))
    out["by_model"] = {
        name: {"n": len(v), "rps_1x2": _mean(v)} for name, v in sorted(per_model.items())
    }
    out["by_competition"] = {
        comp: {
            "n": len(v["ens"]),
            "rps_1x2": _mean(v["ens"]),
            "baseline_n": len(v["base"]),
            "baseline_rps_1x2": _mean(v["base"]),
            "ensemble_rps_1x2_on_baseline_fixtures": _mean(v["ens_paired"]),
        }
        for comp, v in sorted(by_comp.items())
    }

    # -- calibration ----------
    calibration: dict[str, list[dict[str, object]]] = {}
    outcomes = [outcome_1x2(r.goals_home, r.goals_away) for r in rows]
    for index, name in enumerate(("home", "draw", "away")):
        pairs = [
            ((r.p_home, r.p_draw, r.p_away)[index], o == HOME + index)
            for r, o in zip(rows, outcomes, strict=True)
        ]
        calibration[name] = [b.as_dict() for b in calibration_bins(pairs, CALIBRATION_BINS)]
    for k, line in enumerate(OVER_LINES):
        pairs = [(r.overs[k], r.goals_home + r.goals_away > line) for r in rows]
        calibration[f"over_{line}"] = [
            b.as_dict() for b in calibration_bins(pairs, CALIBRATION_BINS)
        ]
    out["calibration"] = calibration
    return out


def largest_calibration_gap(
    bins: Sequence[Mapping[str, object]], *, min_n: int = 10
) -> tuple[float, float] | None:
    """(forecast, observed) of the bin with the biggest gap among bins with at least ``min_n``
    predictions; None if no bin is that full."""
    best: tuple[float, float] | None = None
    for b in bins:
        n, f, o = b.get("n"), b.get("mean_forecast"), b.get("observed_frequency")
        if not (isinstance(n, int) and isinstance(f, float) and isinstance(o, float)):
            continue
        if n >= min_n and (best is None or abs(f - o) > abs(best[0] - best[1])):
            best = (f, o)
    return best


def finite(value: object) -> float | None:
    return float(value) if isinstance(value, int | float) and math.isfinite(value) else None
