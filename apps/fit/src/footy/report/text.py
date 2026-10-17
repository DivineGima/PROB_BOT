"""The weekly report as plain text (architecture section 8.7). Pure.

Honest wording is part of the contract: with few scored predictions the text says the numbers are
noise; the interval is information, never a claim of significance; the success metric (beat the
league-frequency baseline on RPS over at least 300 scored predictions) is stated as a target.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from footy.config import REPORT_TARGET_SCORED
from footy.report.metrics import finite, largest_calibration_gap

TOO_FEW = 30  # below this the report says the numbers mean nothing yet
MAX_COMPETITIONS = 12
MAX_CHARS = 3800


def _fmt(value: object, digits: int = 4) -> str:
    number = finite(value)
    return "n/a" if number is None else f"{number:.{digits}f}"


def _signed(value: object, digits: int = 4) -> str:
    number = finite(value)
    return "n/a" if number is None else f"{number:+.{digits}f}"


def verdict(metrics: Mapping[str, Any]) -> str:
    n = int(metrics.get("n_scored", 0))
    target = int(metrics.get("target", REPORT_TARGET_SCORED))
    if n == 0:
        return "No predictions have been scored yet."
    if n < TOO_FEW:
        return (
            f"Only {n} predictions are scored: far too few to say anything about accuracy. "
            "Treat every number below as noise."
        )
    paired = metrics.get("paired") or {}
    low, high = finite(paired.get("ci_low")), finite(paired.get("ci_high"))
    if low is None or high is None:
        return f"{n} scored, but no baseline comparison is available for them."
    if high < 0:
        direction = "The ensemble is ahead of the baseline and the interval excludes zero."
    elif low > 0:
        direction = "The ensemble is behind the baseline and the interval excludes zero."
    else:
        direction = "The interval includes zero: no difference can be claimed yet."
    lead = (
        f"{n} of the {target} scored predictions needed: early numbers. "
        if n < target
        else f"The {target}-prediction target is reached ({n} scored). "
    )
    return (
        f"{lead}{direction} This is information, not a significance claim; "
        "thresholds and weights are still unvalidated."
    )


def render_text(metrics: Mapping[str, Any], today: str) -> str:
    n = int(metrics.get("n_scored", 0))
    target = int(metrics.get("target", REPORT_TARGET_SCORED))
    pending = int(metrics.get("n_pending", 0))
    lines = [
        f"Weekly report {today}",
        f"Scored predictions: {n} of the {target} needed ({n / target:.0%}); {pending} pending.",
    ]

    ensemble = metrics.get("ensemble")
    paired = metrics.get("paired") or {}
    if ensemble:
        interval = ""
        if finite(paired.get("ci_low")) is not None:
            interval = (
                f" (95% interval {_signed(paired.get('ci_low'))} "
                f"to {_signed(paired.get('ci_high'))})"
            )
        lines += [
            "",
            "Ensemble against the league-frequency baseline "
            f"({paired.get('n', 0)} fixtures with a baseline):",
            f"  RPS 1X2    ensemble {_fmt(paired.get('ensemble_rps_1x2'))}  "
            f"baseline {_fmt(paired.get('baseline_rps_1x2'))}  "
            f"difference {_signed(paired.get('mean_diff_rps_1x2'))}{interval}",
            f"  RPS totals ensemble {_fmt(ensemble.get('rps_totals'))}  "
            f"baseline {_fmt((metrics.get('baseline') or {}).get('rps_totals'))}",
            f"  Log loss 1X2 {_fmt(ensemble.get('logloss_1x2'))}",
        ]
    lines += ["", verdict(metrics)]

    by_model = metrics.get("by_model") or {}
    if by_model:
        lines += ["", "Models, RPS 1X2 (lower is better):"]
        lines.append(
            "  "
            + ", ".join(
                f"{name} {_fmt(v.get('rps_1x2'))} (n {v.get('n')})" for name, v in by_model.items()
            )
        )

    by_comp = metrics.get("by_competition") or {}
    if by_comp:
        lines += ["", "By competition, RPS 1X2 ensemble vs baseline:"]
        for comp, v in list(by_comp.items())[:MAX_COMPETITIONS]:
            lines.append(
                f"  {comp} {_fmt(v.get('ensemble_rps_1x2_on_baseline_fixtures'))} vs "
                f"{_fmt(v.get('baseline_rps_1x2'))} (n {v.get('n')})"
            )
        if len(by_comp) > MAX_COMPETITIONS:
            lines.append(f"  ... and {len(by_comp) - MAX_COMPETITIONS} more")

    calibration = metrics.get("calibration") or {}
    gaps = []
    for name, bins in calibration.items():
        gap = largest_calibration_gap(bins)
        if gap is not None:
            gaps.append((abs(gap[0] - gap[1]), name, gap))
    if gaps:
        _size, name, (forecast, observed) = max(gaps)
        lines += [
            "",
            f"Calibration: the widest gap in a bin of 10+ predictions is {name}, forecast "
            f"{forecast:.0%} against {observed:.0%} observed.",
        ]
    elif n:
        lines += ["", "Calibration: no probability bin holds 10 predictions yet."]

    om = metrics.get("omissions") or {}
    if om.get("omitted"):
        rate = finite(om.get("rate"))
        reasons = ", ".join(f"{k} {v}" for k, v in (om.get("by_reason") or {}).items())
        lines += [
            "",
            f"Omitted matches: {om['omitted']} of {om['published'] + om['omitted']}"
            + (f" ({rate:.1%})" if rate is not None else "")
            + f" - {reasons}.",
        ]
    lines += ["", "Probabilities, not advice."]
    text = "\n".join(lines)
    return text if len(text) <= MAX_CHARS else text[: MAX_CHARS - 1] + "…"
