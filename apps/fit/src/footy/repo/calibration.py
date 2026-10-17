"""Repository for ``calibration_snapshots`` (SQL lives here only; architecture section 5.6)."""

from __future__ import annotations

import json
from collections.abc import Mapping

from footy.repo.d1_client import Statement
from footy.repo.ports import Database


class CalibrationRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    def active_run_id(self) -> str | None:
        rows = self._db.query("SELECT run_id FROM active_run WHERE id = 1")
        return str(rows[0]["run_id"]) if rows else None

    def insert(
        self,
        created_at: str,
        window_from: str,
        window_to: str,
        n_scored: int,
        metrics: Mapping[str, object],
        run_id: str | None,
    ) -> int:
        """Append one snapshot (never updated) and return its id."""
        results = self._db.batch(
            [
                Statement(
                    "INSERT INTO calibration_snapshots (created_at, window_from, window_to, "
                    "n_scored, metrics_json, run_id) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        created_at,
                        window_from,
                        window_to,
                        n_scored,
                        json.dumps(metrics, sort_keys=True, default=str),
                        run_id,
                    ),
                ),
                Statement("SELECT last_insert_rowid() AS snapshot_id"),
            ]
        )
        return int(results[1][0]["snapshot_id"])

    def count(self) -> int:
        rows = self._db.query("SELECT COUNT(*) AS n FROM calibration_snapshots")
        return int(rows[0]["n"])
