"""Backtest regression check (architecture sections 9.3 and 14, ADR-046)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from footy.backtest.job import run_backtest_job
from footy.backtest.regression import compare_with_previous
from footy.errors import ExitCode
from tests.db_seed import seed_world
from tests.helpers import SqliteD1
from tests.synthetic import generate_world


def summary(
    models: list[str],
    rps: dict[str, float],
    *,
    days: int = 365,
    half: float = 300.0,
    shrink: float = 4.0,
) -> dict[str, Any]:
    return {
        "models": models,
        "test_days": days,
        "data_cutoff": "2026-05-31",
        "result": {
            "fit_config": {"half_life_days": half, "shrink_team": shrink},
            "models": {n: {"overall": {"rps_1x2": v, "n": 500}} for n, v in rps.items()},
        },
    }


def test_a_worse_model_beyond_the_tolerance_is_reported() -> None:
    before = summary(["dc", "pi"], {"dc": 0.204, "pi": 0.208, "ensemble": 0.203})
    now = summary(["dc", "pi"], {"dc": 0.2085, "pi": 0.2081, "ensemble": 0.2031})
    check = compare_with_previous(before, now, tolerance=0.003)
    assert check["comparable"] is True and check["regressed"] == ["dc"]
    changes: Any = check["changes"]
    assert changes["dc"]["delta"] == pytest.approx(0.0045)
    assert "ensemble" in changes


def test_a_change_of_exactly_the_tolerance_is_not_a_regression() -> None:
    before = summary(["dc"], {"dc": 0.200})
    within = compare_with_previous(before, summary(["dc"], {"dc": 0.2029}), tolerance=0.003)
    beyond = compare_with_previous(before, summary(["dc"], {"dc": 0.2031}), tolerance=0.003)
    assert within["regressed"] == [] and beyond["regressed"] == ["dc"]


def test_improvements_are_never_regressions() -> None:
    check = compare_with_previous(summary(["dc"], {"dc": 0.21}), summary(["dc"], {"dc": 0.19}))
    changes: Any = check["changes"]
    assert check["regressed"] == [] and changes["dc"]["delta"] < 0


@pytest.mark.parametrize(
    ("previous", "reason"),
    [
        (None, "no previous backtest"),
        (summary(["pi"], {"pi": 0.2}), "different models"),
        (summary(["dc"], {"dc": 0.2}, days=180), "different test_days"),
        (summary(["dc"], {"dc": 0.2}, half=200.0), "different half_life_days"),
        (summary(["dc"], {"dc": 0.2}, shrink=2.0), "different shrink_team"),
        ({"models": ["dc"], "test_days": 365}, "different half_life_days"),
    ],
)
def test_only_a_comparable_previous_backtest_is_used(previous: Any, reason: str) -> None:
    check = compare_with_previous(previous, summary(["dc"], {"dc": 0.5}))
    assert check["comparable"] is False and check["regressed"] == []
    assert reason in str(check["reason"])


def test_a_model_missing_from_either_side_is_skipped() -> None:
    check = compare_with_previous(summary(["dc"], {}), summary(["dc"], {"dc": 0.2}))
    assert check["comparable"] is True and check["changes"] == {}


# -- the job ---------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def db() -> SqliteD1:
    d = SqliteD1()
    seed_world(d, generate_world(seed=41, n_leagues=3, teams_per_league=10, seasons=3))
    return d


def clone(source: SqliteD1) -> SqliteD1:
    copy = SqliteD1()
    source.conn.backup(copy.conn)
    return copy


FAST: dict[str, Any] = {"models": ["dc"], "test_days": 120, "fold_days": 60}


def make_previous_better(d: SqliteD1, by: float) -> None:
    stored = json.loads(d.scalar("SELECT summary_json FROM job_runs WHERE kind = 'backtest'"))
    stored["result"]["models"]["dc"]["overall"]["rps_1x2"] -= by
    d.conn.execute("UPDATE job_runs SET summary_json = ?", (json.dumps(stored),))


def test_the_first_backtest_has_nothing_to_compare_with(db: SqliteD1) -> None:
    result = run_backtest_job(clone(db), **FAST)
    assert result.exit_code == ExitCode.OK
    regression: Any = result.summary["regression"]
    assert regression["reason"] == "no previous backtest"


def test_a_regression_raises_an_alert_and_fails_only_when_asked(db: SqliteD1) -> None:
    d = clone(db)
    assert run_backtest_job(d, **FAST).exit_code == ExitCode.OK
    make_previous_better(d, 0.05)

    informational = run_backtest_job(d, **FAST)
    regression: Any = informational.summary["regression"]
    assert informational.exit_code == ExitCode.OK and regression["regressed"] == ["dc"]
    assert d.scalar("SELECT COUNT(*) FROM events WHERE kind = 'backtest_regression'") == 1

    # the informational run is now the newest comparable one and is not better, so a strict
    # run against it passes; make the previous better again to prove the exit code
    d.conn.execute("DELETE FROM job_runs WHERE job_id < (SELECT MAX(job_id) FROM job_runs)")
    make_previous_better(d, 0.05)
    assert run_backtest_job(d, fail_on_regression=True, **FAST).exit_code == ExitCode.FIT


def test_the_tolerance_decides(db: SqliteD1) -> None:
    d = clone(db)
    run_backtest_job(d, **FAST)
    make_previous_better(d, 0.01)
    lenient = run_backtest_job(d, fail_on_regression=True, regression_tolerance=0.02, **FAST)
    regression: Any = lenient.summary["regression"]
    assert lenient.exit_code == ExitCode.OK and regression["regressed"] == []
