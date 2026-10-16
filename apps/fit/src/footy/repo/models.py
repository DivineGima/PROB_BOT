"""Repository for the model registry: ``model_runs``, ``active_run``, ``model_params`` and
``team_form`` (SQL lives here only; architecture sections 5.4, 8.6 and 9.6).

* Writes use bound parameters and idempotent statements; children are written after their run row.
* Promotion and rollback are ONE batch (atomic on D1). Each statement is guarded so that a run
  that is not promotable can neither become the pointer target nor supersede the current run, and
  repeating a promotion is a no-op.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from footy.form.snapshot import TeamForm
from footy.repo.d1_client import Progress, Statement, execute_resumable, insert_statements
from footy.repo.ports import Database

STATUS_BUILDING = "building"
STATUS_ACTIVE = "active"
STATUS_SUPERSEDED = "superseded"
STATUS_REJECTED = "rejected"
STATUS_FAILED = "failed"


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    status: str
    started_at: str
    finished_at: str | None
    data_cutoff_utc: str | None
    training_from: str | None
    training_to: str | None
    git_sha: str | None
    code_version: str | None
    config_json: str
    ensemble_json: str
    diagnostics_json: str


@dataclass(frozen=True)
class ParamRow:
    model: str
    status: str  # "ok" or "failed"
    payload_version: int | None
    payload_json: str | None
    payload_sha256: str | None
    error: str | None


def _opt_str(value: object) -> str | None:
    return None if value is None else str(value)


class ModelRegistryRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    # -- writing a run (status 'building', or 'failed' when no model fitted) ---------------------

    def write_run(
        self,
        run: RunRecord,
        params: Sequence[ParamRow],
        forms: Iterable[TeamForm],
        progress: Progress,
    ) -> None:
        """Insert the run row, then its parameters and form rows (chunked, idempotent)."""
        self._db.batch(
            insert_statements(
                "model_runs",
                [
                    "run_id",
                    "status",
                    "started_at",
                    "finished_at",
                    "data_cutoff_utc",
                    "training_from",
                    "training_to",
                    "git_sha",
                    "code_version",
                    "config_json",
                    "ensemble_json",
                    "diagnostics_json",
                ],
                [
                    (
                        run.run_id,
                        run.status,
                        run.started_at,
                        run.finished_at,
                        run.data_cutoff_utc,
                        run.training_from,
                        run.training_to,
                        run.git_sha,
                        run.code_version,
                        run.config_json,
                        run.ensemble_json,
                        run.diagnostics_json,
                    )
                ],
            )
        )
        param_statements = insert_statements(
            "model_params",
            [
                "run_id",
                "model",
                "status",
                "payload_version",
                "payload_json",
                "payload_sha256",
                "error",
            ],
            [
                (
                    run.run_id,
                    p.model,
                    p.status,
                    p.payload_version,
                    p.payload_json,
                    p.payload_sha256,
                    p.error,
                )
                for p in params
            ],
        )
        execute_resumable(self._db, f"params:{run.run_id}", param_statements, progress)
        form_statements = insert_statements(
            "team_form",
            [
                "run_id",
                "team_id",
                "n_training",
                "n_season",
                "season_gf",
                "season_ga",
                "l10_n",
                "l10_gf",
                "l10_ga",
                "latest_match_date",
            ],
            [
                (
                    run.run_id,
                    f.team_id,
                    f.n_training,
                    f.n_season,
                    f.season_gf,
                    f.season_ga,
                    f.l10_n,
                    f.l10_gf,
                    f.l10_ga,
                    f.latest_match_date,
                )
                for f in forms
            ],
        )
        execute_resumable(self._db, f"form:{run.run_id}", form_statements, progress)

    # -- reading ---------------------------------------------------------------------------------

    def get_run(self, run_id: str) -> RunRecord | None:
        rows = self._db.query("SELECT * FROM model_runs WHERE run_id = ?", (run_id,))
        return self._run(rows[0]) if rows else None

    def latest_run(self, status: str) -> RunRecord | None:
        rows = self._db.query(
            "SELECT * FROM model_runs WHERE status = ? "
            "ORDER BY started_at DESC, run_id DESC LIMIT 1",
            (status,),
        )
        return self._run(rows[0]) if rows else None

    def active_run_id(self) -> str | None:
        rows = self._db.query("SELECT run_id FROM active_run WHERE id = 1")
        return str(rows[0]["run_id"]) if rows else None

    def load_params(self, run_id: str) -> list[ParamRow]:
        rows = self._db.query(
            "SELECT model, status, payload_version, payload_json, payload_sha256, error "
            "FROM model_params WHERE run_id = ? ORDER BY model",
            (run_id,),
        )
        return [
            ParamRow(
                model=str(r["model"]),
                status=str(r["status"]),
                payload_version=None if r["payload_version"] is None else int(r["payload_version"]),
                payload_json=_opt_str(r["payload_json"]),
                payload_sha256=_opt_str(r["payload_sha256"]),
                error=_opt_str(r["error"]),
            )
            for r in rows
        ]

    def form_coverage(self, run_id: str) -> tuple[int, int]:
        """(active teams that have a ``team_form`` row for this run, active teams)."""
        results = self._db.batch(
            [
                Statement(
                    "SELECT COUNT(*) AS n FROM team_form f JOIN teams t ON t.team_id = f.team_id "
                    "WHERE f.run_id = ? AND t.active = 1",
                    (run_id,),
                ),
                Statement("SELECT COUNT(*) AS n FROM teams WHERE active = 1"),
            ]
        )
        return int(results[0][0]["n"]), int(results[1][0]["n"])

    def run_counts(self) -> dict[str, int]:
        rows = self._db.query("SELECT status, COUNT(*) AS n FROM model_runs GROUP BY status")
        return {str(r["status"]): int(r["n"]) for r in rows}

    # -- state changes ---------------------------------------------------------------------------

    def reject(self, run_id: str, finished_at: str, diagnostics: Mapping[str, object]) -> bool:
        """``building`` -> ``rejected`` with the gate result recorded; False if not building."""
        results = self._db.batch(
            [
                Statement(
                    "UPDATE model_runs SET status = 'rejected', finished_at = ?, "
                    "diagnostics_json = ? WHERE run_id = ? AND status = 'building'",
                    (finished_at, json.dumps(diagnostics, sort_keys=True, default=str), run_id),
                ),
                Statement("SELECT changes() AS n"),
            ]
        )
        return int(results[1][0]["n"]) > 0

    def promote(self, run_id: str, activated_at: str) -> bool:
        """Make ``run_id`` the active run in one atomic batch; also used for rollback.

        Only a ``building`` or ``superseded`` run can become active (an already active run is left
        as it is). Returns True when ``active_run`` points at ``run_id`` afterwards.
        """
        self._db.batch(
            [
                Statement(
                    "UPDATE model_runs SET status = 'active', "
                    "finished_at = COALESCE(finished_at, ?) "
                    "WHERE run_id = ? AND status IN ('building', 'superseded')",
                    (activated_at, run_id),
                ),
                Statement(
                    "INSERT INTO active_run (id, run_id, activated_at) "
                    "SELECT 1, ?, ? WHERE EXISTS "
                    "(SELECT 1 FROM model_runs WHERE run_id = ? AND status = 'active') "
                    "ON CONFLICT (id) DO UPDATE SET run_id = excluded.run_id, "
                    "activated_at = CASE WHEN active_run.run_id = excluded.run_id "
                    "THEN active_run.activated_at ELSE excluded.activated_at END",
                    (run_id, activated_at, run_id),
                ),
                Statement(
                    "UPDATE model_runs SET status = 'superseded' "
                    "WHERE status = 'active' AND run_id <> ? "
                    "AND EXISTS (SELECT 1 FROM active_run WHERE id = 1 AND run_id = ?)",
                    (run_id, run_id),
                ),
            ]
        )
        return self.active_run_id() == run_id

    def prunable_run_ids(self, keep: int) -> list[str]:
        """Runs older than the newest ``keep`` (by start time), never the active run."""
        rows = self._db.query(
            "SELECT run_id FROM model_runs WHERE status <> 'active' AND run_id NOT IN "
            "(SELECT run_id FROM model_runs ORDER BY started_at DESC, run_id DESC LIMIT ?) "
            "ORDER BY started_at, run_id",
            (keep,),
        )
        return [str(r["run_id"]) for r in rows]

    def delete_runs(self, run_ids: Sequence[str]) -> int:
        """Delete the runs and their children (children first, because of the foreign keys)."""
        deleted = 0
        for start in range(0, len(run_ids), 30):
            chunk = list(run_ids[start : start + 30])
            marks = ", ".join("?" for _ in chunk)
            self._db.batch(
                [
                    Statement(f"DELETE FROM team_form WHERE run_id IN ({marks})", tuple(chunk)),  # noqa: S608
                    Statement(f"DELETE FROM model_params WHERE run_id IN ({marks})", tuple(chunk)),  # noqa: S608
                    Statement(
                        f"DELETE FROM model_runs WHERE run_id IN ({marks}) AND status <> 'active'",  # noqa: S608
                        tuple(chunk),
                    ),
                ]
            )
            deleted += len(chunk)
        return deleted

    @staticmethod
    def _run(row: Mapping[str, object]) -> RunRecord:
        return RunRecord(
            run_id=str(row["run_id"]),
            status=str(row["status"]),
            started_at=str(row["started_at"]),
            finished_at=_opt_str(row["finished_at"]),
            data_cutoff_utc=_opt_str(row["data_cutoff_utc"]),
            training_from=_opt_str(row["training_from"]),
            training_to=_opt_str(row["training_to"]),
            git_sha=_opt_str(row["git_sha"]),
            code_version=_opt_str(row["code_version"]),
            config_json=str(row["config_json"] or "{}"),
            ensemble_json=str(row["ensemble_json"] or "{}"),
            diagnostics_json=str(row["diagnostics_json"] or "{}"),
        )
