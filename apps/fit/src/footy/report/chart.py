"""The weekly chart (architecture section 8.7): a reliability curve of the 1X2 probabilities and the
mean RPS of the ensemble, its models and the baseline. One PNG, drawn with matplotlib's non-GUI
backend, so it runs on a CI machine with no display."""

from __future__ import annotations

import io
from collections.abc import Mapping
from typing import Any

from footy.report.metrics import finite


def render_chart(metrics: Mapping[str, Any]) -> bytes:
    """PNG bytes. Raises ``ValueError`` when there is nothing scored to draw."""
    if int(metrics.get("n_scored", 0)) == 0:
        raise ValueError("no scored predictions to chart")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, (left, right) = plt.subplots(1, 2, figsize=(10, 4.2), dpi=110)
    try:
        # -- reliability of the three 1X2 outcomes, all bins together ----------
        calibration = metrics.get("calibration") or {}
        left.plot([0, 1], [0, 1], color="#888888", linestyle="--", linewidth=1, label="perfect")
        for name, colour in (("home", "#1f77b4"), ("draw", "#7f7f7f"), ("away", "#d62728")):
            bins = [b for b in calibration.get(name, []) if b.get("n")]
            if bins:
                left.plot(
                    [b["mean_forecast"] for b in bins],
                    [b["observed_frequency"] for b in bins],
                    marker="o",
                    markersize=3,
                    linewidth=1.2,
                    color=colour,
                    label=name,
                )
        left.set_xlim(0, 1)
        left.set_ylim(0, 1)
        left.set_xlabel("forecast probability")
        left.set_ylabel("observed frequency")
        left.set_title(f"Reliability, 1X2 (n={metrics['n_scored']})")
        left.legend(loc="upper left", fontsize=8)
        left.grid(alpha=0.25)

        # -- mean RPS: ensemble, each model, baseline ----------
        labels: list[str] = []
        values: list[float] = []
        colours: list[str] = []
        paired = metrics.get("paired") or {}
        for label, value, colour in (
            ("baseline", finite(paired.get("baseline_rps_1x2")), "#aaaaaa"),
            ("ensemble", finite((metrics.get("ensemble") or {}).get("rps_1x2")), "#2ca02c"),
        ):
            if value is not None:
                labels.append(label)
                values.append(value)
                colours.append(colour)
        for name, entry in (metrics.get("by_model") or {}).items():
            value = finite(entry.get("rps_1x2"))
            if value is not None:
                labels.append(str(name))
                values.append(value)
                colours.append("#1f77b4")
        right.bar(labels, values, color=colours)
        if values:
            right.set_ylim(max(0.0, min(values) * 0.9), max(values) * 1.05)
        right.set_ylabel("mean RPS 1X2 (lower is better)")
        right.set_title("Scores")
        right.grid(axis="y", alpha=0.25)
        fig.tight_layout()
        buffer = io.BytesIO()
        fig.savefig(buffer, format="png")
        return buffer.getvalue()
    finally:
        plt.close(fig)
