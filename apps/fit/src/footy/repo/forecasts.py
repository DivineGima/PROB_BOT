"""Repository for ``fixture_forecasts`` and the scheduled fixtures that feed it.

SQL lives here only; see architecture sections 5.4 and 8.11.

* Writes are ``INSERT OR IGNORE`` in chunks that respect the 100-parameter cap, resumable through a
  ``Progress`` store; existing rows are never changed.
* Pruning keeps the forecasts of the newest runs and never touches the active run's.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from footy.forecast.build import FORECAST_COLUMNS, Fixture, ForecastRow
from footy.repo.d1_client import Progress, Statement, execute_resumable, insert_statements
from footy.repo.ports import Database

SCHEDULED_STATUSES = ("SCHEDULED", "TIMED")


class ForecastRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    def upcoming_fixtures(self, start: date, end: date) -> list[Fixture]:
        """Scheduled matches with ``start <= match_date <= end``, in date order."""
        marks = ", ".join("?" for _ in SCHEDULED_STATUSES)
        rows = self._db.query(
            "SELECT comp_code, match_date, kickoff_utc, home_team_id, away_team_id FROM matches "  # noqa: S608
            f"WHERE status IN ({marks}) AND match_date >= ? AND match_date <= ? "
            "ORDER BY match_date, match_id",
            (*SCHEDULED_STATUSES, start.isoformat(), end.isoformat()),
        )
        return [
            Fixture(
                comp_code=str(r["comp_code"]),
                match_date=date.fromisoformat(str(r["match_date"])),
                kickoff_utc=None if r["kickoff_utc"] is None else str(r["kickoff_utc"]),
                home_id=int(r["home_team_id"]),
                away_id=int(r["away_team_id"]),
            )
            for r in rows
        ]

    def write(self, run_id: str, rows: Sequence[ForecastRow], progress: Progress) -> int:
        """Insert the forecast rows of a run (idempotent, resumable); returns the row count."""
        statements = insert_statements(
            "fixture_forecasts",
            FORECAST_COLUMNS,
            [r.values(run_id) for r in rows],
        )
        execute_resumable(self._db, f"forecasts:{run_id}", statements, progress)
        return len(rows)

    def count(self, run_id: str) -> int:
        rows = self._db.query(
            "SELECT COUNT(*) AS n FROM fixture_forecasts WHERE run_id = ?", (run_id,)
        )
        return int(rows[0]["n"])

    def verdict_counts(self, run_id: str) -> dict[str, int]:
        rows = self._db.query(
            "SELECT verdict, COUNT(*) AS n FROM fixture_forecasts "
            "WHERE run_id = ? GROUP BY verdict",
            (run_id,),
        )
        return {str(r["verdict"]): int(r["n"]) for r in rows}

    def prune(self, keep_runs: int) -> int:
        """Delete the forecasts of every run outside the newest ``keep_runs`` runs (by start time).
        The active run's forecasts are never deleted. Returns the number of rows deleted."""
        results = self._db.batch(
            [
                Statement(
                    "DELETE FROM fixture_forecasts WHERE run_id NOT IN "
                    "(SELECT run_id FROM model_runs ORDER BY started_at DESC, run_id DESC LIMIT ?) "
                    "AND run_id <> COALESCE((SELECT run_id FROM active_run WHERE id = 1), '')",
                    (keep_runs,),
                ),
                Statement("SELECT changes() AS n"),
            ]
        )
        return int(results[1][0]["n"])
