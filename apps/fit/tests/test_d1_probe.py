"""The probe's decision logic, run against a fake server that behaves like SQLite-backed D1."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from footy.repo.d1_client import D1Client, HttpResult
from footy.repo.d1_probe import probe

MIGRATION = (
    Path(__file__).resolve().parents[3] / "db" / "migrations" / "0001_foundations.sql"
).read_text(encoding="utf-8")


class SqliteBackedD1:
    """Runs REST batches on SQLite. ``atomic`` controls whether a failure rolls the batch back."""

    def __init__(self, *, atomic: bool, max_params: int = 100) -> None:
        self.db = sqlite3.connect(":memory:", isolation_level=None)
        self.db.executescript(MIGRATION)
        self.atomic = atomic
        self.max_params = max_params

    def post(
        self, url: str, headers: Mapping[str, str], body: object, timeout: float
    ) -> HttpResult:
        statements = body["batch"]  # type: ignore[index]
        results: list[dict[str, Any]] = []
        if self.atomic:
            self.db.execute("BEGIN")
        try:
            for item in statements:
                if len(item["params"]) > self.max_params:
                    raise sqlite3.OperationalError("too many SQL variables")
                cursor = self.db.execute(item["sql"], item["params"])
                names = [d[0] for d in cursor.description or []]
                rows = [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]
                results.append({"success": True, "results": rows, "meta": {}})
        except sqlite3.Error as exc:
            if self.atomic:
                self.db.execute("ROLLBACK")
            payload = {"success": False, "errors": [{"code": 7500, "message": str(exc)}]}
            return HttpResult(400, payload)
        if self.atomic:
            self.db.execute("COMMIT")
        return HttpResult(200, {"success": True, "errors": [], "result": results})


def run(server: SqliteBackedD1) -> dict[str, Any]:
    return probe(D1Client("a", "d", "tok", transport=server, sleep=lambda _s: None))


def test_probe_reports_a_server_with_batch_100_limit_and_atomic_batches() -> None:
    report = run(SqliteBackedD1(atomic=True))
    assert report == {
        "batch_supported": True,
        "params_100_accepted": True,
        "params_101_accepted": False,
        "atomic_batch": True,
    }


def test_probe_detects_a_non_atomic_batch_and_cleans_up_its_marker_row() -> None:
    server = SqliteBackedD1(atomic=False)
    report = run(server)
    assert report["atomic_batch"] is False
    assert server.db.execute("SELECT COUNT(*) FROM events").fetchone() == (0,)


def test_probe_detects_a_different_parameter_limit() -> None:
    report = run(SqliteBackedD1(atomic=True, max_params=50))
    assert report["params_100_accepted"] is False
    assert report["params_101_accepted"] is False
