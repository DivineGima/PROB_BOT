"""`footy fit` and `footy publish` against a SQLite-backed fake D1 (Stage 4 exit criteria)."""

from __future__ import annotations

import json
from collections.abc import Callable

import pytest

from footy.errors import ExitCode
from footy.fitting import CODE_VERSION, run_fit_job
from footy.models.registry import load_model
from footy.models.types import FitConfig
from footy.payload import payload_sha256
from footy.publish.job import run_publish_job
from footy.repo.d1_client import D1TransientError
from footy.repo.models import ModelRegistryRepo
from tests.db_seed import seed_world
from tests.helpers import SqliteD1
from tests.synthetic import SyntheticWorld, generate_world


def stamp(second: int) -> Callable[[], str]:
    """A clock that always answers one fixed time, so each run gets its own run id."""
    return lambda: f"2026-06-01T01:17:{second:02d}Z"


@pytest.fixture(scope="module")
def world() -> SyntheticWorld:
    return generate_world(seed=41, n_leagues=3, teams_per_league=10, seasons=3)


@pytest.fixture(scope="module")
def fitted(world: SyntheticWorld) -> SqliteD1:
    """A database that has results and ONE built (not yet published) run. Tests clone it."""
    db = SqliteD1()
    seed_world(db, world)
    result = run_fit_job(db, now=stamp(1), git_sha="sha-1")
    assert result.exit_code == ExitCode.OK, result.summary
    return db


def clone(source: SqliteD1) -> SqliteD1:
    copy = SqliteD1()
    source.conn.backup(copy.conn)
    return copy


def run_ids(db: SqliteD1, status: str | None = None) -> list[str]:
    if status is None:
        return [r["run_id"] for r in db.rows("SELECT run_id FROM model_runs ORDER BY run_id")]
    return [
        r["run_id"]
        for r in db.rows(
            "SELECT run_id FROM model_runs WHERE status = ? ORDER BY run_id", (status,)
        )
    ]


def fit_again(db: SqliteD1, second: int) -> str:
    result = run_fit_job(db, now=stamp(second))
    assert result.exit_code == ExitCode.OK, result.summary
    return str(result.summary["run_id"])


# -- fit ----------


def test_fit_writes_a_building_run_with_everything_the_worker_needs(fitted: SqliteD1) -> None:
    run = fitted.rows("SELECT * FROM model_runs")[0]
    assert run["run_id"] == "R20260601T011701Z" and run["status"] == "building"
    assert run["git_sha"] == "sha-1" and run["code_version"] == CODE_VERSION
    config = json.loads(run["config_json"])
    assert config["unvalidated"] is True and config["models"] == ["dc", "pi", "bp"]
    assert config["min_team_matches"] == 10 and config["drift"]["threshold_goals"] == 0.6
    assert set(config["baseline"]["frequencies"]) >= {"*", "EPL"}
    ensemble = json.loads(run["ensemble_json"])
    assert ensemble["method"] == "equal" and sum(ensemble["weights"].values()) == pytest.approx(1.0)
    diagnostics = json.loads(run["diagnostics_json"])
    assert diagnostics["failed_models"] == [] and "EPL" in diagnostics["freshness"]
    assert run["training_from"] < run["training_to"] <= run["data_cutoff_utc"]


def test_every_model_is_stored_ok_with_a_verifiable_hash_and_loadable_payload(
    fitted: SqliteD1,
) -> None:
    rows = fitted.rows("SELECT * FROM model_params ORDER BY model")
    assert [r["model"] for r in rows] == ["bp", "dc", "pi"]
    for r in rows:
        assert r["status"] == "ok" and r["error"] is None
        assert payload_sha256(r["payload_json"]) == r["payload_sha256"]
        model = load_model(r["model"], json.loads(r["payload_json"]))
        assert model.grid(1, 15, "UCL").sum() == pytest.approx(1.0, abs=1e-12)


def test_team_form_has_a_row_for_every_active_team(fitted: SqliteD1) -> None:
    assert fitted.scalar("SELECT COUNT(*) FROM team_form") == 30
    assert fitted.scalar("SELECT COUNT(*) FROM teams WHERE active = 1") == 30
    row = fitted.rows("SELECT * FROM team_form WHERE team_id = 1")[0]
    assert row["n_training"] > 10 and row["l10_n"] == 10 and row["shots_n"] is None


