"""Nightly forecasts (architecture section 8.11, ADR-042): the pure builder, then the whole path
fit -> forecasts -> gate -> publish -> prune on a SQLite-backed fake D1."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date

import numpy as np
import pytest

from footy.errors import ExitCode
from footy.fitting import run_fit_job
from footy.forecast import Fixture, build_forecast, build_forecasts, fixture_key, renormalise
from footy.form.snapshot import TeamForm
from footy.models.grid import (
    GridError,
    independent_grid,
    markets,
    mix_grids,
)
from footy.publish.job import run_publish_job
from footy.repo.forecasts import ForecastRepo
from footy.scoring import FrequencyBaseline
from footy.scoring.baseline import Result
from tests.db_seed import seed_scheduled, seed_world
from tests.helpers import SqliteD1
from tests.synthetic import SyntheticWorld, generate_world

NOW = "2026-06-01T01:17:00Z"


class StubModel:
    """A fitted model with fixed rates; ``knows`` and ``fail`` choose its behaviour."""

    def __init__(
        self, name: str, rates: tuple[float, float], known: set[int], fail: bool = False
    ) -> None:
        self.name = name
        self._rates = rates
        self._known = known
        self._fail = fail

    def knows(self, team_id: int) -> bool:
        return team_id in self._known

    def grid(self, home_id: int, away_id: int, comp_code: str) -> np.ndarray:
        if self._fail:
            raise GridError("boom")
        return independent_grid(*self._rates)

    def to_payload(self) -> dict[str, object]:
        return {}


def stable_form(team_id: int, **kwargs: object) -> TeamForm:
    base: dict[str, object] = {
        "n_training": 40,
        "n_season": 12,
        "season_gf": 1.5,
        "season_ga": 1.0,
        "l10_n": 10,
        "l10_gf": 1.5,
        "l10_ga": 1.0,
        "latest_match_date": "2026-05-20",
    }
    base.update(kwargs)
    return TeamForm(team_id, **base)  # type: ignore[arg-type]


BASELINE = FrequencyBaseline.from_results(
    [Result("EPL", h, a) for h, a in [(1, 0), (2, 1), (1, 1), (0, 2), (3, 1)] * 10]
)
FIXTURE = Fixture("EPL", date(2026, 6, 2), "2026-06-02T15:00:00Z", 1, 2)
FORMS = {1: stable_form(1), 2: stable_form(2)}


def make(models: dict[str, StubModel], weights: dict[str, float], forms=FORMS):  # type: ignore[no-untyped-def]
    return build_forecast(FIXTURE, forms, models, weights, BASELINE, NOW)


# -- the pure builder ---------------------------------------------------------------------------


def test_the_fixture_key_is_the_section_8_7_key() -> None:
    assert fixture_key(date(2026, 6, 2), "EPL", 1, 2) == "2026-06-02|EPL|1|2"
    assert fixture_key("2026-06-02", "EPL", 1, 2) == "2026-06-02|EPL|1|2"


def test_an_ok_forecast_is_the_linear_pool_and_every_market_comes_from_that_one_grid() -> None:
    models = {
        "dc": StubModel("dc", (1.6, 1.0), {1, 2}),
        "pi": StubModel("pi", (1.3, 1.2), {1, 2}),
    }
    row = make(models, {"dc": 0.75, "pi": 0.25})
    assert row.verdict == "ok" and row.ensemble is not None
    pooled = mix_grids(
        [models["dc"].grid(1, 2, "EPL"), models["pi"].grid(1, 2, "EPL")], [0.75, 0.25]
    )
    expected = markets(pooled)
    assert row.ensemble.p_home == pytest.approx(expected.p_home, abs=1e-12)
    assert row.ensemble.overs == pytest.approx(expected.overs, abs=1e-12)
    total = json.loads(row.total_json or "")
    assert total == pytest.approx(list(expected.total_pmf), abs=1e-12) and len(total) == 13
    e = row.ensemble
    assert e.p_home + e.p_draw + e.p_away == pytest.approx(1.0, abs=1e-12)
    assert list(e.overs) == sorted(e.overs, reverse=True)


def test_the_markets_of_the_pool_equal_the_weighted_sum_of_the_models_markets() -> None:
    models = {"dc": StubModel("dc", (1.8, 0.9), {1, 2}), "bp": StubModel("bp", (1.2, 1.4), {1, 2})}
    row = make(models, {"dc": 0.6, "bp": 0.4})
    per_model = json.loads(row.models_json or "")
    assert set(per_model) == {"bp", "dc"}
    weights = json.loads(row.weights_json or "")
    assert row.ensemble is not None
    home = sum(weights[n] * per_model[n]["p"][0] for n in per_model)
    assert row.ensemble.p_home == pytest.approx(home, abs=1e-12)
    for k in range(13):
        pooled = sum(weights[n] * per_model[n]["total"][k] for n in per_model)
        assert json.loads(row.total_json or "")[k] == pytest.approx(pooled, abs=1e-12)


def test_weights_are_renormalised_over_the_models_that_produced_a_grid() -> None:
    models = {
        "dc": StubModel("dc", (1.5, 1.1), {1, 2}),
        "pi": StubModel("pi", (1.4, 1.2), {1}),  # does not know team 2
        "bp": StubModel("bp", (1.5, 1.0), {1, 2}),
    }
    row = make(models, {"dc": 0.5, "pi": 0.3, "bp": 0.2})
    assert json.loads(row.weights_json or "") == pytest.approx({"bp": 0.2 / 0.7, "dc": 0.5 / 0.7})
    detail = json.loads(row.detail_json)
    assert detail["models_left_out"] == {"pi": "unknown_team"}
    assert "pi" not in json.loads(row.models_json or "")


def test_a_model_that_cannot_build_the_grid_is_left_out_and_named() -> None:
    models = {
        "dc": StubModel("dc", (1.5, 1.1), {1, 2}),
        "bp": StubModel("bp", (1.5, 1.0), {1, 2}, fail=True),
    }
    row = make(models, {"dc": 0.5, "bp": 0.5})
    assert row.verdict == "ok"
    assert json.loads(row.detail_json)["models_left_out"] == {"bp": "grid_failed: GridError"}
    assert json.loads(row.weights_json or "") == {"dc": 1.0}


def test_no_model_for_the_fixture_is_no_model_and_carries_no_numbers() -> None:
    row = make({"dc": StubModel("dc", (1.5, 1.1), {5, 6})}, {"dc": 1.0})
    assert row.verdict == "NO_MODEL"
    assert row.ensemble is None and row.total_json is None and row.models_json is None
    assert json.loads(row.detail_json)["models_left_out"] == {"dc": "unknown_team"}


def test_insufficient_history_and_drift_rows_carry_the_reason_and_no_numbers() -> None:
    models = {"dc": StubModel("dc", (1.5, 1.1), {1, 2})}
    thin = make(models, {"dc": 1.0}, {1: stable_form(1, n_training=4), 2: stable_form(2)})
    assert thin.verdict == "INSUFFICIENT_HISTORY" and thin.ensemble is None
    assert json.loads(thin.detail_json)["drift"]["home"]["reason"] == "few_training_matches"
    drifting = make(models, {"dc": 1.0}, {1: stable_form(1, l10_gf=2.9), 2: stable_form(2)})
    assert drifting.verdict == "DRIFT" and drifting.baseline_json is None
    assert json.loads(drifting.detail_json)["drift"]["home"]["d_gf"] == pytest.approx(1.4)


def test_renormalise_handles_zero_and_unusable_weights() -> None:
    assert renormalise({"a": 0.0, "b": 0.0}, ["a", "b"]) == {"a": 0.5, "b": 0.5}
    assert renormalise({"a": float("nan"), "b": 1.0}, ["a", "b"]) == {"a": 0.0, "b": 1.0}
    assert renormalise({}, ["a"]) == {"a": 1.0}
    assert renormalise({"a": -1.0, "b": 2.0}, ["a", "b"]) == {"a": 0.0, "b": 1.0}


def test_duplicate_fixtures_are_forecast_once() -> None:
    models = {"dc": StubModel("dc", (1.5, 1.1), {1, 2})}
    rows = build_forecasts([FIXTURE, FIXTURE], FORMS, models, {"dc": 1.0}, BASELINE, NOW)
    assert len(rows) == 1


def test_the_row_values_match_the_column_order() -> None:
    from footy.forecast import FORECAST_COLUMNS

    models = {"dc": StubModel("dc", (1.5, 1.1), {1, 2})}
    row = make(models, {"dc": 1.0})
    values = row.values("R1")
    assert len(values) == len(FORECAST_COLUMNS)
    named = dict(zip(FORECAST_COLUMNS, values, strict=True))
    assert named["run_id"] == "R1" and named["fixture_key"] == "2026-06-02|EPL|1|2"
    assert named["p_over_55"] == row.ensemble.overs[5]
    assert json.loads(str(named["baseline_json"]))["p_home"] == pytest.approx(
        BASELINE.forecast("EPL").p_home
    )


# -- the database path -------------------------------------------------------------------------


def stamp(second: int, day: str = "2026-06-01") -> Callable[[], str]:
    return lambda: f"{day}T01:17:{second:02d}Z"


@pytest.fixture(scope="module")
def world() -> SyntheticWorld:
    return generate_world(seed=41, n_leagues=3, teams_per_league=10, seasons=3)


FIXTURES = [
    ("EPL", "2026-06-02", 1, 2),
    ("EPL", "2026-06-02", 3, 4),
    ("EPL", "2026-06-03", 5, 6),
    ("LL", "2026-06-02", 11, 12),
    ("LL", "2026-06-04", 13, 14),
    ("BL", "2026-06-05", 21, 22),
    ("BL", "2026-06-02", 23, 24),
    ("EPL", "2026-06-06", 7, 8),  # outside the 4-day window
    ("EPL", "2026-05-31", 9, 10),  # before today
]


@pytest.fixture(scope="module")
def forecasted(world: SyntheticWorld) -> SqliteD1:
    db = SqliteD1()
    seed_world(db, world)
    seed_scheduled(db, FIXTURES)
    result = run_fit_job(db, now=stamp(1), git_sha="sha")
    assert result.exit_code == ExitCode.OK, result.summary
    return db


def clone(source: SqliteD1) -> SqliteD1:
    copy = SqliteD1()
    source.conn.backup(copy.conn)
    return copy


def only_run(db: SqliteD1) -> str:
    return str(db.scalar("SELECT run_id FROM model_runs"))


def test_fit_stores_one_forecast_per_fixture_in_the_window(forecasted: SqliteD1) -> None:
    run = only_run(forecasted)
    keys = [r["fixture_key"] for r in forecasted.rows("SELECT fixture_key FROM fixture_forecasts")]
    assert sorted(keys) == sorted(
        [
            "2026-06-02|EPL|1|2",
            "2026-06-02|EPL|3|4",
            "2026-06-03|EPL|5|6",
            "2026-06-02|LL|11|12",
            "2026-06-04|LL|13|14",
            "2026-06-05|BL|21|22",
            "2026-06-02|BL|23|24",
        ]
    )
    diagnostics = json.loads(forecasted.scalar("SELECT diagnostics_json FROM model_runs"))
    assert diagnostics["n_forecast_fixtures"] == 7
    assert sum(diagnostics["forecast_verdicts"].values()) == 7
    assert ForecastRepo(forecasted).count(run) == 7


def test_stored_rows_satisfy_the_invariants_and_the_check_constraints(forecasted: SqliteD1) -> None:
    rows = forecasted.rows("SELECT * FROM fixture_forecasts WHERE verdict = 'ok'")
    assert rows, "the synthetic world should produce at least one stable fixture"
    for r in rows:
        assert r["p_home"] + r["p_draw"] + r["p_away"] == pytest.approx(1.0, abs=1e-9)
        overs = [r[f"p_over_{k}"] for k in ("05", "15", "25", "35", "45", "55")]
        assert overs == sorted(overs, reverse=True)
        assert len(json.loads(r["total_json"])) == 13
        assert set(json.loads(r["models_json"])) == {"bp", "dc", "pi"}
        assert sum(json.loads(r["weights_json"]).values()) == pytest.approx(1.0)
        assert json.loads(r["baseline_json"])["p_home"] > 0
    for r in forecasted.rows("SELECT * FROM fixture_forecasts WHERE verdict <> 'ok'"):
        assert (
            r["p_home"] is None and json.loads(r["detail_json"])["drift"]["verdict"] == r["verdict"]
        )


def test_the_database_refuses_an_ok_row_without_numbers_or_with_bad_sums(
    forecasted: SqliteD1,
) -> None:
    db = clone(forecasted)
    run = only_run(db)
    base = (
        "INSERT INTO fixture_forecasts (run_id, fixture_key, comp_code, match_date, "
        "home_team_id, away_team_id, verdict, {cols} detail_json, created_at) "
        "VALUES (?, ?, 'EPL', '2026-06-02', 1, 2, 'ok', {marks} '{{}}', 't')"
    )
    with pytest.raises(Exception, match="CHECK"):
        db.conn.execute(base.format(cols="", marks=""), (run, "k1"))
    cols = (
        "p_home, p_draw, p_away, p_over_05, p_over_15, p_over_25, p_over_35, p_over_45, p_over_55, "
        "total_json, models_json, weights_json, baseline_json, "
    )
    marks = "0.5, 0.5, 0.5, 1, 1, 1, 1, 1, 1, '[]', '{}', '{}', '{}', "  # sums to 1.5
    with pytest.raises(Exception, match="CHECK"):
        db.conn.execute(base.format(cols=cols, marks=marks), (run, "k2"))
    marks = "0.5, 0.3, 0.2, 0.4, 0.6, 0.3, 0.2, 0.1, 0.05, '[]', '{}', '{}', '{}', "  # not monotone
    with pytest.raises(Exception, match="CHECK"):
        db.conn.execute(base.format(cols=cols, marks=marks), (run, "k3"))


def test_the_forecast_set_is_written_once_and_a_rerun_adds_nothing(forecasted: SqliteD1) -> None:
    db = clone(forecasted)
    run = only_run(db)
    from footy.repo.d1_client import MemoryProgress

    repo = ForecastRepo(db)
    before = repo.count(run)
    window = repo.upcoming_fixtures(date(2026, 6, 1), date(2026, 6, 5))
    assert len(window) == 7
    # writing the same rows again changes nothing (INSERT OR IGNORE)
    rows = db.rows("SELECT fixture_key FROM fixture_forecasts")
    assert len(rows) == before
    assert repo.write(run, [], MemoryProgress()) == 0
    assert repo.count(run) == before


def test_a_run_with_all_its_forecasts_publishes(forecasted: SqliteD1) -> None:
    db = clone(forecasted)
    result = run_publish_job(db, now=stamp(9))
    assert result.exit_code == ExitCode.OK, result.summary
    checks = result.summary["gate"]["checks"]  # type: ignore[index]
    assert checks["forecast_rows"] == 7 and checks["forecasts_expected"] == 7


def test_a_run_with_missing_forecast_rows_is_rejected_and_the_old_run_stays_active(
    forecasted: SqliteD1,
) -> None:
    db = clone(forecasted)
    first = only_run(db)
    assert run_publish_job(db, now=stamp(2)).exit_code == ExitCode.OK
    second = str(run_fit_job(db, now=stamp(3)).summary["run_id"])
    db.conn.execute(
        "DELETE FROM fixture_forecasts WHERE run_id = ? AND fixture_key = '2026-06-02|EPL|1|2'",
        (second,),
    )
    result = run_publish_job(db, now=stamp(4))
    assert result.exit_code == ExitCode.FIT
    assert any("6 of 7" in r for r in result.summary["gate"]["reasons"])  # type: ignore[index]
    assert db.scalar("SELECT run_id FROM active_run") == first
    assert db.scalar("SELECT status FROM model_runs WHERE run_id = ?", (second,)) == "rejected"


def test_a_run_that_did_not_record_its_forecast_count_is_rejected(forecasted: SqliteD1) -> None:
    db = clone(forecasted)
    run = only_run(db)
    diagnostics = json.loads(db.scalar("SELECT diagnostics_json FROM model_runs"))
    del diagnostics["n_forecast_fixtures"]
    db.conn.execute(
        "UPDATE model_runs SET diagnostics_json = ? WHERE run_id = ?",
        (json.dumps(diagnostics), run),
    )
    result = run_publish_job(db, now=stamp(5))
    assert result.exit_code == ExitCode.FIT
    assert any("n_forecast_fixtures" in r for r in result.summary["gate"]["reasons"])  # type: ignore[index]


def test_a_window_with_no_fixtures_records_zero_and_publishes() -> None:
    world = generate_world(seed=43, n_leagues=2, teams_per_league=8, seasons=2)
    db = SqliteD1()
    seed_world(db, world)
    result = run_fit_job(db, now=stamp(1))
    assert result.exit_code == ExitCode.OK
    assert result.summary["forecasts"] == 0
    assert (
        json.loads(db.scalar("SELECT diagnostics_json FROM model_runs"))["n_forecast_fixtures"] == 0
    )
    assert run_publish_job(db, now=stamp(2)).exit_code == ExitCode.OK


def test_teams_with_no_matches_get_insufficient_history_forecasts(world: SyntheticWorld) -> None:
    db = SqliteD1()
    seed_world(db, world)
    db.conn.execute(
        "INSERT INTO teams (team_id, canonical_name, home_comp, is_ucl_only, active) "
        "VALUES (900, 'Newcomers FC', 'EPL', 0, 1)"
    )
    seed_scheduled(db, [("EPL", "2026-06-02", 900, 1)])
    assert run_fit_job(db, now=stamp(1)).exit_code == ExitCode.OK
    row = db.rows("SELECT verdict, detail_json FROM fixture_forecasts")[0]
    assert row["verdict"] == "INSUFFICIENT_HISTORY"
    assert json.loads(row["detail_json"])["drift"]["home"]["reason"] == "few_training_matches"


def test_forecasts_are_pruned_to_the_newest_runs_but_never_the_active_one(
    forecasted: SqliteD1,
) -> None:
    db = clone(forecasted)
    active = only_run(db)
    assert run_publish_job(db, now=stamp(2)).exit_code == ExitCode.OK
    for second in range(3, 9):  # six more runs, never published
        assert run_fit_job(db, now=stamp(second)).exit_code == ExitCode.OK
    assert (
        db.scalar("SELECT COUNT(DISTINCT run_id) FROM fixture_forecasts") == 7
    )  # active + six builds
    removed = ForecastRepo(db).prune(keep_runs=3)
    remaining = {r["run_id"] for r in db.rows("SELECT DISTINCT run_id FROM fixture_forecasts")}
    assert active in remaining, "the active run's forecasts must survive"
    assert len(remaining) == 4  # newest three + the (older) active run
    assert removed == 3 * 7


def test_publish_prunes_old_forecasts_and_old_runs_take_theirs_with_them(
    forecasted: SqliteD1,
) -> None:
    db = clone(forecasted)
    for second in range(2, 6):
        assert run_fit_job(db, now=stamp(second)).exit_code == ExitCode.OK
    latest = str(db.scalar("SELECT run_id FROM model_runs ORDER BY run_id DESC LIMIT 1"))
    result = run_publish_job(db, run_id=latest, now=stamp(9), keep=2, forecast_keep=2)
    assert result.exit_code == ExitCode.OK, result.summary
    assert result.summary["pruned_runs"] == 3
    # no forecast row references a run that no longer exists (foreign keys are on)
    assert (
        db.scalar(
            "SELECT COUNT(*) FROM fixture_forecasts WHERE run_id NOT IN "
            "(SELECT run_id FROM model_runs)"
        )
        == 0
    )
    assert db.scalar("SELECT COUNT(DISTINCT run_id) FROM fixture_forecasts") == 2


def test_rollback_moves_to_a_run_that_still_has_its_forecasts(forecasted: SqliteD1) -> None:
    db = clone(forecasted)
    first = only_run(db)
    assert run_publish_job(db, now=stamp(2)).exit_code == ExitCode.OK
    second = str(run_fit_job(db, now=stamp(3)).summary["run_id"])
    assert run_publish_job(db, now=stamp(4)).exit_code == ExitCode.OK
    result = run_publish_job(db, rollback=first, now=stamp(5))
    assert result.exit_code == ExitCode.OK
    assert db.scalar("SELECT run_id FROM active_run") == first
    assert result.summary["forecast_rows"] == 7 and "warning" not in result.summary
    assert second  # promoted earlier, now superseded


def test_a_rollback_to_a_run_without_forecasts_succeeds_with_a_warning(
    forecasted: SqliteD1,
) -> None:
    db = clone(forecasted)
    first = only_run(db)
    assert run_publish_job(db, now=stamp(2)).exit_code == ExitCode.OK
    assert run_fit_job(db, now=stamp(3)).exit_code == ExitCode.OK
    assert run_publish_job(db, now=stamp(4)).exit_code == ExitCode.OK
    db.conn.execute("DELETE FROM fixture_forecasts WHERE run_id = ?", (first,))
    result = run_publish_job(db, rollback=first, now=stamp(5))
    assert result.exit_code == ExitCode.OK
    assert result.summary["forecast_rows"] == 0 and "no stored forecasts" in str(
        result.summary["warning"]
    )
