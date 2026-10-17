"""Tests for the code-review fixes of Stages 3 and 4 (tracker, 2026-10-17). One test group per
finding, each proving the original problem can no longer happen."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

from footy.backtest import job as backtest_job_module
from footy.backtest.job import run_backtest_job
from footy.backtest.walkforward import BacktestConfig, run_backtest
from footy.cli import main
from footy.errors import DataError, ExitCode, FootyError
from footy.fitting import run_fit_job
from footy.jobs import STALE_JOB_MINUTES, run_job
from footy.models.bivariate_poisson import BpModel
from footy.models.dixon_coles import DcModel, fit_dc_outcome
from footy.models.grid import bivariate_poisson_grid
from footy.models.pi_rating import fit_pi_outcome
from footy.models.pooled import read_base
from footy.models.types import FitConfig, FitOutcome, GridModel, LeagueMap, TrainingMatch
from footy.payload import payload_sha256
from footy.publish.job import run_publish_job
from footy.repo.d1_client import D1TransientError
from footy.repo.ops import OpsRepo
from tests.db_seed import seed_world
from tests.helpers import SqliteD1
from tests.synthetic import SyntheticWorld, generate_world

WORKFLOW = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "data.yml"


def stamp(second: int) -> object:
    return lambda: f"2026-06-01T01:17:{second:02d}Z"


@pytest.fixture(scope="module")
def world() -> SyntheticWorld:
    return generate_world(seed=61, n_leagues=3, teams_per_league=10, seasons=3)


@pytest.fixture(scope="module")
def built(world: SyntheticWorld) -> SqliteD1:
    """Results plus one built dc-only run (cheap); tests clone it."""
    db = SqliteD1()
    seed_world(db, world)
    assert run_fit_job(db, models=["dc"], now=stamp(1)).exit_code == ExitCode.OK  # type: ignore[arg-type]
    return db


def clone(source: SqliteD1) -> SqliteD1:
    copy = SqliteD1()
    source.conn.backup(copy.conn)
    return copy


# -- 1. least privilege in the data workflow -------------------------------------------------------


def test_football_data_secrets_are_only_given_to_the_commands_that_use_them() -> None:
    lines = {
        line.strip().split(":", 1)[0]: line
        for line in WORKFLOW.read_text(encoding="utf-8").splitlines()
        if ":" in line
    }
    for name in ("FD_ORG_TOKEN", "SOURCE_ENABLED_FDORG"):
        line = lines[name]
        assert "inputs.command" in line, f"{name} must depend on the chosen command"
        for allowed in ("bootstrap-dry-run", "bootstrap", "ingest"):
            assert f'"{allowed}"' in line
        for forbidden in ("fit", "publish", "backtest", "d1-probe"):
            assert f'"{forbidden}"' not in line, f"{name} must not reach {forbidden}"
    assert "inputs.command != 'bootstrap-dry-run'" in lines["CF_D1_TOKEN"]


# -- 2. the ensemble prior comes only from a matching backtest -------------------------------------


def test_the_reported_backtest_result_is_the_one_with_the_production_settings(
    world: SyntheticWorld,
) -> None:
    db = SqliteD1()
    seed_world(db, world)
    # the first sweep cell (half-life 200) is NOT the production default (300 / 4)
    result = run_backtest_job(
        db, models=["dc"], test_days=60, fold_days=60, half_lives=[200.0, 300.0], shrinks=[4.0]
    )
    assert result.exit_code == ExitCode.OK
    reported = result.summary["result"]
    assert isinstance(reported, dict)
    assert reported["fit_config"]["half_life_days"] == 300.0
    assert result.summary["models"] == ["dc"]
    assert result.summary["test_days"] == 60


def _stored_backtest(db: SqliteD1, half_life: float, shrink: float, n: int = 500) -> None:
    summary = {
        "result": {
            "fit_config": {"half_life_days": half_life, "shrink_team": shrink},
            "models": {
                "dc": {"overall": {"rps_1x2": 0.200, "n": n}},
                "pi": {"overall": {"rps_1x2": 0.230, "n": n}},
            },
        }
    }
    db.conn.execute(
        "INSERT INTO job_runs (kind, started_at, status, summary_json) "
        "VALUES ('backtest', 't', 'ok', ?)",
        (json.dumps(summary),),
    )


def test_fit_ignores_a_backtest_made_with_other_settings(world: SyntheticWorld) -> None:
    mismatched = SqliteD1()
    seed_world(mismatched, world)
    _stored_backtest(mismatched, half_life=200.0, shrink=2.0)
    result = run_fit_job(mismatched, models=["dc", "pi"], now=stamp(2))  # type: ignore[arg-type]
    ensemble = result.summary["ensemble"]
    assert isinstance(ensemble, dict) and ensemble["method"] == "equal"

    matching = SqliteD1()
    seed_world(matching, world)
    _stored_backtest(matching, half_life=300.0, shrink=4.0)
    result = run_fit_job(matching, models=["dc", "pi"], now=stamp(3))  # type: ignore[arg-type]
    ensemble = result.summary["ensemble"]
    assert isinstance(ensemble, dict) and ensemble["method"] == "backtest_prior"
    assert ensemble["weights"]["dc"] > ensemble["weights"]["pi"]

    tiny = SqliteD1()
    seed_world(tiny, world)
    _stored_backtest(tiny, half_life=300.0, shrink=4.0, n=40)  # too few forecasts behind it
    result = run_fit_job(tiny, models=["dc", "pi"], now=stamp(4))  # type: ignore[arg-type]
    assert result.summary["ensemble"]["method"] == "equal"  # type: ignore[index]


# -- 3. the bivariate Poisson covariance is not inflated when served -------------------------------


def test_a_small_fitted_covariance_is_served_unchanged() -> None:
    teams = {1: (0.1, -0.05, "EPL"), 2: (-0.05, 0.1, "EPL")}
    model = BpModel(
        lambda3=0.002,
        mu=0.1,
        gamma=0.2,
        league_att={},
        league_def={},
        teams=teams,
        half_life_days=300.0,
    )
    lam1, lam2 = model.lambdas(1, 2)
    assert np.allclose(model.grid(1, 2, "EPL"), bivariate_poisson_grid(lam1, lam2, 0.002), atol=0)
    # it is genuinely different from the old floor of 0.01
    assert not np.allclose(
        model.grid(1, 2, "EPL"), bivariate_poisson_grid(lam1, lam2, 0.01), atol=1e-6
    )


def test_the_golden_vector_for_almost_no_covariance_really_is_unclipped() -> None:
    from footy.models import golden

    vectors = json.loads(golden.path_for("bp").read_text(encoding="utf-8"))["vectors"]
    almost_none = next(v for v in vectors if v["inputs"]["lambda3"] == 0.0005)
    assert almost_none["effective_inputs"]["lambda3"] == 0.0005


# -- 4. the gate cannot be skipped by omission, and never compares with a corrupt active run -------


def test_a_run_without_n_teams_training_is_rejected(built: SqliteD1) -> None:
    db = clone(built)
    db.conn.execute("UPDATE model_runs SET diagnostics_json = '{}'")
    result = run_publish_job(db, now=stamp(10))  # type: ignore[arg-type]
    assert result.exit_code == ExitCode.FIT
    gate = result.summary["gate"]
    assert isinstance(gate, dict)
    assert any("n_teams_training" in r for r in gate["reasons"])
    assert db.scalar("SELECT COUNT(*) FROM active_run") == 0


def _second_dc_run(db: SqliteD1, second: int) -> str:
    result = run_fit_job(db, models=["dc"], now=stamp(second))  # type: ignore[arg-type]
    assert result.exit_code == ExitCode.OK, result.summary
    return str(result.summary["run_id"])


def test_a_corrupt_active_payload_is_skipped_by_the_stability_guard_not_trusted(
    built: SqliteD1,
) -> None:
    db = clone(built)
    assert run_publish_job(db, now=stamp(10)).exit_code == ExitCode.OK  # type: ignore[arg-type]
    db.conn.execute(
        "UPDATE model_params SET payload_json = payload_json || ' ' WHERE run_id = ?",
        ("R20260601T011701Z",),
    )
    new = _second_dc_run(db, 20)
    result = run_publish_job(db, now=stamp(21))  # type: ignore[arg-type]
    assert result.exit_code == ExitCode.OK, result.summary
    gate = result.summary["gate"]
    assert isinstance(gate, dict)
    skipped = gate["checks"]["stability"]["dc"]["skipped"]
    assert "does not verify" in skipped
    assert db.rows("SELECT run_id FROM active_run")[0]["run_id"] == new


# -- 5. the ensemble history describes the same matches for every model ---------------------------


class _Blind:
    """Wraps a fitted model that does not know some teams, so it skips their matches."""

    name = "bp"

    def __init__(self, inner: GridModel, unknown: set[int]) -> None:
        self._inner, self._unknown = inner, unknown

    def knows(self, team_id: int) -> bool:
        return team_id not in self._unknown and self._inner.knows(team_id)

    def grid(self, home_id: int, away_id: int, comp_code: str):  # type: ignore[no-untyped-def]
        return self._inner.grid(home_id, away_id, comp_code)

    def to_payload(self) -> dict[str, object]:
        return self._inner.to_payload()


def test_rps_history_only_holds_matches_every_model_forecast(world: SyntheticWorld) -> None:
    def blind_fitter(
        matches: Sequence[TrainingMatch], leagues: LeagueMap, as_of: date, config: FitConfig
    ) -> FitOutcome:
        out = fit_dc_outcome(matches, leagues, as_of, config)
        assert out.fitted is not None
        return FitOutcome(
            "bp", "ok", out.payload, None, out.diagnostics, _Blind(out.fitted, {1, 2, 3})
        )

    config = BacktestConfig(world.as_of - timedelta(days=89), world.as_of, fold_days=45)
    result = run_backtest(
        world.matches, world.leagues, {"dc": fit_dc_outcome, "bp": blind_fitter}, config
    )
    dc_forecasts = result.models["dc"].overall()
    assert dc_forecasts is not None
    history = result.rps_history
    assert len(history["dc"]) == len(history["bp"]) > 0  # aligned
    assert len(history["dc"]) < dc_forecasts.n  # dc forecast matches that bp skipped
    assert result.skipped_unknown_team["bp"] > 0


# -- 6. (data_cutoff_utc with --as-of is covered in test_fit_publish.py) -------------------------


# -- 7. abandoned jobs, shared job wrapper and the pi memo --------------------------------------


def test_stale_running_jobs_are_closed_and_fresh_ones_are_not() -> None:
    db = SqliteD1()
    ops = OpsRepo(db)
    db.conn.execute(
        "INSERT INTO job_runs (kind, started_at, status) VALUES "
        "('fit', '2026-06-01T00:00:00Z', 'running'),"
        "('fit', '2026-06-01T01:00:00Z', 'running'),"
        "('fit', '2026-06-01T00:00:00Z', 'ok')"
    )
    closed = ops.fail_stale_jobs("2026-06-01T01:30:00Z", 60)
    assert closed == 1
    rows = db.rows("SELECT started_at, status, error FROM job_runs ORDER BY job_id")
    assert [r["status"] for r in rows] == ["failed", "running", "ok"]
    assert "never recorded its end" in rows[0]["error"]
    assert ops.fail_stale_jobs("2026-06-01T01:30:00Z", 60) == 0  # idempotent


def test_run_job_sweeps_abandoned_rows_before_starting() -> None:
    db = SqliteD1()
    db.conn.execute(
        "INSERT INTO job_runs (kind, started_at, status) "
        "VALUES ('backtest', '2026-06-01T00:00:00Z', 'running')"
    )
    result = run_job(
        OpsRepo(db),
        "fit",
        now=lambda: "2026-06-01T03:00:00Z",
        git_sha=None,
        summary={"mode": "fit"},
        body=lambda: ExitCode.OK,
    )
    assert result.exit_code == ExitCode.OK
    statuses = {r["kind"]: r["status"] for r in db.rows("SELECT kind, status FROM job_runs")}
    assert statuses == {"backtest": "failed", "fit": "ok"}
    assert STALE_JOB_MINUTES >= 45  # longer than the workflow timeout


def test_run_job_turns_expected_failures_into_results() -> None:
    now = lambda: "2026-06-01T03:00:00Z"  # noqa: E731

    def failing() -> ExitCode:
        raise DataError("bad data")

    db = SqliteD1()
    result = run_job(OpsRepo(db), "fit", now=now, git_sha="g", summary={}, body=failing)
    assert result.exit_code == ExitCode.DATA and result.summary["error"] == "bad data"
    assert db.rows("SELECT status, error FROM job_runs")[0] == {
        "status": "failed",
        "error": "bad data",
    }

    def lost_database() -> ExitCode:
        raise D1TransientError("down")

    result = run_job(
        OpsRepo(SqliteD1()), "fit", now=now, git_sha=None, summary={}, body=lost_database
    )
    assert result.exit_code == ExitCode.UNEXPECTED

    def unexpected() -> ExitCode:
        raise RuntimeError("a genuine bug must not be swallowed")

    with pytest.raises(RuntimeError):
        run_job(OpsRepo(SqliteD1()), "fit", now=now, git_sha=None, summary={}, body=unexpected)

    broken = SqliteD1()
    broken.fail_next = D1TransientError("down at the start")
    start = run_job(
        OpsRepo(broken), "fit", now=now, git_sha=None, summary={}, body=lambda: ExitCode.OK
    )
    assert start.exit_code == ExitCode.UNEXPECTED
    assert issubclass(DataError, FootyError)


def test_the_pi_rating_is_not_refitted_for_every_shrinkage_value(
    world: SyntheticWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[date] = []

    def counting(
        matches: Sequence[TrainingMatch], leagues: LeagueMap, as_of: date, config: FitConfig
    ) -> FitOutcome:
        calls.append(as_of)
        return fit_pi_outcome(matches, leagues, as_of, config)

    monkeypatch.setattr(backtest_job_module, "fitters_for", lambda names: {"pi": counting})
    db = SqliteD1()
    seed_world(db, world)
    result = run_backtest_job(
        db, models=["pi"], test_days=90, fold_days=45, half_lives=[300.0], shrinks=[2.0, 4.0, 8.0]
    )
    assert result.exit_code == ExitCode.OK
    folds = result.summary["result"]["folds"]  # type: ignore[index]
    assert len(calls) == folds  # once per fold, not once per fold and shrinkage value


# -- 10. shared model code: strict payload parsing ----------------------------------------------


def _payload() -> dict[str, object]:
    return {
        "payload_version": 1,
        "model": "dc",
        "mu": 0.1,
        "gamma": 0.2,
        "rho": -0.05,
        "half_life_days": 300.0,
        "league_att": {"EPL": 0.0},
        "league_def": {"EPL": 0.0},
        "teams": {"1": [0.1, -0.1, "EPL"]},
    }


def test_payload_parsing_is_strict_and_shared() -> None:
    assert DcModel.from_payload(_payload()).rho == -0.05
    assert read_base(_payload(), "dc", 1)["teams"] == {1: (0.1, -0.1, "EPL")}
    for broken in (
        {k: v for k, v in _payload().items() if k != "mu"},  # missing field
        {**_payload(), "rho": "x"},  # not a number
        {**_payload(), "teams": {"1": [0.1]}},  # a team row that is too short
        {**_payload(), "teams": {"x": [0.1, 0.2, "EPL"]}},  # a team id that is not a number
        {**_payload(), "model": "bp"},  # another model's payload
    ):
        with pytest.raises(ValueError):
            DcModel.from_payload(broken)
    assert (
        payload_sha256("abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


# -- accept-drift: an explicit, logged override of the stability guard only ---------------------


def _jump_one_team(db: SqliteD1, run_id: str) -> None:
    row = db.rows(
        "SELECT payload_json FROM model_params WHERE run_id = ? AND model = 'dc'", (run_id,)
    )[0]
    payload = json.loads(row["payload_json"])
    payload["teams"]["5"][0] += 2.0
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    db.conn.execute(
        "UPDATE model_params SET payload_json = ?, payload_sha256 = ? "
        "WHERE run_id = ? AND model = 'dc'",
        (text, payload_sha256(text), run_id),
    )


def test_accept_drift_lets_one_named_run_through_and_logs_it(built: SqliteD1) -> None:
    db = clone(built)
    run_publish_job(db, now=stamp(10))  # type: ignore[arg-type]
    jumped = _second_dc_run(db, 20)
    _jump_one_team(db, jumped)
    assert run_publish_job(db, now=stamp(21)).exit_code == ExitCode.FIT  # type: ignore[arg-type]

    # rejected runs cannot be forced through: build another jumped run and accept it explicitly
    other = _second_dc_run(db, 30)
    _jump_one_team(db, other)
    result = run_publish_job(db, run_id=other, accept_drift=True, now=stamp(31))  # type: ignore[arg-type]
    assert result.exit_code == ExitCode.OK and result.summary["drift_accepted"] is True
    assert db.rows("SELECT run_id FROM active_run")[0]["run_id"] == other
    gate = result.summary["gate"]
    assert isinstance(gate, dict) and gate["checks"]["stability_accepted"] is True
    event = db.rows("SELECT level, kind, detail_json FROM events WHERE kind = 'drift_accepted'")
    assert len(event) == 1 and json.loads(event[0]["detail_json"])["run_id"] == other


def test_accept_drift_still_applies_the_structural_checks(built: SqliteD1) -> None:
    db = clone(built)
    db.conn.execute("DELETE FROM team_form")
    result = run_publish_job(db, run_id="R20260601T011701Z", accept_drift=True, now=stamp(10))  # type: ignore[arg-type]
    assert result.exit_code == ExitCode.FIT
    assert db.scalar("SELECT COUNT(*) FROM active_run") == 0
    assert db.scalar("SELECT COUNT(*) FROM events WHERE kind = 'drift_accepted'") == 0


def test_accept_drift_needs_an_explicit_run_id_and_no_rollback(built: SqliteD1) -> None:
    db = clone(built)
    assert run_publish_job(db, accept_drift=True, now=stamp(10)).exit_code == ExitCode.DATA  # type: ignore[arg-type]
    both = run_publish_job(db, run_id="R1", rollback="R2", accept_drift=True, now=stamp(11))  # type: ignore[arg-type]
    assert both.exit_code == ExitCode.DATA


def test_the_cli_exposes_accept_drift_only_with_a_run_id(
    built: SqliteD1, capsys: pytest.CaptureFixture[str]
) -> None:
    env = {"CF_ACCOUNT_ID": "a", "D1_DATABASE_ID": "d", "CF_D1_TOKEN": "t"}
    db = clone(built)
    code = main(["publish", "--accept-drift"], env=env, database_factory=lambda _s: db)
    assert code == 2 and "--run-id" in json.loads(capsys.readouterr().out)["error"]
    code = main(
        ["publish", "--run-id", "R20260601T011701Z", "--accept-drift"],
        env=env,
        database_factory=lambda _s: db,
    )
    assert code == 0 and json.loads(capsys.readouterr().out)["drift_accepted"] is True