def test_the_fit_job_is_recorded(fitted: SqliteD1) -> None:
    job = fitted.rows("SELECT kind, status, summary_json FROM job_runs WHERE kind = 'fit'")[0]
    assert job["status"] == "ok"
    assert json.loads(job["summary_json"])["models_ok"] == ["dc", "pi", "bp"]


def test_a_backtest_summary_sets_the_initial_ensemble_weights(world: SyntheticWorld) -> None:
    db = SqliteD1()
    seed_world(db, world)
    summary = {
        "result": {
            "fit_config": {"half_life_days": 300.0, "shrink_team": 4.0},  # the fit's own settings
            "models": {
                "dc": {"overall": {"rps_1x2": 0.200, "n": 2000}},
                "pi": {"overall": {"rps_1x2": 0.215, "n": 2000}},
                "bp": {"overall": {"rps_1x2": 0.201, "n": 2000}},
            },
        }
    }
    db.conn.execute(
        "INSERT INTO job_runs (kind, started_at, status, summary_json) "
        "VALUES ('backtest', 't', 'ok', ?)",
        (json.dumps(summary),),
    )
    result = run_fit_job(db, now=stamp(2))
    ensemble = result.summary["ensemble"]
    assert isinstance(ensemble, dict) and ensemble["method"] == "backtest_prior"
    weights = ensemble["weights"]
    assert weights["dc"] > weights["bp"] > weights["pi"]


def test_a_failing_model_is_stored_failed_and_alerted_and_the_others_continue(
    world: SyntheticWorld,
) -> None:
    db = SqliteD1()
    seed_world(db, world)
    # a tiny strength bound fails dc and bp; pi has its own bound and still fits
    result = run_fit_job(db, config=FitConfig(max_abs_strength=0.05), now=stamp(3))
    assert result.exit_code == ExitCode.FIT
    assert result.summary["models_ok"] == ["pi"]
    failed = result.summary["models_failed"]
    assert isinstance(failed, dict) and set(failed) == {"dc", "bp"}
    rows = {r["model"]: r for r in db.rows("SELECT * FROM model_params")}
    assert rows["dc"]["status"] == "failed" and rows["dc"]["payload_json"] is None
    assert "exceeds the bound" in rows["dc"]["error"]
    assert rows["pi"]["status"] == "ok"
    assert db.rows("SELECT status FROM model_runs")[0]["status"] == "building"
    weights = json.loads(db.rows("SELECT ensemble_json FROM model_runs")[0]["ensemble_json"])
    assert weights["weights"] == {"pi": 1.0}
    assert db.scalar("SELECT COUNT(*) FROM events WHERE kind = 'model_failed'") == 2
    assert db.rows("SELECT status FROM job_runs WHERE kind = 'fit'")[0]["status"] == "partial"


def test_when_every_model_fails_the_run_is_failed_and_has_no_form(world: SyntheticWorld) -> None:
    db = SqliteD1()
    seed_world(db, world)
    result = run_fit_job(
        db, config=FitConfig(max_abs_strength=0.05, min_mean_lambda=5.0), now=stamp(4)
    )
    assert result.exit_code == ExitCode.FIT
    assert result.summary["run_status"] == "failed" and result.summary["models_ok"] == []
    assert db.rows("SELECT status FROM model_runs")[0]["status"] == "failed"
    assert db.scalar("SELECT COUNT(*) FROM team_form") == 0
    assert db.scalar("SELECT COUNT(*) FROM events WHERE kind = 'all_models_failed'") == 1
    # a failed run can never be published
    publish = run_publish_job(db, now=stamp(5))
    assert publish.exit_code == ExitCode.DATA  # no 'building' run exists
    assert db.scalar("SELECT COUNT(*) FROM active_run") == 0


def test_fit_with_no_results_is_a_data_error() -> None:
    db = SqliteD1()
    result = run_fit_job(db)
    assert result.exit_code == ExitCode.DATA and "bootstrap" in str(result.summary["error"])
    assert db.rows("SELECT status FROM job_runs")[0]["status"] == "failed"


