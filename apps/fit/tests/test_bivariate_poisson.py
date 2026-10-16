"""Bivariate Poisson: pmf, analytic gradient, parameter recovery and failure paths (Stage 4)."""

from __future__ import annotations

import math

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from scipy.optimize import check_grad

from footy.models.bivariate_poisson import (
    BpModel,
    fit_bivariate_poisson,
    fit_bp_outcome,
    log_pmf,
    objective,
)
from footy.models.grid import GRID_SIZE, bivariate_poisson_grid
from footy.models.structure import Structure
from footy.models.types import FitConfig
from tests.synthetic import generate_world


def test_log_pmf_matches_the_grid_builder() -> None:
    l1, l2, l3 = 1.2, 0.9, 0.2
    grid = bivariate_poisson_grid(l1, l2, l3)
    xs, ys = np.meshgrid(
        np.arange(GRID_SIZE, dtype=float), np.arange(GRID_SIZE, dtype=float), indexing="ij"
    )
    n = GRID_SIZE * GRID_SIZE
    raw = np.exp(
        log_pmf(
            xs.ravel(), ys.ravel(), np.full(n, math.log(l1)), np.full(n, math.log(l2)), math.log(l3)
        )
    )
    # the grid is the same pmf cut at 12 goals and renormalised
    assert np.allclose(raw.reshape(GRID_SIZE, GRID_SIZE) / raw.sum(), grid, atol=1e-12)


def test_negative_index_has_zero_probability() -> None:
    x = np.array([-1.0, 0.0, 2.0])
    y = np.array([0.0, -1.0, 1.0])
    out = log_pmf(x, y, np.zeros(3), np.zeros(3), -2.0)
    assert out[0] == -np.inf and out[1] == -np.inf and np.isfinite(out[2])


def test_covariance_term_is_the_probability_of_a_shared_event() -> None:
    # with no covariance the pmf factorises: P(1,1) = Po(1; l1) Po(1; l2)
    l1, l2 = 1.1, 0.8
    out = log_pmf(
        np.array([1.0]), np.array([1.0]), np.array([math.log(l1)]), np.array([math.log(l2)]), -30.0
    )
    assert math.exp(out[0]) == pytest.approx(math.exp(-l1) * l1 * math.exp(-l2) * l2, rel=1e-9)


@pytest.fixture(scope="module")
def world():  # type: ignore[no-untyped-def]
    return generate_world(seed=17, n_leagues=3, teams_per_league=10, seasons=3, lambda3=0.15)


def test_analytic_gradient_matches_finite_differences(world) -> None:  # type: ignore[no-untyped-def]
    s = Structure.build(world.matches, world.leagues, world.as_of, FitConfig())
    rng = np.random.default_rng(5)
    theta = np.append(s.initial(), -2.0) + rng.normal(0, 0.05, s.n_base + 1)

    def f(t: np.ndarray) -> float:
        return objective(t, s)[0]

    def g(t: np.ndarray) -> np.ndarray:
        return objective(t, s)[1]

    err = check_grad(f, g, theta, epsilon=1e-6)
    assert err < 1e-3 * max(1.0, float(np.linalg.norm(g(theta))))


def test_parameter_recovery_on_a_bivariate_poisson_world() -> None:
    big = generate_world(seed=9, n_leagues=3, teams_per_league=10, seasons=8, lambda3=0.15)
    cfg = FitConfig(window_days=4000, half_life_days=1e6, shrink_team=1.0)
    model, diag = fit_bivariate_poisson(big.matches, big.leagues, big.as_of, cfg)
    ids = sorted(big.attack)
    fit_att = np.array([model.teams[t][0] for t in ids])
    true_att = np.array([big.attack[t] for t in ids])
    assert np.corrcoef(fit_att, true_att)[0, 1] > 0.88
    assert model.gamma == pytest.approx(big.gamma, abs=0.06)
    assert model.lambda3 == pytest.approx(0.15, abs=0.06)
    assert diag["n_teams"] == 30


def test_fitted_grid_and_payload_round_trip(world) -> None:  # type: ignore[no-untyped-def]
    model, _ = fit_bivariate_poisson(world.matches, world.leagues, world.as_of)
    grid = model.grid(1, 15, "UCL")
    assert grid.sum() == pytest.approx(1.0, abs=1e-12) and (grid >= 0).all()
    clone = BpModel.from_payload(model.to_payload())
    assert np.array_equal(clone.grid(2, 14, "EPL"), model.grid(2, 14, "EPL"))
    bad = model.to_payload()
    bad["payload_version"] = 3
    with pytest.raises(ValueError):
        BpModel.from_payload(bad)
    broken = model.to_payload()
    broken["teams"] = "nope"
    with pytest.raises(ValueError):
        BpModel.from_payload(broken)


def test_failure_paths_are_failed_outcomes_not_exceptions(world) -> None:  # type: ignore[no-untyped-def]
    assert fit_bp_outcome(world.matches[:15], world.leagues, world.as_of).status == "failed"
    stalled = fit_bp_outcome(world.matches, world.leagues, world.as_of, FitConfig(max_iterations=2))
    assert stalled.status == "failed" and "converge" in (stalled.error or "")
    bounded = fit_bp_outcome(
        world.matches, world.leagues, world.as_of, FitConfig(max_abs_strength=0.05)
    )
    assert bounded.status == "failed" and "exceeds the bound" in (bounded.error or "")


@settings(max_examples=25, deadline=None)
@given(
    l1=st.floats(min_value=0.1, max_value=3.0),
    l2=st.floats(min_value=0.1, max_value=3.0),
    l3=st.floats(min_value=0.0005, max_value=1.0),
)
def test_pmf_is_a_distribution_over_the_infinite_support(l1: float, l2: float, l3: float) -> None:
    """Summed over a wide range the pmf is 1 (the model is a proper distribution)."""
    xs, ys = np.meshgrid(np.arange(30, dtype=float), np.arange(30, dtype=float), indexing="ij")
    total = np.exp(
        log_pmf(
            xs.ravel(),
            ys.ravel(),
            np.full(900, math.log(l1)),
            np.full(900, math.log(l2)),
            math.log(l3),
        )
    ).sum()
    assert total == pytest.approx(1.0, abs=1e-6)
