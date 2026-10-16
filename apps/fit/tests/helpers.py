"""Test doubles shared by the Stage 2 tests. All data is synthetic or hand-written (ADR-025)."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from footy.ingest.fd_org import FdOrgClient, HttpResponse
from footy.ingest.pacer import Pacer
from footy.repo.d1_client import D1PermanentError, D1TransientError, Row, Statement

MIGRATIONS = Path(__file__).resolve().parents[3] / "db" / "migrations"
TOKEN = "fd-secret-token-abc123"


class SqliteD1:
    """A D1 client backed by in-memory SQLite with every migration applied.

    ``batch`` is atomic like D1's: a failing statement rolls the whole batch back.
    """

    def __init__(self) -> None:
        self.conn = sqlite3.connect(":memory:", isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        for path in sorted(MIGRATIONS.glob("*.sql")):
            self.conn.executescript(path.read_text(encoding="utf-8"))
        self.requests = 0
        self.fail_next: Exception | None = None
        self.fail_at_request: int | None = None
        self.fail_when: Callable[[Sequence[Statement]], bool] | None = None
        self.sent: list[str] = []

    def query(self, sql: str, params: Sequence[object] = ()) -> list[Row]:
        return self.batch([Statement(sql, tuple(params))])[0]  # type: ignore[arg-type]

    def batch(self, statements: Sequence[Statement]) -> list[list[Row]]:
        self.requests += 1
        self.sent.append(statements[0].sql if statements else "")
        if self.fail_when is not None and self.fail_when(statements):
            self.fail_when = None
            raise D1TransientError("injected failure")
        if self.fail_at_request == self.requests:
            raise D1TransientError("injected failure")
        if self.fail_next is not None:
            error, self.fail_next = self.fail_next, None
            raise error
        out: list[list[Row]] = []
        self.conn.execute("BEGIN")
        try:
            for s in statements:
                cursor = self.conn.execute(s.sql, s.params)
                out.append([dict(r) for r in cursor.fetchall()])
        except sqlite3.Error as exc:
            self.conn.execute("ROLLBACK")
            raise D1PermanentError(f"sql error: {exc}") from None
        self.conn.execute("COMMIT")
        return out

    def scalar(self, sql: str, params: Sequence[object] = ()) -> Any:
        return self.conn.execute(sql, params).fetchone()[0]

    def rows(self, sql: str, params: Sequence[object] = ()) -> list[dict[str, Any]]:
        return [dict(r) for r in self.conn.execute(sql, params).fetchall()]


class ScriptedTransport:
    """Football-data.org transport double.

    ``routes`` maps ``(competition_code, kind)`` to a payload (200) or an int HTTP status.
    ``kind`` is
    ``"season:2025"``, ``"window"`` or ``"teams"``. Unknown routes answer 200 with no matches.
    ``sequence`` (if given) overrides routing: responses are returned in order.
    """

    def __init__(
        self,
        routes: Mapping[tuple[str, str], object] | None = None,
        sequence: Sequence[HttpResponse | Exception] | None = None,
    ) -> None:
        self.routes = dict(routes or {})
        self.sequence = list(sequence or [])
        self.calls: list[dict[str, Any]] = []

    def get(
        self, url: str, headers: Mapping[str, str], params: Mapping[str, str], timeout: float
    ) -> HttpResponse:
        self.calls.append({"url": url, "headers": dict(headers), "params": dict(params)})
        if self.sequence:
            item = self.sequence.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        parts = url.split("/competitions/")[1].split("/")
        code, tail = parts[0], parts[1]
        if tail == "teams":
            kind = "teams"
        elif "season" in params:
            kind = f"season:{params['season']}"
        else:
            kind = "window"
        route = self.routes.get((code, kind))
        if isinstance(route, int):
            return HttpResponse(route, b"{}")
        if route is None:
            route = {"teams": []} if kind == "teams" else {"matches": []}
        return HttpResponse(200, json.dumps(route).encode())


def make_client(
    transport: ScriptedTransport,
    *,
    sleeps: list[float] | None = None,
    max_attempts: int = 3,
) -> FdOrgClient:
    record = sleeps if sleeps is not None else []
    return FdOrgClient(
        TOKEN,
        transport=transport,
        pacer=Pacer(0),
        max_attempts=max_attempts,
        base_delay=0.0,
        sleep=record.append,
        rng=lambda: 0.5,
        now=lambda: "2026-10-17T01:17:00Z",
    )


def fd_match(
    match_id: int,
    home: str | None,
    away: str | None,
    utc: str = "2025-10-18T14:00:00Z",
    *,
    status: str = "FINISHED",
    duration: str | None = "REGULAR",
    full: tuple[int | None, int | None] = (2, 1),
    regular: tuple[int | None, int | None] | None = None,
    season_start: str | None = "2025-08-15",
) -> dict[str, Any]:
    score: dict[str, Any] = {"fullTime": {"home": full[0], "away": full[1]}}
    if duration is not None:
        score["duration"] = duration
    if regular is not None:
        score["regularTime"] = {"home": regular[0], "away": regular[1]}
    raw: dict[str, Any] = {
        "id": match_id,
        "utcDate": utc,
        "status": status,
        "homeTeam": {"name": home},
        "awayTeam": {"name": away},
        "score": score,
    }
    if season_start is not None:
        raw["season"] = {"startDate": season_start}
    return raw


Factory = Callable[[], SqliteD1]