def test_fit_rejects_unknown_models_and_a_repeated_run_id(fitted: SqliteD1) -> None:
    db = clone(fitted)
    assert run_fit_job(db, models=["nope"], now=stamp(9)).exit_code == ExitCode.DATA
    again = run_fit_job(db, now=stamp(1))  # same second -> same run id
    assert again.exit_code == ExitCode.DATA and "already exists" in str(again.summary["error"])


def test_as_of_limits_the_data_used(world: SyntheticWorld) -> None:
    from datetime import timedelta

    db = SqliteD1()
    seed_world(db, world)
    early = world.as_of - timedelta(days=200)
    result = run_fit_job(db, models=["dc"], as_of=early, now=stamp(6))
    assert result.exit_code == ExitCode.OK
    run = db.rows("SELECT * FROM model_runs")[0]
    # the cut-off is the latest result actually used, not the newest result in the database
    assert run["data_cutoff_utc"] == run["training_to"] <= early.isoformat()
    assert str(result.summary["newest_stored_result"]) > early.isoformat()


def test_a_database_failure_during_fit_is_reported_not_raised(world: SyntheticWorld) -> None:
    db = SqliteD1()
    seed_world(db, world)
    db.fail_when = lambda statements: "INSERT OR IGNORE INTO model_params" in statements[0].sql
    result = run_fit_job(db, models=["dc"], now=stamp(7))
    assert result.exit_code == ExitCode.UNEXPECTED
    assert db.rows("SELECT status FROM job_runs WHERE kind = 'fit'")[0]["status"] == "failed"


# -- publish ----------


def test_publishing_the_first_run_makes_it_active(fitted: SqliteD1) -> None:
    db = clone(fitted)
    result = run_publish_job(db, now=stamp(10))
    assert result.exit_code == ExitCode.OK and result.summary["result"] == "promoted"
    assert db.rows("SELECT run_id FROM active_run")[0]["run_id"] == "R20260601T011701Z"
    assert run_ids(db, "active") == ["R20260601T011701Z"]
    gate = result.summary["gate"]
    assert isinstance(gate, dict) and gate["passed"] is True
    # invariant 1: the pointer's run is active and has an ok model
    assert (
        db.scalar(
            "SELECT COUNT(*) FROM active_run a JOIN model_runs r ON r.run_id = a.run_id "
            "JOIN model_params p ON p.run_id = r.run_id "
            "WHERE r.status = 'active' AND p.status = 'ok'"
        )
        == 3
    )


def test_publishing_twice_is_a_no_op(fitted: SqliteD1) -> None:
    db = clone(fitted)
    run_publish_job(db, now=stamp(10))
    activated = db.scalar("SELECT activated_at FROM active_run")
    again = run_publish_job(db, run_id="R20260601T011701Z", now=stamp(40))
    assert again.exit_code == ExitCode.OK and again.summary["result"] == "already active"
    assert db.scalar("SELECT activated_at FROM active_run") == activated


def test_a_second_run_supersedes_the_first(fitted: SqliteD1) -> None:
    db = clone(fitted)
    run_publish_job(db, now=stamp(10))
    second = fit_again(db, 20)
    result = run_publish_job(db, now=stamp(21))
    assert result.exit_code == ExitCode.OK and result.summary["replaced"] == "R20260601T011701Z"
    assert db.rows("SELECT run_id FROM active_run")[0]["run_id"] == second
    assert run_ids(db, "superseded") == ["R20260601T011701Z"]
    assert run_ids(db, "active") == [second]


def test_a_corrupted_run_is_rejected_and_the_old_run_stays_active(fitted: SqliteD1) -> None:
    db = clone(fitted)
    run_publish_job(db, now=stamp(10))
    bad = fit_again(db, 20)
    row = db.rows(
        "SELECT payload_json FROM model_params WHERE run_id = ? AND model = 'dc'", (bad,)
    )[0]
    db.conn.execute(
        "UPDATE model_params SET payload_json = ? WHERE run_id = ? AND model = 'dc'",
        (row["payload_json"].replace('"mu":', '"mu": ', 1) + " ", bad),
    )
    result = run_publish_job(db, now=stamp(21))
    assert result.exit_code == ExitCode.FIT
    assert "rejected" in str(result.summary["result"])
    gate = result.summary["gate"]
    assert isinstance(gate, dict) and any("hash" in r for r in gate["reasons"])
    assert db.rows("SELECT run_id FROM active_run")[0]["run_id"] == "R20260601T011701Z"
    assert run_ids(db, "rejected") == [bad]
    assert run_ids(db, "active") == ["R20260601T011701Z"]
    assert db.scalar("SELECT COUNT(*) FROM events WHERE kind = 'run_rejected'") == 1
    stored = json.loads(
        db.rows("SELECT diagnostics_json FROM model_runs WHERE run_id = ?", (bad,))[0][
            "diagnostics_json"
        ]
    )
    assert stored["gate"]["passed"] is False


