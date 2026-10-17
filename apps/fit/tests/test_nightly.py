"""The whole nightly job on hand-written source fixtures and a SQLite-backed fake D1 (essentials 2,
Stage 6 step 8; PRD_2 testing): ``ingest``, ``score``, ``fit``, ``publish`` in order, across two
nights, with a prediction logged in between exactly as the Worker would log it.

Asserts what the exit criteria promise: a promoted run that carries forecasts, a prediction that is
scored automatically once its result arrives, rolling ensemble weights built from it, and no
unmapped teams anywhere along the way.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

import pytest

from footy.aliases import load_reference
from footy.errors import ExitCode
from footy.fitting import run_fit_job
from footy.ingest.pipeline import run_bootstrap, run_ingest, seed_reference
from footy.publish.job import run_publish_job
from footy.repo.d1_client import MemoryProgress
from footy.report.job import run_report_job
from footy.score.job import run_score_job
from tests.helpers import ScriptedTransport, SqliteD1, fd_match, make_client

REF = load_reference()
CLUBS = [
    "Arsenal FC",
    "Chelsea FC",
    "Liverpool FC",
    "Manchester City FC",
    "Newcastle United FC",
    "Brighton & Hove Albion FC",
    "Everton FC",
    "Fulham FC",
    "Brentford FC",
    "Aston Villa FC",
    "West Ham United FC",
    "Tottenham Hotspur FC",
]
SEASON_START = "2026-08-15"


def night(day: str, hh_mm: str = "01:17") -> str:
    return f"{day}T{hh_mm}:00Z"


def clock(day: str) -> Any:
    return lambda: night(day)


def goals_for(i: int, j: int) -> tuple[int, int]:
    """Deterministic, low-variance scores: hand-written in spirit, no randomness."""
    return (i + 2 * j) % 3, (2 * i + j + 1) % 3


def round_robin(start: date, rounds: int) -> list[dict[str, Any]]:
    """Finished matches of the 12 clubs, six per round, four days apart (circle method)."""
    clubs = list(range(len(CLUBS)))
    out: list[dict[str, Any]] = []
    match_id = 1
    for r in range(rounds):
        day = start + timedelta(days=4 * r)
        rotated = [clubs[0], *clubs[1:][-(r % 11) :], *clubs[1:][: -(r % 11) or None]]
        for k in range(6):
            a, b = rotated[k], rotated[11 - k]
            home, away = (a, b) if (r + k) % 2 == 0 else (b, a)
            gh, ga = goals_for(home, away)
            out.append(
                fd_match(
                    match_id,
                    CLUBS[home],
                    CLUBS[away],
                    f"{day.isoformat()}T14:00:00Z",
                    full=(gh, ga),
                    season_start=SEASON_START,
                )
            )
            match_id += 1
    return out


def scheduled(match_id: int, home: int, away: int, day: str) -> dict[str, Any]:
    return fd_match(
        match_id,
        CLUBS[home],
        CLUBS[away],
        f"{day}T14:00:00Z",
        status="TIMED",
        duration=None,
        full=(None, None),
        season_start=SEASON_START,
    )


def finished(
    match_id: int, home: int, away: int, day: str, score: tuple[int, int]
) -> dict[str, Any]:
    return fd_match(
        match_id,
        CLUBS[home],
        CLUBS[away],
        f"{day}T14:00:00Z",
        full=score,
        season_start=SEASON_START,
    )


def ingest(db: SqliteD1, day: str, matches: list[dict[str, Any]]) -> Any:
    transport = ScriptedTransport({("PL", "window"): {"matches": matches}})
    return run_ingest(
        make_client(transport),
        db=db,
        today=date.fromisoformat(day),
        now=clock(day),
        check_team_lists=False,
    )


def worker_logs(db: SqliteD1, day: str) -> int:
    """What the Worker does with an upload: copy each stored ok forecast of `day` into the log."""
    db.conn.execute(
        "INSERT OR IGNORE INTO uploads (upload_id, update_id, received_at, status) "
        "VALUES (1, 1, ?, 'processed')",
        (night(day, "06:00"),),
    )
    cursor = db.conn.execute(
        "INSERT OR IGNORE INTO predictions (fixture_key, upload_id, run_id, label, comp_code, "
        "match_date, kickoff_utc, home_team_id, away_team_id, p_home, p_draw, p_away, p_over_05, "
        "p_over_15, p_over_25, p_over_35, p_over_45, p_over_55, total_json, models_json, "
        "weights_json, drift_json, baseline_json, inputs_json, created_at) "
        "SELECT fixture_key, 1, run_id, fixture_key, comp_code, match_date, kickoff_utc, "
        "home_team_id, away_team_id, p_home, p_draw, p_away, p_over_05, p_over_15, p_over_25, "
        "p_over_35, p_over_45, p_over_55, total_json, models_json, weights_json, detail_json, "
        "baseline_json, '{}', ? FROM fixture_forecasts WHERE verdict = 'ok' AND match_date = ? "
        "AND run_id = (SELECT run_id FROM active_run WHERE id = 1)",
        (night(day, "06:30"), day),
    )
    return int(cursor.rowcount)


@pytest.fixture(scope="module")
def two_nights() -> dict[str, Any]:
    db = SqliteD1()
    seed_reference(db, REF, MemoryProgress())
    history = round_robin(date(2026, 8, 15), rounds=14)  # 84 matches, 14 per club
    boot = run_bootstrap(
        make_client(ScriptedTransport({("PL", "season:2026"): {"matches": history}})),
        REF,
        db=db,
        today=date(2026, 10, 10),
        seasons=[2026],
        now=clock("2026-10-10"),
    )
    assert boot.exit_code == ExitCode.OK, boot.summary

    pairs = [(0, 1), (2, 3), (4, 5), (6, 7), (8, 9), (10, 11)]
    # -- night 1 (16 October): the fixtures of the 17th are known; nothing to score yet --------
    night1: dict[str, Any] = {}
    fixtures17 = [scheduled(1000 + k, h, a, "2026-10-17") for k, (h, a) in enumerate(pairs)]
    night1["ingest"] = ingest(db, "2026-10-16", fixtures17)
    night1["score"] = run_score_job(db, now=clock("2026-10-16"))
    night1["fit"] = run_fit_job(db, now=clock("2026-10-16"), git_sha="sha-1")
    night1["publish"] = run_publish_job(db, now=clock("2026-10-16"))
    logged = worker_logs(db, "2026-10-17")  # Divine uploads on the morning of the 17th

    # -- night 2 (18 October): the 17th has been played, the 19th is scheduled -----------------
    results = [finished(1000 + k, h, a, "2026-10-17", (2, 1)) for k, (h, a) in enumerate(pairs)]
    fixtures19 = [scheduled(2000 + k, a, h, "2026-10-19") for k, (h, a) in enumerate(pairs)]
    night2: dict[str, Any] = {}
    night2["ingest"] = ingest(db, "2026-10-18", results + fixtures19)
    night2["score"] = run_score_job(db, now=clock("2026-10-18"))
    night2["fit"] = run_fit_job(db, now=clock("2026-10-18"), git_sha="sha-2")
    night2["publish"] = run_publish_job(db, now=clock("2026-10-18"))
    return {"db": db, "night1": night1, "night2": night2, "logged": logged, "boot": boot}


def test_every_step_of_both_nights_succeeds_in_order(two_nights: dict[str, Any]) -> None:
    for name in ("night1", "night2"):
        for step, result in two_nights[name].items():
            assert result.exit_code == ExitCode.OK, (name, step, result.summary)
    kinds = [r["kind"] for r in two_nights["db"].rows("SELECT kind FROM job_runs ORDER BY job_id")]
    assert kinds == ["bootstrap", "ingest", "score", "fit", "publish"] * 1 + [
        "ingest",
        "score",
        "fit",
        "publish",
    ]
    assert {r["status"] for r in two_nights["db"].rows("SELECT status FROM job_runs")} == {"ok"}


def test_no_team_is_unmapped_anywhere(two_nights: dict[str, Any]) -> None:
    db: SqliteD1 = two_nights["db"]
    assert db.scalar("SELECT COUNT(*) FROM events WHERE kind = 'unmapped_team'") == 0
    for name in ("night1", "night2"):
        assert two_nights[name]["ingest"].summary["unmapped_teams"] == {}
    assert two_nights["boot"].summary["unmapped_teams"] == {}


def test_the_first_night_promotes_a_run_that_carries_the_forecasts(
    two_nights: dict[str, Any],
) -> None:
    db: SqliteD1 = two_nights["db"]
    publish = two_nights["night1"]["publish"].summary
    assert publish["result"] == "promoted"
    summary = two_nights["night1"]["fit"].summary
    assert summary["forecasts"] == 6
    run1 = str(summary["run_id"])
    assert db.scalar("SELECT COUNT(*) FROM fixture_forecasts WHERE run_id = ?", (run1,)) == 6
    verdicts = summary["forecast_verdicts"]
    assert verdicts.get("ok", 0) >= 1, f"the stable synthetic league should forecast: {verdicts}"
    assert two_nights["logged"] == verdicts["ok"]


def test_the_second_night_promotes_a_new_run_and_supersedes_the_first(
    two_nights: dict[str, Any],
) -> None:
    db: SqliteD1 = two_nights["db"]
    run1 = str(two_nights["night1"]["fit"].summary["run_id"])
    run2 = str(two_nights["night2"]["fit"].summary["run_id"])
    assert run1 != run2
    assert db.scalar("SELECT run_id FROM active_run") == run2
    assert db.scalar("SELECT status FROM model_runs WHERE run_id = ?", (run1,)) == "superseded"
    assert db.scalar("SELECT status FROM model_runs WHERE run_id = ?", (run2,)) == "active"
    assert db.scalar("SELECT COUNT(*) FROM fixture_forecasts WHERE run_id = ?", (run2,)) == 6
    forecast_days = {
        r["match_date"]
        for r in db.rows(
            "SELECT DISTINCT match_date FROM fixture_forecasts WHERE run_id = ?", (run2,)
        )
    }
    assert forecast_days == {"2026-10-19"}


def test_the_logged_predictions_are_scored_automatically_after_the_results_arrive(
    two_nights: dict[str, Any],
) -> None:
    db: SqliteD1 = two_nights["db"]
    logged = two_nights["logged"]
    score = two_nights["night2"]["score"].summary
    assert score["scored"] == logged and score["still_pending"] == 0
    rows = db.rows("SELECT * FROM predictions")
    assert len(rows) == logged and {r["status"] for r in rows} == {"scored"}
    for r in rows:
        assert (r["goals_home"], r["goals_away"]) == (2, 1)
        assert 0.0 <= r["rps_1x2"] <= 1.0 and r["scored_at"] == night("2026-10-18")
    # nothing was scored on the first night: the predictions did not exist yet
    assert two_nights["night1"]["score"].summary["pending_before"] == 0


def test_the_scored_predictions_feed_the_second_nights_ensemble_weights(
    two_nights: dict[str, Any],
) -> None:
    db: SqliteD1 = two_nights["db"]
    run2 = str(two_nights["night2"]["fit"].summary["run_id"])
    run1 = str(two_nights["night1"]["fit"].summary["run_id"])
    first = json.loads(db.scalar("SELECT ensemble_json FROM model_runs WHERE run_id = ?", (run1,)))
    second = json.loads(db.scalar("SELECT ensemble_json FROM model_runs WHERE run_id = ?", (run2,)))
    assert first["method"] != "rolling_rps" and first["n_scored"] == 0
    assert second["method"] == "rolling_rps" and second["n_scored"] == two_nights["logged"]
    assert sum(second["weights"].values()) == pytest.approx(1.0)


def test_the_weekly_report_can_be_built_from_the_nights_results(two_nights: dict[str, Any]) -> None:
    db: SqliteD1 = two_nights["db"]
    report = run_report_job(db, now=clock("2026-10-19"))
    assert report.exit_code == ExitCode.OK
    assert report.summary["n_scored"] == two_nights["logged"]
    assert db.scalar("SELECT COUNT(*) FROM calibration_snapshots") == 1
