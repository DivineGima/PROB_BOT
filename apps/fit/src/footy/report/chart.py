"""The weekly chart (architecture 4, section 8.7, ADR-055): one PNG with four plain-language panels,
drawn with matplotlib's non-GUI backend so it runs on a CI machine with no display.

1. Accuracy grade: the bot, its models and the simple benchmark (mean RPS 1X2, shorter is better).
2. How often the calls came true: the strongest call and the favourite by confidence band, what
   the bot said against what happened.
3. Goals: the stated chance of each over line against how often it happened.
4. Results: the stated chance of home, draw and away against how often each happened.

[v4] Panels 2 to 4 read the additive ``plain_metrics`` keys; an older snapshot without them draws
"no data" in that panel rather than failing.
"""

from __future__ import annotations

import io
from collections.abc import Mapping
from typing import Any

from footy.report.metrics import finite

GREEN, AMBER, RED, BLUE, GREY, INK = (
    "#2e9e5b",
    "#e0a526",
    "#d6453d",
    "#3b7dd8",
    "#c9ced6",
    "#1d2430",
)
BANDS = (
    ("clear", "Favourite\n60%+"),
    ("slight", "Favourite\n50-60%"),
    ("open", "Favourite\nunder 50%"),
)


def _rate(entry: Mapping[str, Any]) -> tuple[float | None, float | None, int]:
    n = entry.get("n") if isinstance(entry.get("n"), int) else 0
    return finite(entry.get("mean_forecast")), finite(entry.get("rate")), int(n or 0)


def _no_data(ax: Any, title: str) -> None:
    ax.set_title(title, fontsize=11, loc="left", weight="bold")
    ax.text(0.5, 0.5, "no data yet", ha="center", va="center", color="#888", transform=ax.transAxes)
    ax.set_xticks([])
    ax.set_yticks([])