def test_a_run_with_jumped_parameters_is_rejected(fitted: SqliteD1) -> None:
    db = clone(fitted)
    run_publish_job(db, now=stamp(10))
    jumped = fit_again(db, 20)
    row = db.rows(
        "SELECT payload_json FROM model_params WHERE run_id = ? AND model = 'dc'", (jumped,)
    )[0]
    payload = json.loads(row["payload_json"])
    payload["teams"]["5"][0] += 2.0  # one team's attack jumps by 2.0 -- with a VALID hash
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    db.conn.execute(
        "UPDATE model_params SET payload_json = ?, payload_sha256 = ? "
        "WHERE run_id = ? AND model = 'dc'",
        (text, payload_sha256(text), jumped),
    )
    result = run_publish_job(db, now=stamp(21))
    assert result.exit_code == ExitCode.FIT
    gate = result.summary["gate"]
    assert isinstance(gate, dict)
    assert any("moved more than" in r and "team 5" in r for r in gate["reasons"])
    assert db.rows("SELECT run_id FROM active_run")[0]["run_id"] == "R20260601T011701Z"
    assert run_ids(db, "rejected") == [jumped]


def test_missing_team_form_rows_reject_the_run(fitted: SqliteD1) -> None:
    db = clone(fitted)
    db.conn.execute("DELETE FROM team_form WHERE team_id > 10")
    result = run_publish_job(db, now=stamp(10))
    assert result.exit_code == ExitCode.FIT
    assert db.scalar("SELECT COUNT(*) FROM active_run") == 0
    assert run_ids(db, "rejected") == ["R20260601T011701Z"]


def test_publish_with_nothing_to_publish_or_a_wrong_id_is_a_data_error(fitted: SqliteD1) -> None:
    db = clone(fitted)
    assert run_publish_job(db, run_id="Rnope", now=stamp(10)).exit_code == ExitCode.DATA
    run_publish_job(db, now=stamp(11))
    assert run_publish_job(db, now=stamp(12)).exit_code == ExitCode.DATA  # no building run left


def test_a_rejected_run_cannot_be_published_later(fitted: SqliteD1) -> None:
    db = clone(fitted)
    db.conn.execute("DELETE FROM team_form")
    run_publish_job(db, now=stamp(10))  # rejected
    again = run_publish_job(db, run_id="R20260601T011701Z", now=stamp(11))
    assert again.exit_code == ExitCode.FIT
    assert db.scalar("SELECT COUNT(*) FROM active_run") == 0


def test_promotion_is_atomic_when_the_database_fails_midway(fitted: SqliteD1) -> None:
    db = clone(fitted)
    run_publish_job(db, now=stamp(10))
    second = fit_again(db, 20)
    db.fail_when = lambda statements: any("INSERT INTO active_run" in s.sql for s in statements)
    result = run_publish_job(db, now=stamp(21))
    assert result.exit_code == ExitCode.UNEXPECTED
    # nothing moved: the old run is still the only active run and the new one is still building
    assert db.rows("SELECT run_id FROM active_run")[0]["run_id"] == "R20260601T011701Z"
    assert run_ids(db, "active") == ["R20260601T011701Z"]
    assert run_ids(db, "building") == [second]


def test_the_repo_refuses_to_promote_a_run_that_is_not_promotable(fitted: SqliteD1) -> None:
    db = clone(fitted)
    run_publish_job(db, now=stamp(10))
    db.conn.execute(
        "INSERT INTO model_runs (run_id, status, started_at) VALUES ('Rbad', 'rejected', 't')"
    )
    repo = ModelRegistryRepo(db)
    assert repo.promote("Rbad", "t") is False
    assert repo.promote("Rmissing", "t") is False
    assert db.rows("SELECT run_id FROM active_run")[0]["run_id"] == "R20260601T011701Z"
    assert run_ids(db, "active") == ["R20260601T011701Z"]  # the active run was not superseded


