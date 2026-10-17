"""Repository for the operational tables: job_runs, events and source_fetch_log (SQL lives here
only). Events carry an optional ``dedupe_key``; an event with a key already seen inside the dedupe
window is not written again (section 9.2: at most one alert per key per 24 h)."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta

from footy.config import EVENT_DEDUPE_HOURS
from footy.ingest.fd_org import FetchRecord
from footy.repo.d1_client import Statement, insert_statements
from footy.repo.ports import Database

_TS = "%Y-%m-%dT%H:%M:%SZ"


def _cutoff(at: str, hours: int) -> str:
    return (datetime.strptime(at, _TS) - timedelta(hours=hours)).strftime(_TS)


def _minutes_before(at: str, minutes: int) -> str:
    return (datetime.strptime(at, _TS) - timedelta(minutes=minutes)).strftime(_TS)


class OpsRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    def start_job(self, kind: str, started_at: str, git_sha: str | None) -> int:
        results = self._db.batch(
            [
                Statement(
                    "INSERT INTO job_runs (kind, started_at, status, git_sha) "
                    "VALUES (?, ?, 'running', ?)",
                    (kind, started_at, git_sha),
                ),
                Statement("SELECT last_insert_rowid() AS job_id"),
            ]
        )
        return int(results[1][0]["job_id"])

    def finish_job(
        self,
        job_id: int,
        finished_at: str,
        status: str,
        summary: Mapping[str, object],
        error: str | None = None,
    ) -> None:
        self._db.query(
            "UPDATE job_runs SET finished_at = ?, status = ?, summary_json = ?, error = ? "
            "WHERE job_id = ?",
            (finished_at, status, json.dumps(summary, sort_keys=True), error, job_id),
        )

    def log_fetches(self, source: str, records: Iterable[FetchRecord]) -> None:
        rows = [
            (
                source,
                r.resource,
                r.fetched_at,
                r.http_status,
                int(r.ok),
                None,
                None,
                r.content_sha256,
                r.rows,
                r.bytes,
            )
            for r in records
        ]
        statements = insert_statements(
            "source_fetch_log",
            [
                "source",
                "resource",
                "fetched_at",
                "http_status",
                "ok",
                "etag",
                "last_modified",
                "content_sha256",
                "rows",
                "bytes",
            ],
            rows,
        )
        if statements:
            self._db.batch(statements)

    def record_event(
        self,
        at: str,
        level: str,
        source: str,
        kind: str,
        detail: Mapping[str, object],
        dedupe_key: str | None = None,
    ) -> bool:
        """Write one event; returns False when a same-key event already exists in the window."""
        payload = json.dumps(detail, sort_keys=True, default=str)
        if dedupe_key is None:
            self._db.query(
                "INSERT INTO events (at, level, source, kind, detail_json) VALUES (?, ?, ?, ?, ?)",
                (at, level, source, kind, payload),
            )
            return True
        rows = self._db.batch(
            [
                Statement(
                    "INSERT INTO events (at, level, source, kind, detail_json, dedupe_key) "
                    "SELECT ?, ?, ?, ?, ?, ? WHERE NOT EXISTS "
                    "(SELECT 1 FROM events WHERE dedupe_key = ? AND at >= ?)",
                    (
                        at,
                        level,
                        source,
                        kind,
                        payload,
                        dedupe_key,
                        dedupe_key,
                        _cutoff(at, EVENT_DEDUPE_HOURS),
                    ),
                ),
                Statement("SELECT changes() AS n"),
            ]
        )
        return int(rows[1][0]["n"]) > 0

    def fail_stale_jobs(self, at: str, older_than_minutes: int) -> int:
        """Close ``running`` rows started more than ``older_than_minutes`` ago (a job killed by the
        workflow timeout never records its end). Returns how many were closed."""
        cutoff = _minutes_before(at, older_than_minutes)
        results = self._db.batch(
            [
                Statement(
                    "UPDATE job_runs SET status = 'failed', finished_at = ?, "
                    "error = 'abandoned: the job never recorded its end' "
                    "WHERE status = 'running' AND started_at < ?",
                    (at, cutoff),
                ),
                Statement("SELECT changes() AS n"),
            ]
        )
        return int(results[1][0]["n"])

    def latest_job_summary(self, kind: str) -> dict[str, object] | None:
        """The stored summary of the newest finished job of this kind (``ok`` or ``partial``)."""
        rows = self._db.query(
            "SELECT summary_json FROM job_runs WHERE kind = ? AND status IN ('ok', 'partial') "
            "AND summary_json IS NOT NULL ORDER BY job_id DESC LIMIT 1",
            (kind,),
        )
        if not rows:
            return None
        try:
            loaded = json.loads(rows[0]["summary_json"])
        except (TypeError, ValueError):
            return None
        return loaded if isinstance(loaded, dict) else None

    def count_events(self, kind: str) -> int:
        rows = self._db.query("SELECT COUNT(*) AS n FROM events WHERE kind = ?", (kind,))
        return int(rows[0]["n"])
