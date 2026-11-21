"""``footy digest``: the daily results picture (architecture 4, sections 6.7 and 8.7, ADR-054).

Every night, right after scoring, the predictions scored since the last digest are drawn as one PNG
card per batch of at most ``ROWS_PER_IMAGE`` matches: the match, its 90-minute score, the bot's
home/draw/away bar with the real outcome outlined, and whether the strongest call (ADR-057) came
true. The caption counts how often the favourite and the strongest call were right.

Idempotent without a migration: a digest that sent (or had nothing to send) stores ``through``, the
newest ``scored_at`` it covered, in its ``job_runs.summary_json``; the next digest starts after it.
A failed send leaves no new ``through``, so the same matches are sent again the next night. The
very first digest looks back ``FIRST_LOOKBACK_HOURS`` only, so it never floods the chat.
"""

from __future__ import annotations

import io
import logging
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta

from footy.clock import utc_now
from footy.config import REPORT_TARGET_SCORED
from footy.errors import ConfigError, ExitCode
from footy.jobs import JobResult, run_job
from footy.repo.ops import OpsRepo
from footy.repo.ports import Database
from footy.repo.predictions import DigestRow, PredictionsRepo
from footy.report.display import call_hit, favourite, outcome_of, short_call, strongest_call
from footy.telegram import TelegramSender

log = logging.getLogger("footy.digest")

ROWS_PER_IMAGE = 12
MAX_ROWS = 60  # at most 5 pictures a night; anything older waits for the next run
FIRST_LOOKBACK_HOURS = 48
GREEN, AMBER, RED, INK = "#2e9e5b", "#e0a526", "#d6453d", "#1d2430"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _day(date: str) -> str:
    d = datetime.fromisoformat(date)
    return f"{d.day} {MONTHS[d.month - 1]}"


def summarise(rows: Sequence[DigestRow]) -> dict[str, int]:
    fav = sum(1 for r in rows if favourite(r.p1x2)[0] == outcome_of(r.goals_home, r.goals_away))
    call = sum(
        1 for r in rows if call_hit(strongest_call(r.p1x2, r.overs)[0], r.goals_home, r.goals_away)
    )
    return {"n": len(rows), "favourite_right": fav, "strongest_right": call}


def caption(rows: Sequence[DigestRow], graded_total: int, part: int, parts: int) -> str:
    s = summarise(rows)
    dates = sorted({r.match_date for r in rows})
    span = _day(dates[0]) if len(dates) == 1 else f"{_day(dates[0])} to {_day(dates[-1])}"
    head = f"🗓️ Graded: {span}" + (f" (picture {part} of {parts})" if parts > 1 else "")
    return (
        f"{head} · {s['n']} matches · favourite right {s['favourite_right']} of {s['n']} · "
        f"⭐ strongest call right {s['strongest_right']} of {s['n']} · "
        f"graded so far {graded_total} of {REPORT_TARGET_SCORED}. Send /results for details."
    )


