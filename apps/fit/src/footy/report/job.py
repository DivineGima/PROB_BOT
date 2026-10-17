"""``footy report``: the weekly calibration summary (architecture sections 8.7 and 9.2).

Computes the metrics over every scored prediction, stores one ``calibration_snapshots`` row (when
something is scored), and with ``send`` delivers the text and the chart to Telegram. The snapshot is
written BEFORE anything is sent, so a Telegram outage never loses the numbers; a failed send then
ends the job with the outage exit code. ``monday_only`` lets the nightly workflow call it every
night and report only on Mondays.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime

from footy.clock import utc_now
from footy.errors import ConfigError, ExitCode
from footy.jobs import JobResult, run_job
from footy.repo.calibration import CalibrationRepo
from footy.repo.ops import OpsRepo
from footy.repo.ports import Database
from footy.repo.predictions import PredictionsRepo
from footy.report.chart import render_chart
from footy.report.metrics import compute_metrics
from footy.report.text import render_text
from footy.telegram import TelegramSender

log = logging.getLogger("footy.report")

MONDAY = 0


def run_report_job(
    db: Database,
    *,
    sender: TelegramSender | None = None,
    send: bool = False,
    monday_only: bool = False,
    now: Callable[[], str] = utc_now,
    git_sha: str | None = None,
) -> JobResult:
    ops = OpsRepo(db)
    summary: dict[str, object] = {"mode": "report", "send": send}

    def body() -> ExitCode:
        if send and sender is None:
            raise ConfigError("--send needs TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")
        at = now()
        today = datetime.fromisoformat(at.replace("Z", "+00:00")).astimezone(UTC)
        if monday_only and today.weekday() != MONDAY:
            summary["skipped"] = "not a Monday"
            return ExitCode.OK

        predictions = PredictionsRepo(db)
        rows = predictions.scored_for_report()
        counts = predictions.counts_by_status()
        metrics = compute_metrics(
            rows,
            omissions=predictions.omission_counts(),
            published_total=predictions.published_total(),
            pending=counts.get("pending", 0),
        )
        text = render_text(metrics, at[:10])
        summary.update({"n_scored": len(rows), "text": text})

        if rows:
            snapshot_id = CalibrationRepo(db).insert(
                at,
                str(metrics["window_from"]),
                str(metrics["window_to"]),
                len(rows),
                metrics,
                CalibrationRepo(db).active_run_id(),
            )
            summary["snapshot_id"] = snapshot_id

        png: bytes | None = None
        if rows:
            try:
                png = render_chart(metrics)
            except Exception:  # a drawing problem must not stop the text from being sent
                log.exception("the report chart could not be drawn")
                summary["chart"] = "failed"
        if send and sender is not None:
            sender.send_message(text)
            if png is not None:
                sender.send_photo(png, caption=f"Weekly report {at[:10]}")
            summary["sent"] = True
        return ExitCode.OK

    return run_job(ops, "report", now=now, git_sha=git_sha, summary=summary, body=body)
