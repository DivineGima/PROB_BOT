"""``footy healthcheck`` (architecture sections 9.2 and 10, NFR-08): each of the five checks fails
for the reason it names and only then, and a failure becomes one deduplicated alert event."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from footy.errors import ExitCode
from footy.health import run_checks, run_healthcheck_job
from footy.repo.health import HealthRepo
from tests.db_seed import seed_reference, seed_scheduled
from tests.helpers import SqliteD1

NOW = datetime(2026, 10, 18, 2, 0, tzinfo=UTC)
TODAY, TOMORROW = "2026-10-18", "2026-10-19"


@pytest.fixture
def db() -> SqliteD1:
    d = SqliteD1()
    seed_reference(d)
    return d


def activate(db: SqliteD1, run_id: str = "R1", at: str = "2026-10-18T01:30:00Z") -> None:
    db.conn.execute(
        "INSERT INTO model_runs (run_id, status, started_at) VALUES (?, 'active', ?)", (run_id, at)
    )
    db.conn.execute(
        "INSERT INTO active_run (id, run_id, activated_at) VALUES (1, ?, ?)", (run_id, at)
    )


def forecast(db: SqliteD1, run_id: str, day: str, n: int = 1) -> None:
    for i in range(n):
        db.conn.execute(
            "INSERT INTO fixture_forecasts (run_id, fixture_key, comp_code, match_date, "
            "home_team_id, away_team_id, verdict, detail_json, created_at) "
            "VALUES (?, ?, 'EPL', ?, 1, 2, 'NO_MODEL', '{}', 't')",
            (run_id, f"{day}|{i}", day),
        )


def by_name(db: SqliteD1, now: datetime = NOW) -> dict[str, tuple[bool, str]]:
    return {c.name: (c.ok, c.detail) for c in run_checks(HealthRepo(db), now)}


def test_a_healthy_system_passes_every_check(db: SqliteD1) -> None:
    activate(db)
    seed_scheduled(db, [("EPL", TODAY, 1, 2), ("EPL", TOMORROW, 3, 4)])
    forecast(db, "R1", TODAY)
    forecast(db, "R1", TOMORROW)
    checks = by_name(db)
    assert all(ok for ok, _ in checks.values()), checks
    assert set(checks) == {
        "active_run",
        "run_age",
        "forecast_coverage",
        "stuck_uploads",
        "bot_token",
    }


def test_no_published_run_fails_the_run_checks(db: SqliteD1) -> None:
    checks = by_name(db)
    assert not checks["active_run"][0]
    assert not checks["forecast_coverage"][0]
    assert "run_age" not in checks


def test_a_run_older_than_36_hours_is_stale(db: SqliteD1) -> None:
    activate(db, at="2026-10-16T13:00:00Z")  # 37 h before NOW
    ok, detail = by_name(db)["run_age"]
    assert not ok and "37 h old" in detail
    db.conn.execute("UPDATE active_run SET activated_at = '2026-10-16T14:00:00Z'")  # exactly 36 h
    assert by_name(db)["run_age"][0]


def test_an_unreadable_activation_time_fails_instead_of_crashing(db: SqliteD1) -> None:
    activate(db, at="not a time")
    assert not by_name(db)["run_age"][0]


def test_scheduled_fixtures_without_forecasts_fail_the_coverage_check(db: SqliteD1) -> None:
    activate(db)
    seed_scheduled(db, [("EPL", TODAY, 1, 2), ("EPL", TOMORROW, 3, 4)])
    forecast(db, "R1", TODAY)  # tomorrow has none
    ok, detail = by_name(db)["forecast_coverage"]
    assert not ok and TOMORROW in detail and TODAY not in detail


def test_a_day_without_fixtures_needs_no_forecasts(db: SqliteD1) -> None:
    activate(db)
    ok, detail = by_name(db)["forecast_coverage"]
    assert ok and "0 day(s)" in detail


def test_forecasts_of_another_run_do_not_count(db: SqliteD1) -> None:
    activate(db)
    db.conn.execute(
        "INSERT INTO model_runs (run_id, status, started_at) VALUES ('Rold', 'superseded', 't')"
    )
    seed_scheduled(db, [("EPL", TODAY, 1, 2)])
    forecast(db, "Rold", TODAY)
    assert not by_name(db)["forecast_coverage"][0]


def test_an_upload_stuck_for_ten_minutes_fails_but_a_fresh_one_does_not(db: SqliteD1) -> None:
    activate(db)
    db.conn.execute(
        "INSERT INTO uploads (update_id, received_at, status) "
        "VALUES (1, '2026-10-18T01:49:59Z', 'received')"
    )
    db.conn.execute(
        "INSERT INTO uploads (update_id, received_at, status) "
        "VALUES (2, '2026-10-18T01:50:01Z', 'received')"
    )
    db.conn.execute(
        "INSERT INTO uploads (update_id, received_at, status) "
        "VALUES (3, '2026-10-18T01:00:00Z', 'processed')"
    )
    ok, detail = by_name(db)["stuck_uploads"]
    assert not ok and detail.startswith("1 upload")


def test_a_run_uses_its_own_stale_limit_like_the_worker(db: SqliteD1) -> None:
    activate(db, at="2026-10-17T14:00:00Z")  # 12 h old
    assert by_name(db)["run_age"][0]
    db.conn.execute("UPDATE model_runs SET config_json = '{\"stale_hours\": 6}'")
    ok, detail = by_name(db)["run_age"]
    assert not ok and "limit 6 h" in detail
    db.conn.execute('UPDATE model_runs SET config_json = \'{"stale_hours": "soon"}\'')
    assert by_name(db)["run_age"][0]  # unreadable: falls back to 36 h


def test_every_way_the_worker_cannot_speak_fails_the_token_check(db: SqliteD1) -> None:
    activate(db)
    for kind in ("bot_token_missing", "alert_chat_invalid", "alert_send_failed", "watchdog_failed"):
        db.conn.execute("DELETE FROM events")
        db.conn.execute(
            "INSERT INTO events (at, level, source, kind) VALUES (?, 'error', 'bot', ?)",
            ("2026-10-17T20:00:00Z", kind),
        )
        assert not by_name(db)["bot_token"][0], kind
    db.conn.execute("DELETE FROM events")
    assert by_name(db)["bot_token"][0]


def test_a_recent_missing_token_report_fails_the_token_check(db: SqliteD1) -> None:
    activate(db)
    db.conn.execute(
        "INSERT INTO events (at, level, source, kind) "
        "VALUES ('2026-10-17T05:00:00Z', 'error', 'bot', 'bot_token_missing')"
    )
    assert not by_name(db)["bot_token"][0]
    db.conn.execute("UPDATE events SET at = '2026-10-17T01:00:00Z'")  # 25 h ago: fixed since
    assert by_name(db)["bot_token"][0]


# -- the job ----------------------------------------------------------------------------------


def run_job(db: SqliteD1) -> tuple[ExitCode, dict[str, object]]:
    result = run_healthcheck_job(db, now=lambda: "2026-10-18T02:00:00Z")
    return result.exit_code, result.summary


def test_a_healthy_job_exits_zero_and_raises_nothing(db: SqliteD1) -> None:
    activate(db)
    code, summary = run_job(db)
    assert code == ExitCode.OK and summary["healthy"] is True
    assert db.scalar("SELECT COUNT(*) FROM events") == 0
    assert db.scalar("SELECT status FROM job_runs WHERE kind = 'healthcheck'") == "ok"


def test_an_unhealthy_job_exits_one_and_raises_one_alert_per_failed_check(db: SqliteD1) -> None:
    code, summary = run_job(db)  # nothing published
    assert code == ExitCode.UNEXPECTED and summary["healthy"] is False
    kinds = db.rows("SELECT kind, level, dedupe_key FROM events ORDER BY event_id")
    assert {k["dedupe_key"] for k in kinds} == {
        "alert:health:active_run",
        "alert:health:forecast_coverage",
    }
    assert all(k["kind"] == "health_check_failed" and k["level"] == "alert" for k in kinds)


def test_running_again_the_same_day_does_not_alert_twice(db: SqliteD1) -> None:
    run_job(db)
    run_job(db)
    assert db.scalar("SELECT COUNT(*) FROM events") == 2