def render_chart(metrics: Mapping[str, Any]) -> bytes:
    """PNG bytes. Raises ``ValueError`` when there is nothing scored to draw."""
    n_scored = int(metrics.get("n_scored", 0))
    if n_scored == 0:
        raise ValueError("no scored predictions to chart")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import PercentFormatter

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})
    fig, axs = plt.subplots(2, 2, figsize=(9, 8.2), dpi=110)
    try:
        target = int(metrics.get("target", 300))
        fig.suptitle(
            f"Weekly report · {n_scored} of {target} graded",
            fontsize=14,
            weight="bold",
            color=INK,
        )

        # -- 1. accuracy grade ----------
        ax = axs[0, 0]
        paired = metrics.get("paired") or {}
        bars: list[tuple[str, float, str]] = []
        base = finite(paired.get("baseline_rps_1x2"))
        if base is not None:
            bars.append(("Simple\nbenchmark", base, GREY))
        ens = finite((metrics.get("ensemble") or {}).get("rps_1x2"))
        if ens is not None:
            bars.append(("Your bot", ens, GREEN))
        for name, entry in (metrics.get("by_model") or {}).items():
            value = finite(entry.get("rps_1x2"))
            if value is not None:
                bars.append((f"model {name}", value, "#9cc3e8"))
        if bars:
            labels = [b[0] for b in bars][::-1]
            values = [b[1] for b in bars][::-1]
            ax.barh(labels, values, color=[b[2] for b in bars][::-1], height=0.6)
            for i, v in enumerate(values):
                ax.text(v, i, f" {v:.3f}", va="center", fontsize=9)
            ax.set_xlim(0, max(values) * 1.25)
            ax.set_title(
                "1. Accuracy grade (shorter = better)", fontsize=11, loc="left", weight="bold"
            )
            diff = finite(paired.get("mean_diff_rps_1x2"))
            low, high = finite(paired.get("ci_low")), finite(paired.get("ci_high"))
            if diff is not None and base:
                better = -diff / base
                proven = (
                    "interval excludes zero"
                    if low is not None and high is not None and (high < 0 or low > 0)
                    else "not proven yet (could be luck)"
                )
                ax.set_xlabel(
                    f"Bot is {abs(better):.0%} {'better' if better >= 0 else 'worse'} · {proven}",
                    color="#a06b00",
                )
        else:
            _no_data(ax, "1. Accuracy grade")
        ax.spines[["top", "right"]].set_visible(False)

        # -- 2. how often the calls came true ----------
        ax = axs[0, 1]
        groups: list[tuple[str, Mapping[str, Any]]] = []
        strongest = metrics.get("strongest") or {}
        if strongest.get("n"):
            groups.append(("★ Strongest\ncall", strongest))
        bands = (metrics.get("favourite") or {}).get("by_band") or {}
        groups += [
            (label, bands.get(key) or {}) for key, label in BANDS if (bands.get(key) or {}).get("n")
        ]
        if groups:
            xs = list(range(len(groups)))
            said = [_rate(g)[0] or 0.0 for _, g in groups]
            happened = [_rate(g)[1] or 0.0 for _, g in groups]
            ax.bar([x - 0.2 for x in xs], said, 0.38, color=GREY, label="bot said")
            ax.bar([x + 0.2 for x in xs], happened, 0.38, color=BLUE, label="happened")
            for x, (_, g), h in zip(xs, groups, happened, strict=True):
                ax.text(x + 0.2, h + 0.02, f"{h:.0%}", ha="center", fontsize=8.5)
                ax.text(x, -0.2, f"n={_rate(g)[2]}", ha="center", fontsize=7.5, color="#888")
            ax.set_xticks(xs, [label for label, _ in groups], fontsize=8)
            ax.set_ylim(0, 1.1)
            ax.yaxis.set_major_formatter(PercentFormatter(1.0))
            ax.legend(fontsize=8, loc="upper right", frameon=False)
            ax.set_title("2. How often the calls came true", fontsize=11, loc="left", weight="bold")
        else:
            _no_data(ax, "2. How often the calls came true")
        ax.spines[["top", "right"]].set_visible(False)

        # -- 3. goals ----------
        ax = axs[1, 0]
        overs = metrics.get("overs") or {}
        lines = sorted(overs, key=float)
        if lines:
            said = [finite(overs[k].get("forecast")) or 0.0 for k in lines]
            happened = [finite(overs[k].get("observed")) or 0.0 for k in lines]
            xs_f = [float(k) for k in lines]
            ax.plot(xs_f, said, "o-", color=GREY, lw=2.5, label="bot said")
            ax.plot(xs_f, happened, "o-", color=BLUE, lw=2.5, label="happened")
            ax.set_xticks(xs_f, lines)
            ax.set_ylim(0, 1.05)
            ax.yaxis.set_major_formatter(PercentFormatter(1.0))
            ax.set_xlabel("over … goals")
            ax.legend(fontsize=8, frameon=False)
            ax.set_title(
                "3. Goals: blue above grey = more goals", fontsize=10, loc="left", weight="bold"
            )
        else:
            _no_data(ax, "3. Goals")
        ax.spines[["top", "right"]].set_visible(False)

        # -- 4. results ----------
        ax = axs[1, 1]
        outcomes = metrics.get("outcomes") or {}
        if outcomes:
            names = (
                ("home", "Home win", GREEN),
                ("draw", "Draw", AMBER),
                ("away", "Away win", RED),
            )
            said = [finite((outcomes.get(k) or {}).get("forecast")) or 0.0 for k, _, _ in names]
            happened = [finite((outcomes.get(k) or {}).get("observed")) or 0.0 for k, _, _ in names]
            xs = [0, 1, 2]
            ax.bar([x - 0.2 for x in xs], said, 0.38, color=GREY, label="bot said")
            ax.bar([x + 0.2 for x in xs], happened, 0.38, color=[c for _, _, c in names])
            for x, s_, h in zip(xs, said, happened, strict=True):
                ax.text(x - 0.2, s_ + 0.01, f"{s_:.0%}", ha="center", fontsize=8.5)
                ax.text(x + 0.2, h + 0.01, f"{h:.0%}", ha="center", fontsize=8.5)
            ax.set_xticks(xs, [label for _, label, _ in names])
            ax.set_ylim(0, max([*said, *happened, 0.4]) * 1.2)
            ax.yaxis.set_major_formatter(PercentFormatter(1.0))
            ax.set_title(
                "4. Results: grey said, colour happened", fontsize=10, loc="left", weight="bold"
            )
        else:
            _no_data(ax, "4. Results")
        ax.spines[["top", "right"]].set_visible(False)

        fig.text(
            0.5,
            0.008,
            "A small sample is noisy: treat every number as early. Probabilities, not advice.",
            ha="center",
            fontsize=8.5,
            color="#777",
        )
        fig.tight_layout(rect=(0, 0.02, 1, 0.96), h_pad=3)
        buffer = io.BytesIO()
        fig.savefig(buffer, format="png", facecolor="white")
        return buffer.getvalue()
    finally:
        plt.close(fig)
