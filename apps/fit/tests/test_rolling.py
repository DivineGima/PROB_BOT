"""Rolling per-model RPS from logged predictions feeds the next fit's ensemble weights
(architecture sections 8.3 and 8.7, ADR-046)."""

from __future__ import annotations

import json

import pytest

from footy.ensemble.history import model_rps_series
from footy.errors import ExitCode
from footy.fitting import run_fit_job
from footy.repo.predictions import PredictionsRepo
from footy.score.types import ScoredRow
from tests.db_seed import TOTAL_PMF, seed_prediction, seed_world
from tests.helpers import SqliteD1
from tests.synthetic import generate_world


def models_json(**forecasts: tuple[float, float, float]) -> str:
    return json.dumps({n: {"p": list(p), "total": TOTAL_PMF} for n, p in forecasts.items()})


def scored(pred_id: int, models: str, goals: tuple[int, int] = (2, 0)) -> ScoredRow:
    return ScoredRow(pred_id, f"2026-10-{pred_id:02d}", models, goals[0], goals[1])


# -- the pure history ----------


def test_each_models_rps_is_recomputed_from_its_own_stored_forecast() -> None:
    row = scored(
        1,
        models_json(dc=(0.5, 0.3, 0.2), pi=(0.2, 0.3, 0.5)),
        goals=(2, 0),
    )
    series = model_rps_series([row], ["dc", "pi"])
    assert series["dc"] == [pytest.approx(0.145)]  # home win: ((0.5-1)^2 + (0.8-1)^2) / 2
    assert series["pi"] == [pytest.approx(((0.2 - 1) ** 2 + (0.5 - 1) ** 2) / 2)]


def test_a_prediction_enters_only_if_every_requested_model_forecast_it() -> None:
    rows = [
        scored(1, models_json(dc=(0.5, 0.3, 0.2), pi=(0.4, 0.3, 0.3), bp=(0.5, 0.2, 0.3))),
        scored(2, models_json(dc=(0.5, 0.3, 0.2), pi=(0.4, 0.3, 0.3))),  # bp skipped this fixture
        scored(3, models_json(dc=(0.6, 0.2, 0.2), pi=(0.4, 0.3, 0.3), bp=(0.5, 0.2, 0.3))),
    ]
    series = model_rps_series(rows, ["dc", "pi", "bp"])
    assert {name: len(v) for name, v in series.items()} == {"dc": 2, "pi": 2, "bp": 2}
    # the dc entries are those of rows 1 and 3, not 1 and 2
    assert series["dc"][1] == pytest.approx(((0.6 - 1) ** 2 + (0.8 - 1) ** 2) / 2)
    # asking for fewer models keeps more rows
    assert {n: len(v) for n, v in model_rps_series(rows, ["dc", "pi"]).items()} == {
        "dc": 3,
        "pi": 3,
    }


def test_malformed_stored_forecasts_are_skipped_not_fatal() -> None:
    rows = [
        scored(1, "not json"),
        scored(2, json.dumps({"dc": {"p": [0.5, 0.5]}})),  # wrong length
        scored(3, json.dumps({"dc": {"p": [0.5, 0.3, "x"]}})),
        scored(4, json.dumps({"dc": {"p": [1.5, 0.3, 0.2]}})),  # not a probability
        scored(5, json.dumps(["dc"])),
        scored(6, models_json(dc=(0.5, 0.3, 0.2))),
    ]
    assert model_rps_series(rows, ["dc"]) == {"dc": [pytest.approx(0.145)]}


def test_no_rows_gives_empty_series() -> None:
    assert model_rps_series([], ["dc", "pi"]) == {"dc": [], "pi": []}


# -- the repository and the fit job ----------


@pytest.fixture(scope="module")
def world_db() -> SqliteD1:
    db = SqliteD1()
    seed_world(db, generate_world(seed=41, n_leagues=3, teams_per_league=10, seasons=3))
    return db


def clone(source: SqliteD1) -> SqliteD1:
    copy = SqliteD1()
    source.conn.backup(copy.conn)
    return copy


def log_scored(db: SqliteD1, n: int, models_for: object, *, start: int = 0) -> None:
    """``n`` scored predictions on distinct fixtures: a home win, with the given model forecasts."""
    for i in range(n):
        day = f"2026-{9 if (start + i) < 28 else 10:02d}-{(start + i) % 28 + 1:02d}"
        seed_prediction(
            db,
            day=day,
            home=1 + (start + i) % 9,
            away=11 + (start + i) // 9 % 9,
            models=models_for,  # type: ignore[arg-type]
            status="scored",
            goals=(2, 0),
            rps=(0.1, 0.1, 0.5),
        )


def fit_weights(db: SqliteD1) -> dict[str, object]:
    result = run_fit_job(db, now=lambda: "2026-06-01T01:17:01Z")
    assert result.exit_code == ExitCode.OK, result.summary
    return json.loads(db.scalar("SELECT ensemble_json FROM model_runs"))  # type: ignore[no-any-return]


def test_recent_scored_returns_the_newest_rows_oldest_first(world_db: SqliteD1) -> None:
    db = clone(world_db)
    log_scored(db, 5, {"dc": {"p": [0.5, 0.3, 0.2], "total": TOTAL_PMF}})
    rows = PredictionsRepo(db).recent_scored(3)
    assert [r.match_date for r in rows] == sorted(r.match_date for r in rows)
    assert len(rows) == 3
    newest = db.scalar("SELECT MAX(match_date) FROM predictions")
    assert rows[-1].match_date == newest


def test_without_scored_predictions_the_weights_do_not_use_the_rolling_method(
    world_db: SqliteD1,
) -> None:
    weights = fit_weights(clone(world_db))
    assert weights["method"] != "rolling_rps" and weights["n_scored"] == 0


def test_the_next_fit_weights_the_models_by_how_they_actually_did(world_db: SqliteD1) -> None:
    db = clone(world_db)
    good, middling, poor = (0.8, 0.1, 0.1), (1 / 3, 1 / 3, 1 / 3), (0.1, 0.1, 0.8)  # a home win
    log_scored(
        db,
        60,
        {
            "dc": {"p": list(good), "total": TOTAL_PMF},
            "pi": {"p": list(middling), "total": TOTAL_PMF},
            "bp": {"p": list(poor), "total": TOTAL_PMF},
        },
    )
    weights = fit_weights(db)
    assert weights["method"] == "rolling_rps" and weights["n_scored"] == 60
    w = weights["weights"]
    assert isinstance(w, dict)
    assert w["dc"] > w["pi"] > w["bp"]
    assert sum(w.values()) == pytest.approx(1.0)


def test_predictions_that_a_fitted_model_skipped_do_not_count(world_db: SqliteD1) -> None:
    db = clone(world_db)
    aligned = {n: {"p": [0.6, 0.2, 0.2], "total": TOTAL_PMF} for n in ("dc", "pi", "bp")}
    partial = {n: {"p": [0.6, 0.2, 0.2], "total": TOTAL_PMF} for n in ("dc", "pi")}
    log_scored(db, 12, aligned)
    log_scored(db, 100, partial, start=12)
    weights = fit_weights(db)
    assert weights["n_scored"] == 12


def test_the_rolling_window_is_the_newest_200_aligned_predictions(world_db: SqliteD1) -> None:
    db = clone(world_db)
    same = {n: {"p": [0.6, 0.2, 0.2], "total": TOTAL_PMF} for n in ("dc", "pi", "bp")}
    log_scored(db, 230, same)
    assert fit_weights(db)["n_scored"] == 200
