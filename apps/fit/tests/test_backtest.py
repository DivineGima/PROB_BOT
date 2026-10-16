"""Training repository, walk-forward backtest and the backtest job (Stage 3)."""

from __future__ import annotations

import itertools
import json
from collections.abc import Mapping, Sequence
from datetime import date, timedelta

import pytest

from footy.backtest.job import run_backtest_job
from footy.backtest.report import format_report
from footy.backtest.walkforward import BacktestConfig, folds_for, run_backtest
from footy.errors import ExitCode
from footy.models.dixon_coles import fit_dc_outcome
from footy.models.registry import fitters_for, load_model
from footy.models.types import MODEL_DC, FitConfig, FitOutcome, TrainingMatch
from footy.repo import training as training_module
from footy.repo.training import TrainingRepo
from tests.db_seed import seed_world
from tests.helpers import SqliteD1
from tests.synthetic import SyntheticWorld, generate_world


@pytest.fixture(scope="module")
def world() -> SyntheticWorld:
    return generate_world(seed=21, n_leagues=3, teams_per_league=10, seasons=3)


def _db(world: SyntheticWorld) -> SqliteD1:
    db = SqliteD1()
    seed_world(db, world)
    return db


# -- training repository -------------------------------------------------------------------------


def test_training_repo_returns_only_verified_finished_matches(world: SyntheticWorld) -> None:
    db = _db(world)
    db.conn.execute(
        "INSERT INTO matches (comp_code, season, match_date, home_team_id, away_team_id, status, "
        "goals_home, goals_away, result_basis, updated_at) VALUES "
        "('EPL','2025','2026-05-30',1,2,'FINISHED',9,9,'unverified','x'),"
        "('EPL','2025','2026-06-01',1,3,'SCHEDULED',NULL,NULL,NULL,'x'),"
        "('EPL','2025','2026-06-02',1,4,'POSTPONED',NULL,NULL,NULL,'x')"
    )
    found = TrainingRepo(db).finished_matches()
    assert len(found) == len(world.matches)
    assert all(m.goals_home <= 20 and m.goals_away <= 20 for m in found)
    assert found == sorted(found, key=lambda m: (m.match_date, m.home_id, m.away_id))


