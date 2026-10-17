"""`footy score`: settling pending predictions (architecture section 8.7, ADR-028)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from footy.errors import ExitCode
from footy.score.job import run_score_job
from footy.score.settle import kickoff_of, parse_instant, settle
from footy.score.types import PENDING, SCORED, VOID, PendingPrediction
from tests.db_seed import TOTAL_PMF, seed_match, seed_prediction, seed_reference
from tests.helpers import SqliteD1

NOW = datetime(2026, 10, 18, 1, 17, tzinfo=UTC)


def pending(**kwargs: object) -> PendingPrediction:
    base: dict[str, object] = {
        "pred_id": 1,
        "fixture_key": "2026-10-17|EPL|1|2",
        "comp_code": "EPL",
        "match_date": "2026-10-17",
        "kickoff_utc": "2026-10-17T15:00:00Z",
        "p_home": 0.5,
        "p_draw": 0.3,
        "p_away": 0.2,
        "total_json": json.dumps(TOTAL_PMF),
        "match_status": "FINISHED",
        "match_goals_home": 2,
        "match_goals_away": 0,
        "result_basis": "ft_90",
    }
    base.update(kwargs)
    return PendingPrediction(**base)  # type: ignore[arg-type]


# -- the pure rule ----------


def test_a_verified_result_is_scored_with_hand_computed_values() -> None:
    s = settle(pending(), NOW)
    assert s.action == SCORED and (s.goals_home, s.goals_away) == (2, 0)
    # home win: ((0.5-1)^2 + (0.8-1)^2) / 2 = 0.145
    assert s.rps_1x2 == pytest.approx(0.145, abs=1e-12)
    # total 2 (category 2) against the stored pmf, 13 categories
    assert s.rps_totals == pytest.approx(0.31303025 / 12, abs=1e-12)
    assert s.logloss_1x2 == pytest.approx(-__import__("math").log(0.5), abs=1e-12)


@pytest.mark.parametrize(
    ("goals", "rps", "p_observed"),
    [((2, 0), 0.145, 0.5), ((1, 1), 0.145, 0.3), ((0, 3), 0.445, 0.2)],
)
def test_each_outcome_scores_the_ranked_probability(
    goals: tuple[int, int], rps: float, p_observed: float
) -> None:
    s = settle(pending(match_goals_home=goals[0], match_goals_away=goals[1]), NOW)
    assert s.rps_1x2 == pytest.approx(rps, abs=1e-12)
    assert s.logloss_1x2 == pytest.approx(-__import__("math").log(p_observed), abs=1e-12)


def test_a_regular_time_result_after_extra_time_is_also_scored() -> None:
    assert settle(pending(result_basis="regular"), NOW).action == SCORED


@pytest.mark.parametrize("status", ["POSTPONED", "CANCELLED", "SUSPENDED", "AWARDED"])
def test_postponed_cancelled_suspended_awarded_are_void_under_their_own_name(status: str) -> None:
    s = settle(pending(match_status=status, match_goals_home=None, match_goals_away=None), NOW)
    assert (s.action, s.void_reason) == (VOID, status)


def test_an_unverified_or_incomplete_finished_result_waits_and_is_then_voided() -> None:
    """The source can add the 90-minute score later, so it is not given up on at first sight."""
    for kwargs in (
        {"result_basis": "unverified"},
        {"result_basis": None},
        {"match_goals_home": None},
    ):
        assert settle(pending(**kwargs), NOW).action == PENDING, kwargs
        late = settle(pending(**kwargs), datetime(2026, 10, 20, 15, 0, tzinfo=UTC))
        assert (late.action, late.void_reason) == (VOID, "UNVERIFIED_RESULT"), kwargs


def test_an_unplayed_match_stays_pending_until_three_days_after_kickoff() -> None:
    open_match = {"match_status": "TIMED", "match_goals_home": None, "match_goals_away": None}
    assert (
        settle(pending(**open_match), datetime(2026, 10, 20, 14, 59, tzinfo=UTC)).action == PENDING
    )
    s = settle(pending(**open_match), datetime(2026, 10, 20, 15, 0, tzinfo=UTC))
    assert (s.action, s.void_reason) == (VOID, "NO_RESULT")


def test_no_matching_match_row_is_the_rescheduled_case_and_ends_no_result() -> None:
    gone = {"match_status": None, "match_goals_home": None, "match_goals_away": None}
    assert settle(pending(**gone), NOW).action == PENDING
    late = settle(pending(**gone), datetime(2026, 10, 25, tzinfo=UTC))
    assert (late.action, late.void_reason) == (VOID, "NO_RESULT")


def test_an_in_play_match_that_never_finishes_is_closed_too() -> None:
    s = settle(
        pending(match_status="IN_PLAY", match_goals_home=None, match_goals_away=None),
        datetime(2026, 11, 1, tzinfo=UTC),
    )
    assert (s.action, s.void_reason) == (VOID, "NO_RESULT")


def test_an_unreadable_total_distribution_is_left_pending_with_a_note() -> None:
    for bad in ("not json", "[0.5, 0.5]", json.dumps(["a"] * 13), "{}"):
        s = settle(pending(total_json=bad), NOW)
        assert s.action == PENDING and s.note, bad


def test_kickoff_falls_back_to_the_end_of_the_fixture_day() -> None:
    assert kickoff_of(pending(kickoff_utc="garbage")) == datetime(
        2026, 10, 17, 23, 59, 59, tzinfo=UTC
    )
    assert parse_instant("2026-10-17T15:00:00Z") == datetime(2026, 10, 17, 15, tzinfo=UTC)
    assert parse_instant("nonsense") is None


# -- the job on a SQLite-backed fake D1 ----------


@pytest.fixture
def db() -> SqliteD1:
    d = SqliteD1()
    seed_reference(d)
    return d


def stamp(day: str = "2026-10-18") -> object:
    return lambda: f"{day}T01:17:00Z"


def row(db: SqliteD1, pred_id: int) -> dict[str, object]:
    return db.rows("SELECT * FROM predictions WHERE pred_id = ?", (pred_id,))[0]


def test_the_job_scores_voids_and_leaves_open_matches_alone(db: SqliteD1) -> None:
    done = seed_prediction(db, home=1, away=2)
    seed_match(db, home=1, away=2, goals=(2, 0))
    moved = seed_prediction(db, home=3, away=4)
    seed_match(db, home=3, away=4, status="POSTPONED", goals=None, basis=None)
    open_ = seed_prediction(db, home=5, away=6, day="2026-10-19")
    seed_match(db, home=5, away=6, day="2026-10-19", status="TIMED", goals=None, basis=None)

    result = run_score_job(db, now=stamp())  # type: ignore[arg-type]
    assert result.exit_code == ExitCode.OK, result.summary
    assert result.summary["scored"] == 1 and result.summary["still_pending"] == 1
    assert result.summary["voided"] == {"POSTPONED": 1}
    scored = row(db, done)
    assert scored["status"] == "scored" and (scored["goals_home"], scored["goals_away"]) == (2, 0)
    assert (
        scored["rps_1x2"] == pytest.approx(0.145) and scored["scored_at"] == "2026-10-18T01:17:00Z"
    )
    assert (row(db, moved)["status"], row(db, moved)["void_reason"]) == ("void", "POSTPONED")
    assert row(db, open_)["status"] == "pending"
    assert db.scalar("SELECT status FROM job_runs WHERE kind = 'score'") == "ok"


def test_scoring_twice_changes_nothing(db: SqliteD1) -> None:
    pred = seed_prediction(db)
    seed_match(db, goals=(1, 1))
    run_score_job(db, now=stamp())  # type: ignore[arg-type]
    first = row(db, pred)
    again = run_score_job(db, now=stamp("2026-10-19"))  # type: ignore[arg-type]
    assert again.summary["pending_before"] == 0 and again.exit_code == ExitCode.OK
    assert row(db, pred) == first


def test_a_late_result_scores_a_prediction_that_was_pending_the_night_before(
    db: SqliteD1,
) -> None:
    pred = seed_prediction(db)
    seed_match(db, status="IN_PLAY", goals=None, basis=None)
    run_score_job(db, now=stamp())  # type: ignore[arg-type]
    assert row(db, pred)["status"] == "pending"
    db.conn.execute(
        "UPDATE matches SET status = 'FINISHED', goals_home = 3, goals_away = 1, "
        "result_basis = 'regular'"
    )
    run_score_job(db, now=stamp("2026-10-19"))  # type: ignore[arg-type]
    assert (row(db, pred)["status"], row(db, pred)["goals_home"]) == ("scored", 3)


def test_a_rescheduled_match_ends_no_result_and_raises_one_alert(db: SqliteD1) -> None:
    # the match moved to the 25th, so the prediction's key date matches no row
    first = seed_prediction(db, home=1, away=2)
    second = seed_prediction(db, home=3, away=4)
    seed_match(db, home=1, away=2, day="2026-10-25", status="TIMED", goals=None, basis=None)
    seed_match(db, home=3, away=4, day="2026-10-25", status="TIMED", goals=None, basis=None)
    early = run_score_job(db, now=stamp("2026-10-19"))  # type: ignore[arg-type]
    assert early.summary["still_pending"] == 2
    assert db.scalar("SELECT COUNT(*) FROM events WHERE kind = 'no_result_voided'") == 0

    result = run_score_job(db, now=stamp("2026-10-21"))  # type: ignore[arg-type]
    assert result.summary["voided"] == {"NO_RESULT": 2}
    assert {row(db, first)["void_reason"], row(db, second)["void_reason"]} == {"NO_RESULT"}
    events = db.rows("SELECT detail_json FROM events WHERE kind = 'no_result_voided'")
    assert len(events) == 1
    detail = json.loads(events[0]["detail_json"])
    assert detail["count"] == 2 and detail["fixtures"] == [
        "2026-10-17|EPL|1|2",
        "2026-10-17|EPL|3|4",
    ]


def test_an_unverified_result_is_never_scored_and_is_scored_once_it_is_verified(
    db: SqliteD1,
) -> None:
    pred = seed_prediction(db)
    seed_match(db, basis="unverified")
    run_score_job(db, now=stamp())  # type: ignore[arg-type]
    assert row(db, pred)["status"] == "pending"  # one day after kickoff: still waiting
    # the source adds the 90-minute score the next night
    db.conn.execute("UPDATE matches SET result_basis = 'regular'")
    run_score_job(db, now=stamp("2026-10-19"))  # type: ignore[arg-type]
    assert (row(db, pred)["status"], row(db, pred)["goals_home"]) == ("scored", 2)


def test_an_unverified_result_that_stays_unverified_is_void_after_the_window(db: SqliteD1) -> None:
    pred = seed_prediction(db)
    seed_match(db, basis="unverified")
    run_score_job(db, now=stamp("2026-10-21"))  # type: ignore[arg-type]
    assert (row(db, pred)["status"], row(db, pred)["void_reason"]) == ("void", "UNVERIFIED_RESULT")


def test_a_corrupt_prediction_is_reported_not_scored_and_does_not_stop_the_others(
    db: SqliteD1,
) -> None:
    broken = seed_prediction(db, home=1, away=2)
    db.conn.execute("UPDATE predictions SET total_json = 'garbage' WHERE pred_id = ?", (broken,))
    fine = seed_prediction(db, home=3, away=4)
    seed_match(db, home=1, away=2)
    seed_match(db, home=3, away=4)
    result = run_score_job(db, now=stamp())  # type: ignore[arg-type]
    assert result.exit_code == ExitCode.OK
    assert result.summary["unreadable"] == [broken]
    assert row(db, broken)["status"] == "pending" and row(db, fine)["status"] == "scored"
    assert db.scalar("SELECT COUNT(*) FROM events WHERE kind = 'score_unreadable'") == 1


def test_the_job_is_recorded_and_works_with_nothing_to_do(db: SqliteD1) -> None:
    result = run_score_job(db, now=stamp())  # type: ignore[arg-type]
    assert result.exit_code == ExitCode.OK and result.summary["pending_before"] == 0
    assert db.scalar("SELECT COUNT(*) FROM job_runs WHERE kind = 'score'") == 1


def test_a_database_outage_is_reported_not_raised(db: SqliteD1) -> None:
    seed_prediction(db)
    db.fail_when = lambda statements: "FROM predictions p" in statements[0].sql
    db.fail_next = None
    result = run_score_job(db, now=stamp())  # type: ignore[arg-type]
    assert result.exit_code == ExitCode.UNEXPECTED and "injected" in str(result.summary["error"])


def test_updates_never_touch_a_row_that_is_no_longer_pending(db: SqliteD1) -> None:
    from footy.repo.predictions import PredictionsRepo
    from footy.score.types import Settlement

    pred = seed_prediction(db, status="scored", goals=(1, 0), rps=(0.1, 0.1, 0.5))
    PredictionsRepo(db).apply(
        [
            Settlement(
                pred,
                SCORED,
                goals_home=9,
                goals_away=9,
                rps_1x2=0.9,
                rps_totals=0.9,
                logloss_1x2=9.0,
            )
        ],
        "2026-10-19T00:00:00Z",
    )
    assert (row(db, pred)["goals_home"], row(db, pred)["rps_1x2"]) == (1, 0.1)


def test_scoring_and_voiding_change_only_the_result_columns(db: SqliteD1) -> None:
    """Invariant 2 (section 5.7): a prediction's forecast is never modified; only the result and
    scoring columns are written."""
    scored = seed_prediction(db, home=1, away=2)
    seed_match(db, home=1, away=2, goals=(0, 3))
    voided = seed_prediction(db, home=3, away=4)
    seed_match(db, home=3, away=4, status="CANCELLED", goals=None, basis=None)
    before = {i: row(db, i) for i in (scored, voided)}
    run_score_job(db, now=stamp())  # type: ignore[arg-type]
    result_columns = {
        "status", "void_reason", "goals_home", "goals_away", "rps_1x2", "rps_totals",
        "logloss_1x2", "scored_at",
    }  # fmt: skip
    for pred_id, old in before.items():
        new = row(db, pred_id)
        changed = {k for k in old if old[k] != new[k]}
        assert changed and changed <= result_columns, changed
