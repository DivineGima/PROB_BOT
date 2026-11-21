"""[v4] Display contract, strongest call, plain metrics and the daily digest (architecture 4,
ADR-054 to ADR-057)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from footy.errors import ExitCode
from footy.models.golden import GOLDEN_DIR
from footy.repo.predictions import PredictionsRepo
from footy.report.digest import ROWS_PER_IMAGE, render_digest, run_digest_job
from footy.report.display import call_hit, favourite, filled_cells, strongest_call
from tests.db_seed import seed_prediction, seed_reference
from tests.helpers import SqliteD1
from tests.test_report import FakeSession, metrics_for, report_row, sender

VECTORS = json.loads((GOLDEN_DIR / "strongest.json").read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", VECTORS)
def test_the_python_strongest_call_gives_the_shared_vectors(case: dict[str, Any]) -> None:
    # apps/bot/src/format/display.ts is checked against the same file by Vitest.
    key, p = strongest_call(case["p1x2"], case["overs"])
    assert key == case["expected"]["key"]
    assert abs(p - case["expected"]["p"]) <= 1e-9
    assert favourite(case["p1x2"])[0] == case["expected"]["favourite"]
    assert filled_cells(case["p1x2"][0]) == case["expected"]["home_cells"]


def test_a_call_is_judged_on_the_score() -> None:
    assert call_hit("over_1.5", 1, 1) and not call_hit("over_1.5", 1, 0)
    assert call_hit("under_3.5", 2, 1) and not call_hit("under_3.5", 2, 2)
    assert call_hit("draw", 0, 0) and not call_hit("home", 0, 1)


def test_the_plain_metrics_are_additive_and_count_hits() -> None:
    rows = [report_row(i, goals=(2, 0) if i % 2 else (1, 1)) for i in range(1, 21)]
    m = metrics_for(rows)
    assert m["strongest"]["n"] == 20 and 0 <= m["strongest"]["hits"] <= 20
    assert set(m["favourite"]["by_band"]) == {"clear", "slight", "open"}
    assert m["favourite"]["hits"] == 10  # the home favourite wins the odd-numbered 2-0 games
    assert m["outcomes"]["home"]["observed"] == 0.5
    assert m["goals"]["actual"] == 2.0 and m["goals"]["expected"] is not None
    assert set(m["overs"]) == {"0.5", "1.5", "2.5", "3.5", "4.5", "5.5"}
    assert "strongest" not in metrics_for([])


def _db(n: int) -> SqliteD1:
    db = SqliteD1()
    seed_reference(db)
    for i in range(n):
        seed_prediction(
            db,
            day=f"2026-10-{i + 1:02d}",
            home=1 + i,
            away=21 + i,
            status="scored",
            goals=(2, 0) if i % 2 else (0, 1),
            rps=(0.2, 0.1, 0.9),
        )
    return db


def clock(at: str) -> Any:
    return lambda: at


def test_the_digest_card_is_a_png() -> None:
    db = _db(3)
    rows = PredictionsRepo(db).scored_after("", 10)
    png = render_digest(rows, "Latest graded predictions")
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and len(png) > 5_000
    with pytest.raises(ValueError):
        render_digest([], "x")


def test_the_digest_sends_once_and_then_nothing_new() -> None:
    db = _db(14)
    db.conn.execute("UPDATE predictions SET scored_at = '2026-10-19T01:30:00Z'")
    session = FakeSession()
    first = run_digest_job(db, sender=sender(session), send=True, now=clock("2026-10-19T02:00:00Z"))
    assert first.exit_code == ExitCode.OK, first.summary
    photos = [c for c in session.calls if c[0].endswith("/sendPhoto")]
    assert len(photos) == 2 and ROWS_PER_IMAGE < 14  # 14 matches: two pictures
    assert first.summary["through"] == "2026-10-19T01:30:00Z"

    again = run_digest_job(db, sender=sender(session), send=True, now=clock("2026-10-20T02:00:00Z"))
    assert again.summary["n"] == 0 and again.summary["through"] == "2026-10-19T01:30:00Z"
    assert len([c for c in session.calls if c[0].endswith("/sendPhoto")]) == 2


def test_the_first_digest_looks_back_48_hours_only() -> None:
    db = _db(4)
    db.conn.execute("UPDATE predictions SET scored_at = '2026-10-01T01:30:00Z'")
    result = run_digest_job(db, now=clock("2026-10-19T02:00:00Z"))
    assert result.summary["first_run"] is True and result.summary["n"] == 0


def test_a_failed_send_is_retried_the_next_night() -> None:
    db = _db(2)
    db.conn.execute("UPDATE predictions SET scored_at = '2026-10-19T01:30:00Z'")
    failing = run_digest_job(
        db, sender=sender(FakeSession([500] * 20)), send=True, now=clock("2026-10-19T02:00:00Z")
    )
    assert failing.exit_code != ExitCode.OK
    session = FakeSession()
    retry = run_digest_job(db, sender=sender(session), send=True, now=clock("2026-10-20T02:00:00Z"))
    assert retry.summary["n"] == 2 and retry.summary.get("sent") == 1