def test_training_repo_pages_and_respects_date_bounds(
    world: SyntheticWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = _db(world)
    monkeypatch.setattr(training_module, "PAGE_SIZE", 50)
    repo = TrainingRepo(db)
    assert len(repo.finished_matches()) == len(world.matches)
    low, high = date(2025, 10, 1), date(2025, 12, 31)
    window = repo.finished_matches(low, high)
    assert window
    assert all(low <= m.match_date <= high for m in window)
    assert len(window) == sum(1 for m in world.matches if low <= m.match_date <= high)


def test_league_groups_map_missing_home_competition_to_ucl_only(world: SyntheticWorld) -> None:
    db = _db(world)
    db.conn.execute(
        "INSERT INTO teams (team_id, canonical_name, home_comp, is_ucl_only, active) "
        "VALUES (900, 'Only Europe', NULL, 1, 1)"
    )
    groups = TrainingRepo(db).league_groups()
    assert groups[900] == "UCL_ONLY"
    assert groups[1] == world.leagues[1]
    assert 900 in TrainingRepo(db).active_team_ids()


# -- walk-forward --------------------------------------------------------------------------------


def test_folds_cover_the_period_without_gaps() -> None:
    cfg = BacktestConfig(date(2026, 1, 1), date(2026, 1, 31), fold_days=10)
    folds = folds_for(cfg)
    assert folds[0][0] == date(2026, 1, 1)
    assert folds[-1][1] == date(2026, 1, 31)
    assert all(b[0] == a[1] + timedelta(days=1) for a, b in itertools.pairwise(folds))
    with pytest.raises(ValueError):
        folds_for(BacktestConfig(date(2026, 2, 1), date(2026, 1, 1)))
    with pytest.raises(ValueError):
        folds_for(BacktestConfig(date(2026, 1, 1), date(2026, 1, 2), fold_days=0))


def test_walk_forward_never_trains_on_the_future(world: SyntheticWorld) -> None:
    seen: list[tuple[date, date]] = []

    def spy(
        matches: Sequence[TrainingMatch], leagues: Mapping[int, str], as_of: date, config: FitConfig
    ) -> FitOutcome:
        seen.append((as_of, max(m.match_date for m in matches if m.match_date <= as_of)))
        # a fitter that is handed future matches would be a leak: it must only be given the past
        assert all(m.match_date <= as_of for m in matches)
        return fit_dc_outcome(matches, leagues, as_of, config)

    config = BacktestConfig(world.as_of - timedelta(days=89), world.as_of, fold_days=45)
    run_backtest(world.matches, world.leagues, {MODEL_DC: spy}, config)
    assert len(seen) == 2
    assert seen[0][0] == config.test_from - timedelta(days=1)


def test_dixon_coles_beats_the_baseline_on_synthetic_truth(world: SyntheticWorld) -> None:
    config = BacktestConfig(world.as_of - timedelta(days=179), world.as_of, fold_days=45)
    result = run_backtest(world.matches, world.leagues, fitters_for([MODEL_DC]), config)
    summary = result.summary()
    entry = summary["models"][MODEL_DC]  # type: ignore[index]
    assert entry["beats_baseline"] is True
    assert entry["rps_skill_vs_baseline"] > 0
    assert entry["paired_rps_diff_mean"] < 0
    assert result.forecast_matches > 100
    assert summary["label"] == "tuning on history, not validation"
    # the baseline is scored on exactly the matches the model forecast
    assert summary["baseline"]["overall"]["n"] == entry["overall"]["n"]  # type: ignore[index]
    # per-competition numbers exist for every league and the linking competition
    assert set(entry["per_competition"]) >= {"EPL", "LL", "BL"}


def test_a_failing_model_is_recorded_not_hidden(world: SyntheticWorld) -> None:
    def broken(
        matches: Sequence[TrainingMatch], leagues: Mapping[int, str], as_of: date, config: FitConfig
    ) -> FitOutcome:
        return FitOutcome(MODEL_DC, "failed", None, "boom")

    config = BacktestConfig(world.as_of - timedelta(days=89), world.as_of, fold_days=45)
    result = run_backtest(world.matches, world.leagues, {MODEL_DC: broken}, config)
    assert result.fold_failures[MODEL_DC] == ["boom", "boom"]
    assert result.forecast_matches == 0
    assert result.summary()["fold_failures"] == {MODEL_DC: 2}


def test_teams_with_too_little_history_are_skipped_and_counted(world: SyntheticWorld) -> None:
    # Cut the training history so short that almost no team has 10 matches yet.
    early = [
        m for m in world.matches if m.match_date < world.matches[0].match_date + timedelta(days=20)
    ]
    later = [m for m in world.matches if m.match_date >= date(2025, 3, 1)][:60]
    config = BacktestConfig(later[0].match_date, later[-1].match_date, fold_days=30)
    result = run_backtest(
        early + later,
        world.leagues,
        {MODEL_DC: lambda m, lg, a, c: fit_dc_outcome(m, lg, a, FitConfig(min_matches=10))},
        config,
    )
    assert result.skipped_insufficient_history > 0


def test_load_model_round_trips_a_payload(world: SyntheticWorld) -> None:
    outcome = fit_dc_outcome(world.matches, world.leagues, world.as_of)
    assert outcome.payload is not None
    model = load_model(MODEL_DC, outcome.payload)
    assert outcome.fitted is not None
    assert (model.grid(1, 12, "UCL") == outcome.fitted.grid(1, 12, "UCL")).all()
    with pytest.raises(ValueError):
        load_model("nope", {})
    with pytest.raises(ValueError):
        fitters_for(["nope"])


# -- the job -------------------------------------------------------------------------------------


def test_backtest_job_records_the_run_and_the_report(world: SyntheticWorld) -> None:
    db = _db(world)
    reports: list[str] = []
    result = run_backtest_job(
        db, test_days=180, fold_days=45, report_sink=reports.append, git_sha="abc123"
    )
    assert result.exit_code == ExitCode.OK
    assert result.summary["data_cutoff"] == world.as_of.isoformat() or result.summary["data_cutoff"]
    job = db.rows("SELECT kind, status, git_sha, summary_json FROM job_runs")[0]
    assert (job["kind"], job["status"], job["git_sha"]) == ("backtest", "ok", "abc123")
    stored = json.loads(job["summary_json"])
    assert stored["result"]["models"]["dc"]["beats_baseline"] is True
    assert "beats baseline" in reports[0]
    assert "baseline" in reports[0] and "EPL" in reports[0]


def test_backtest_job_sweep_lists_every_combination(world: SyntheticWorld) -> None:
    db = _db(world)
    reports: list[str] = []
    result = run_backtest_job(
        db,
        test_days=90,
        fold_days=45,
        half_lives=[200.0, 400.0],
        shrinks=[2.0],
        report_sink=reports.append,
    )
    assert result.exit_code == ExitCode.OK
    sweep = result.summary["sweep"]
    assert isinstance(sweep, list)
    assert [row["half_life_days"] for row in sweep] == [200.0, 400.0]
    assert all(row["rps_dc"] < 0.3 for row in sweep)
    assert "sweep" in reports[0]


def test_backtest_job_without_data_fails_cleanly() -> None:
    db = SqliteD1()
    result = run_backtest_job(db)
    assert result.exit_code == ExitCode.DATA
    assert "bootstrap" in str(result.summary["error"])
    assert db.rows("SELECT status FROM job_runs")[0]["status"] == "failed"


def test_backtest_job_rejects_nonsense_arguments(world: SyntheticWorld) -> None:
    db = _db(world)
    assert run_backtest_job(db, test_days=0).exit_code == ExitCode.DATA
    assert run_backtest_job(db, fold_days=0).exit_code == ExitCode.DATA
    too_many = run_backtest_job(db, half_lives=[1.0 + i for i in range(5)], shrinks=[1.0, 2.0, 3.0])
    assert too_many.exit_code == ExitCode.DATA
    too_long = run_backtest_job(db, test_days=5000)
    assert too_long.exit_code == ExitCode.DATA
    assert "shorten" in str(too_long.summary["error"])


def test_backtest_job_reports_partial_when_a_fold_fails(
    world: SyntheticWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    from footy.backtest import job as job_module

    def flaky(names: list[str]) -> dict[str, object]:
        calls = {"n": 0}

        def fitter(m: list[TrainingMatch], lg: dict[int, str], a: date, c: FitConfig) -> FitOutcome:
            calls["n"] += 1
            if calls["n"] == 1:
                return FitOutcome(MODEL_DC, "failed", None, "first fold failed")
            return fit_dc_outcome(m, lg, a, c)

        return {MODEL_DC: fitter}

    monkeypatch.setattr(job_module, "fitters_for", flaky)
    result = run_backtest_job(_db(world), test_days=90, fold_days=45)
    assert result.exit_code == ExitCode.FIT


def test_report_formatting_handles_a_summary_without_models() -> None:
    text = format_report(
        {"label": "x", "baseline": {}, "models": {}, "folds": 0, "forecast_matches": 0}
    )
    assert "baseline" in text


def test_three_models_and_the_ensemble_are_compared_with_the_baseline(
    world: SyntheticWorld,
) -> None:
    config = BacktestConfig(world.as_of - timedelta(days=119), world.as_of, fold_days=60)
    result = run_backtest(world.matches, world.leagues, fitters_for(["dc", "pi", "bp"]), config)
    models = result.summary()["models"]
    assert isinstance(models, dict)
    assert set(models) == {"dc", "pi", "bp", "ensemble"}
    rps = {name: entry["overall"]["rps_1x2"] for name, entry in models.items()}
    # RPS is convex in the forecast, so the pooled forecast cannot score worse than the worst
    # member when it is a convex combination of the members
    assert rps["ensemble"] <= max(rps["dc"], rps["pi"], rps["bp"]) + 1e-12
    assert all(entry["overall"]["n"] == models["dc"]["overall"]["n"] for entry in models.values())
    # weights per fold: equal in the first fold (nothing scored yet), a valid pool afterwards
    first, second = result.fold_weights
    assert first == pytest.approx({"dc": 1 / 3, "pi": 1 / 3, "bp": 1 / 3}, abs=1e-5)
    assert sum(second.values()) == pytest.approx(1.0, abs=1e-5)
    assert second != first
    assert models["bp"]["beats_baseline"] is True


def test_the_ensemble_can_be_switched_off(world: SyntheticWorld) -> None:
    config = BacktestConfig(
        world.as_of - timedelta(days=59), world.as_of, fold_days=60, ensemble=False
    )
    result = run_backtest(world.matches, world.leagues, fitters_for(["dc", "pi"]), config)
    assert "ensemble" not in result.summary()["models"]  # type: ignore[operator]
    assert result.fold_weights == []