# -- rollback and pruning ----------


def test_rollback_points_the_active_run_back_at_a_superseded_run(fitted: SqliteD1) -> None:
    db = clone(fitted)
    run_publish_job(db, now=stamp(10))
    second = fit_again(db, 20)
    run_publish_job(db, now=stamp(21))
    result = run_publish_job(db, rollback="R20260601T011701Z", now=stamp(30))
    assert result.exit_code == ExitCode.OK and result.summary["result"] == "rolled back"
    assert db.rows("SELECT run_id FROM active_run")[0]["run_id"] == "R20260601T011701Z"
    assert run_ids(db, "active") == ["R20260601T011701Z"]
    assert run_ids(db, "superseded") == [second]
    # and forward again
    assert run_publish_job(db, rollback=second, now=stamp(31)).exit_code == ExitCode.OK
    assert run_ids(db, "active") == [second]


def test_rollback_rules(fitted: SqliteD1) -> None:
    db = clone(fitted)
    run_publish_job(db, now=stamp(10))
    assert run_publish_job(db, rollback="Rnope", now=stamp(11)).exit_code == ExitCode.DATA
    again = run_publish_job(db, rollback="R20260601T011701Z", now=stamp(12))
    assert again.exit_code == ExitCode.OK and again.summary["result"] == "already active"
    db.conn.execute(
        "INSERT INTO model_runs (run_id, status, started_at) VALUES ('Rr', 'rejected', 't')"
    )
    refused = run_publish_job(db, rollback="Rr", now=stamp(13))
    assert refused.exit_code == ExitCode.DATA and "superseded" in str(refused.summary["error"])


def test_old_runs_are_pruned_but_never_the_active_run(fitted: SqliteD1) -> None:
    db = clone(fitted)
    run_publish_job(db, now=stamp(10), keep=3)
    for second in (20, 30, 40, 50):
        fit_again(db, second)
        assert run_publish_job(db, now=stamp(second + 1), keep=3).exit_code == ExitCode.OK
    ids = run_ids(db)
    assert len(ids) == 3 and ids[-1] == db.rows("SELECT run_id FROM active_run")[0]["run_id"]
    assert "R20260601T011701Z" not in ids
    # children of pruned runs are gone too
    assert (
        db.scalar(
            "SELECT COUNT(*) FROM model_params WHERE run_id NOT IN (SELECT run_id FROM model_runs)"
        )
        == 0
    )
    assert (
        db.scalar(
            "SELECT COUNT(*) FROM team_form WHERE run_id NOT IN (SELECT run_id FROM model_runs)"
        )
        == 0
    )


def test_a_transient_database_error_when_reading_is_reported(fitted: SqliteD1) -> None:
    db = clone(fitted)
    db.fail_next = D1TransientError("down")
    result = run_publish_job(db, now=stamp(10))
    assert result.exit_code == ExitCode.UNEXPECTED


def test_active_teams_without_matches_get_form_rows_and_the_run_still_publishes(
    world: SyntheticWorld,
) -> None:
    """Like the 11 Scottish clubs: active, no matches. They need a row (n_training 0) so the
    Worker omits them as INSUFFICIENT_HISTORY and the 95% coverage check counts them."""
    db = SqliteD1()
    seed_world(db, world)
    for number in range(1, 4):
        db.conn.execute(
            "INSERT INTO teams (canonical_name, home_comp, is_ucl_only, active) "
            "VALUES (?, NULL, 1, 1)",
            (f"No Matches {number}",),
        )
    result = run_fit_job(db, models=["dc"], now=stamp(8))
    assert result.exit_code == ExitCode.OK
    empty = db.rows("SELECT * FROM team_form WHERE n_training = 0")
    assert len(empty) == 3 and all(r["season_gf"] is None and r["l10_n"] == 0 for r in empty)
    assert db.scalar("SELECT COUNT(*) FROM team_form") == 33
    published = run_publish_job(db, now=stamp(9))
    assert published.exit_code == ExitCode.OK
    gate = published.summary["gate"]
    assert isinstance(gate, dict) and gate["checks"]["team_form_coverage"] == 1.0
