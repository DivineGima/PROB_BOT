"""Pi-rating: hand-computed update, mapping to a grid, fit and failure paths (Stage 4)."""

from __future__ import annotations

import math
from datetime import timedelta

import numpy as np
import pytest

from footy.models.pi_rating import (
    PiModel,
    PiParams,
    expected_goal_difference,
    fit_pi_outcome,
    fit_pi_rating,
    predicted_difference,
    update_ratings,
    weighted_error,
)
from footy.models.types import FitConfig
from tests.synthetic import generate_world

P = PiParams()


def test_paper_constants() -> None:
    # Constantinou and Fenton (2013): lambda 0.035, gamma 0.7, b 10, c 3 (docs/verification.md)
    assert (P.learning_rate, P.catch_up_rate, P.base, P.scale) == (0.035, 0.7, 10.0, 3.0)


def test_expected_goal_difference_is_signed_and_zero_at_zero() -> None:
    assert expected_goal_difference(0.0) == 0.0
    assert expected_goal_difference(0.6) == pytest.approx(10 ** (0.6 / 3) - 1)
    assert expected_goal_difference(-0.3) == pytest.approx(-(10 ** (0.3 / 3) - 1))
    assert expected_goal_difference(-1.5) == -expected_goal_difference(1.5)


def test_weighted_error_diminishes_large_errors() -> None:
    assert weighted_error(0.0) == 0.0
    assert weighted_error(9.0) == pytest.approx(3.0)  # 3 * log10(10)
    assert weighted_error(4.0) / 4.0 > weighted_error(8.0) / 8.0


def test_update_matches_a_hand_computed_example_home_win() -> None:
    ratings = {1: [0.6, 0.2], 2: [0.1, -0.3]}
    predicted = update_ratings(ratings, 1, 2, 3, 0, P)
    assert predicted == pytest.approx(0.8438186, abs=1e-7)
    # error |3 - 0.84382| = 2.15618, psi = 3 log10(3.15618) = 1.4974859; the home side beat the
    # prediction so it gains lambda * psi = 0.0524120 at home and gamma times that away
    assert ratings[1][0] == pytest.approx(0.6524120, abs=1e-7)
    assert ratings[1][1] == pytest.approx(0.2366884, abs=1e-7)
    assert ratings[2][1] == pytest.approx(-0.3524120, abs=1e-7)
    assert ratings[2][0] == pytest.approx(0.0633116, abs=1e-7)


def test_update_matches_a_hand_computed_example_underperformance() -> None:
    ratings = {1: [0.6, 0.2], 2: [0.1, -0.3]}
    update_ratings(ratings, 1, 2, 0, 0, P)  # expected a home win by 0.84, got a draw
    assert ratings[1][0] == pytest.approx(0.5720996, abs=1e-7)
    assert ratings[1][1] == pytest.approx(0.1804697, abs=1e-7)
    assert ratings[2][1] == pytest.approx(-0.2720996, abs=1e-7)
    assert ratings[2][0] == pytest.approx(0.1195303, abs=1e-7)


def test_a_new_team_starts_at_zero_and_ratings_stay_zero_sum() -> None:
    ratings: dict[int, list[float]] = {}
    update_ratings(ratings, 7, 8, 2, 1, P)
    assert ratings[7][0] > 0 > ratings[8][1]
    assert ratings[7][0] + ratings[8][1] == pytest.approx(
        0.0, abs=1e-12
    )  # one gains what the other loses


def test_predicted_difference_uses_home_rating_of_home_and_away_rating_of_away() -> None:
    assert predicted_difference(0.6, -0.3, P) == pytest.approx(
        expected_goal_difference(0.6) - expected_goal_difference(-0.3)
    )


def _model() -> PiModel:
    return PiModel(
        ratings={1: (0.6, 0.2), 2: (0.1, -0.3)},
        league_total={"EPL": 2.8},
        pooled_total=2.6,
        diff_scale=0.5,
        params=P,
    )