def render_digest(rows: Sequence[DigestRow], title: str) -> bytes:
    """One PNG card for at most ``ROWS_PER_IMAGE`` scored predictions."""
    if not rows:
        raise ValueError("nothing to draw")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    plt.rcParams.update({"font.family": "DejaVu Sans"})
    n = len(rows)
    height = 12 + 6.2 * n
    fig = plt.figure(figsize=(7.2, 1.55 + 0.62 * n), dpi=150)
    try:
        ax = fig.add_axes((0, 0, 1, 1))
        ax.set_xlim(0, 100)
        ax.set_ylim(0, height)
        ax.axis("off")
        s = summarise(rows)
        ax.text(3, height - 3.2, title, fontsize=15, weight="bold", color=INK)
        ax.text(
            3,
            height - 6.6,
            f"Favourite right {s['favourite_right']} of {n}   ·   "
            f"★ strongest call right {s['strongest_right']} of {n}",
            fontsize=9.5,
            color="#555",
        )
        ax.text(
            3,
            height - 9.4,
            "Bar = the bot's chances (green home · amber draw · red away). "
            "Black outline = what happened.",
            fontsize=8,
            color="#777",
        )
        for i, r in enumerate(rows):
            y = height - 15.5 - i * 6.2
            if i % 2 == 0:
                ax.add_patch(Rectangle((0, y - 2.4), 100, 6.2, color="#f4f6f9", zorder=0))
            actual = outcome_of(r.goals_home, r.goals_away)
            fav_ok = favourite(r.p1x2)[0] == actual
            ax.text(
                3,
                y + 0.6,
                "✔" if fav_ok else "✘",
                fontsize=14,
                va="center",
                weight="bold",
                color=GREEN if fav_ok else RED,
            )
            ax.text(
                7,
                y + 1.2,
                f"{r.home} {r.goals_home}-{r.goals_away} {r.away}"[:44],
                fontsize=9.5,
                weight="bold",
                color=INK,
                va="center",
            )
            ax.text(
                7,
                y - 1.0,
                f"{r.comp_code} · {_day(r.match_date)}",
                fontsize=7.5,
                color="#888",
                va="center",
            )
            x, width = 52.0, 30.0
            for key, p, colour in zip(
                ("home", "draw", "away"), r.p1x2, (GREEN, AMBER, RED), strict=True
            ):
                hit = actual == key
                ax.add_patch(
                    Rectangle(
                        (x, y - 1.3),
                        width * p,
                        3.6,
                        color=colour,
                        ec="black" if hit else "white",
                        lw=2.2 if hit else 0.8,
                    )
                )
                if p >= 0.17:
                    ax.text(
                        x + width * p / 2,
                        y + 0.5,
                        f"{p * 100:.0f}",
                        fontsize=7.5,
                        color="white",
                        ha="center",
                        va="center",
                        weight="bold",
                    )
                x += width * p
            key, _p = strongest_call(r.p1x2, r.overs)
            ok = call_hit(key, r.goals_home, r.goals_away)
            ax.text(84, y + 0.5, f"★ {short_call(key)}", fontsize=8, color=INK, va="center")
            ax.text(
                98,
                y + 0.5,
                "✔" if ok else "✘",
                fontsize=11,
                va="center",
                ha="right",
                weight="bold",
                color=GREEN if ok else RED,
            )
        buffer = io.BytesIO()
        fig.savefig(buffer, format="png", facecolor="white")
        return buffer.getvalue()
    finally:
        plt.close(fig)


def _first_cutoff(at: str) -> str:
    moment = datetime.fromisoformat(at.replace("Z", "+00:00")).astimezone(UTC)
    return (moment - timedelta(hours=FIRST_LOOKBACK_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_digest_job(
    db: Database,
    *,
    sender: TelegramSender | None = None,
    send: bool = False,
    now: Callable[[], str] = utc_now,
    git_sha: str | None = None,
) -> JobResult:
    ops = OpsRepo(db)
    summary: dict[str, object] = {"mode": "digest", "send": send}

    def body() -> ExitCode:
        if send and sender is None:
            raise ConfigError("--send needs TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")
        at = now()
        previous = ops.latest_job_summary("digest") or {}
        after = previous.get("through")
        if not isinstance(after, str):
            after = _first_cutoff(at)
            summary["first_run"] = True
        predictions = PredictionsRepo(db)
        rows = predictions.scored_after(after, MAX_ROWS)
        summary.update({"after": after, "n": len(rows)})
        if not rows:
            summary["through"] = after  # carried forward: nothing new was scored
            return ExitCode.OK
        graded_total = predictions.counts_by_status().get("scored", 0)
        batches = [rows[i : i + ROWS_PER_IMAGE] for i in range(0, len(rows), ROWS_PER_IMAGE)]
        pictures: list[tuple[bytes, str]] = []
        for part, batch in enumerate(batches, start=1):
            pictures.append(
                (
                    render_digest(batch, "Latest graded predictions"),
                    caption(batch, graded_total, part, len(batches)),
                )
            )
        summary.update(summarise(rows))
        if send and sender is not None:
            for png, text in pictures:
                sender.send_photo(png, caption=text)
            summary["sent"] = len(pictures)
        # Only now is the high-water mark moved: a failed send above raises and leaves it.
        summary["through"] = rows[-1].scored_at
        return ExitCode.OK

    return run_job(ops, "digest", now=now, git_sha=git_sha, summary=summary, body=body)
