"""Read-only queries for the health check (architecture sections 9.2 and 10). SQL lives here only.

Everything is a small indexed read; nothing here writes.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass

from footy.repo.forecasts import SCHEDULED_STATUSES
from footy.repo.ports import Database


@dataclass(frozen=True)
class ActiveRunInfo:
    run_id: str
    activated_at: str
    stale_hours: float | None  # the limit stored in the run's config, if it has one


class HealthRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    def active_run(self) -> ActiveRunInfo | None:
        rows = self._db.query(
            "SELECT a.run_id, a.activated_at, r.config_json FROM active_run a "
            "JOIN model_runs r ON r.run_id = a.run_id WHERE a.id = 1"
        )
        if not rows:
            return None
        limit: float | None = None
        try:
            value = json.loads(rows[0]["config_json"] or "{}").get("stale_hours")
            if isinstance(value, int | float) and not isinstance(value, bool) and value > 0:
                limit = float(value)
        except (TypeError, ValueError, AttributeError):
            limit = None
        return ActiveRunInfo(str(rows[0]["run_id"]), str(rows[0]["activated_at"]), limit)

    def scheduled_count(self, match_date: str) -> int:
        """Matches still to be played on ``match_date`` (fixtures a forecast is expected for)."""
        marks = ", ".join("?" for _ in SCHEDULED_STATUSES)
        rows = self._db.query(
            f"SELECT COUNT(*) AS n FROM matches WHERE match_date = ? AND status IN ({marks})",  # noqa: S608
            (match_date, *SCHEDULED_STATUSES),
        )
        return int(rows[0]["n"])

    def forecast_count(self, run_id: str, match_date: str) -> int:
        rows = self._db.query(
            "SELECT COUNT(*) AS n FROM fixture_forecasts WHERE run_id = ? AND match_date = ?",
            (run_id, match_date),
        )
        return int(rows[0]["n"])

    def stuck_uploads(self, received_before: str) -> int:
        """Uploads acknowledged but never finalised (ADR-029)."""
        rows = self._db.query(
            "SELECT COUNT(*) AS n FROM uploads WHERE status = 'received' AND received_at <= ?",
            (received_before,),
        )
        return int(rows[0]["n"])

    def events_since(self, kinds: Sequence[str], since: str) -> int:
        marks = ", ".join("?" for _ in kinds)
        rows = self._db.query(
            f"SELECT COUNT(*) AS n FROM events WHERE kind IN ({marks}) AND at >= ?",  # noqa: S608
            (*kinds, since),
        )
        return int(rows[0]["n"])