def test_grid_mapping_follows_the_stated_formula() -> None:
    model = _model()
    d = 0.5 * 0.8438186
    lam1, lam2 = model.rates(1, 2, "EPL")
    assert lam1 == pytest.approx((2.8 + d) / 2, abs=1e-6)
    assert lam2 == pytest.approx((2.8 - d) / 2, abs=1e-6)
    assert model.rates(1, 2, "UNKNOWN")[0] == pytest.approx((2.6 + d) / 2, abs=1e-6)  # pooled total
    grid = model.grid(1, 2, "EPL")
    assert grid.sum() == pytest.approx(1.0, abs=1e-12)


def test_mapped_rate_is_floored_for_a_huge_difference() -> None:
    model = PiModel({1: (3.0, 0.0), 2: (0.0, -3.0)}, {"EPL": 2.0}, 2.0, 2.0, P)
    lam1, lam2 = model.rates(1, 2, "EPL")
    assert lam2 == P.min_rate
    assert lam1 > 2.0


def test_payload_round_trip_and_version_check() -> None:
    model = _model()
    clone = PiModel.from_payload(model.to_payload())
    assert np.array_equal(model.grid(1, 2, "EPL"), clone.grid(1, 2, "EPL"))
    bad = model.to_payload()
    bad["payload_version"] = 9
    with pytest.raises(ValueError):
        PiModel.from_payload(bad)
    malformed = model.to_payload()
    malformed["teams"] = []
    with pytest.raises(ValueError):
        PiModel.from_payload(malformed)


@pytest.fixture(scope="module")
def world():  # type: ignore[no-untyped-def]
    return generate_world(seed=31, n_leagues=3, teams_per_league=10, seasons=3)


def test_fit_orders_teams_like_the_truth(world) -> None:  # type: ignore[no-untyped-def]
    model, diag = fit_pi_rating(world.matches, world.leagues, world.as_of)
    ids = sorted(world.attack)
    fit_strength = np.array([model.ratings[t][0] + model.ratings[t][1] for t in ids])
    true_strength = np.array([world.attack[t] - world.defence[t] for t in ids])
    assert np.corrcoef(fit_strength, true_strength)[0, 1] > 0.8
    assert 0.2 <= diag["diff_scale"] <= 2.0  # type: ignore[operator]
    assert diag["n_teams"] == 30


def test_fit_is_deterministic(world) -> None:  # type: ignore[no-untyped-def]
    a, _ = fit_pi_rating(world.matches, world.leagues, world.as_of)
    b, _ = fit_pi_rating(list(reversed(world.matches)), world.leagues, world.as_of)
    assert a.to_payload() == b.to_payload()  # input order does not matter


def test_matches_after_as_of_are_never_used(world) -> None:  # type: ignore[no-untyped-def]
    early = world.as_of - timedelta(days=200)
    cut, _ = fit_pi_rating(world.matches, world.leagues, early)
    only_past, _ = fit_pi_rating(
        [m for m in world.matches if m.match_date <= early], world.leagues, early
    )
    assert cut.to_payload() == only_past.to_payload()


def test_too_few_matches_is_a_failed_outcome(world) -> None:  # type: ignore[no-untyped-def]
    outcome = fit_pi_outcome(world.matches[:10], world.leagues, world.as_of)
    assert outcome.status == "failed" and "minimum" in (outcome.error or "")


def test_a_rating_beyond_the_bound_fails_the_sanity_check(world) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(Exception, match="exceeds the bound"):
        fit_pi_rating(
            world.matches, world.leagues, world.as_of, params=PiParams(max_abs_rating=0.01)
        )


def test_implausible_goal_rates_fail_the_sanity_check(world) -> None:  # type: ignore[no-untyped-def]
    outcome = fit_pi_outcome(
        world.matches, world.leagues, world.as_of, FitConfig(max_mean_lambda=0.5)
    )
    assert outcome.status == "failed" and "mean goal rate" in (outcome.error or "")


def test_decay_only_changes_totals_and_scale_not_ratings(world) -> None:  # type: ignore[no-untyped-def]
    slow, _ = fit_pi_rating(
        world.matches, world.leagues, world.as_of, FitConfig(half_life_days=5000)
    )
    fast, _ = fit_pi_rating(world.matches, world.leagues, world.as_of, FitConfig(half_life_days=60))
    assert (
        slow.ratings == fast.ratings
    )  # the pass itself is recency-weighted by lambda, not by decay
    assert (
        not math.isclose(slow.diff_scale, fast.diff_scale) or slow.pooled_total != fast.pooled_total
    )
