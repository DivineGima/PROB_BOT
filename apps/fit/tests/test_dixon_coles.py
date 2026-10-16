"""Dixon-Coles fit: gradient, parameter recovery, failure paths, payload round trip (Stage 3)."""

from __future__ import annotations

from datetime import timedelta

import numpy as np
import pytest
from scipy.optimize import check_grad

from footy.models.dixon_coles import (
    DcModel,
    fit_dc_outcome,
    fit_dixon_coles,
    objective,
)
from footy.models.structure import Structure, decay_weights, window_matches
from footy.models.types import FitConfig, ModelFitError
from tests.synthetic import generate_world


@pytest.fixture(scope="module")
def world():  # type: ignore[no-untyped-def]
    return generate_world(seed=11, n_leagues=3, teams_per_league=10, seasons=3)


def test_analytic_gradient_matches_finite_differences(world) -> None:  # type: ignore[no-untyped-def]
    cfg = FitConfig()
    s = Structure.build(world.matches, world.leagues, world.as_of, cfg)
    rng = np.random.default_rng(3)
    theta = np.append(s.initial(), -0.05) + rng.normal(0, 0.05, s.n_base + 1)

    def f(t: np.ndarray) -> float:
        return objective(t, s)[0]

    def g(t: np.ndarray) -> np.ndarray:
        return objective(t, s)[1]

    err = check_grad(f, g, theta, epsilon=1e-6)
    assert err < 1e-3 * max(1.0, float(np.linalg.norm(g(theta))))


def test_decay_weights_halve_at_the_half_life(world) -> None:  # type: ignore[no-untyped-def]
    w = decay_weights([world.as_of, world.as_of - timedelta(days=300)], world.as_of, 300.0)
    assert w[0] == pytest.approx(1.0)
    assert w[1] == pytest.approx(0.5)


def test_window_excludes_old_and_future_matches(world) -> None:  # type: ignore[no-untyped-def]
    kept = window_matches(world.matches, world.as_of, 365)
    assert kept
    assert all(0 <= (world.as_of - m.match_date).days < 365 for m in kept)
    before = world.as_of - timedelta(days=100)
    assert all(m.match_date <= before for m in window_matches(world.matches, before, 5000))


def test_parameter_recovery_on_synthetic_league() -> None:
    # Eight seasons make every team's estimate tight enough to compare with the truth.
    big = generate_world(seed=5, n_leagues=3, teams_per_league=10, seasons=8)
    cfg = FitConfig(window_days=4000, half_life_days=1e6, shrink_team=1.0)
    model, diag = fit_dixon_coles(big.matches, big.leagues, big.as_of, cfg)
    ids = sorted(big.attack)
    fit_att = np.array([model.teams[t][0] for t in ids])
    true_att = np.array([big.attack[t] for t in ids])
    fit_def = np.array([model.teams[t][1] for t in ids])
    true_def = np.array([big.defence[t] for t in ids])
    assert np.corrcoef(fit_att, true_att)[0, 1] > 0.93
    assert np.corrcoef(fit_def, true_def)[0, 1] > 0.93
    assert model.gamma == pytest.approx(big.gamma, abs=0.06)
    assert model.rho == pytest.approx(big.rho, abs=0.06)
    # the fitted scoring rates match the truth for fixtures inside and across leagues
    errors = [
        abs(model.lambdas(h, a)[k] - big.lambdas(h, a)[k])
        for h, a in [(1, 2), (3, 15), (12, 25), (20, 4)]
        for k in (0, 1)
    ]
    assert max(errors) < 0.3
    assert diag["n_teams"] == 30


def test_fitted_model_grid_is_a_distribution(world) -> None:  # type: ignore[no-untyped-def]
    model, _ = fit_dixon_coles(world.matches, world.leagues, world.as_of)
    grid = model.grid(1, 15, "UCL")
    assert grid.sum() == pytest.approx(1.0, abs=1e-12)
    assert (grid >= 0).all()


def test_payload_round_trip_gives_identical_grids(world) -> None:  # type: ignore[no-untyped-def]
    model, _ = fit_dixon_coles(world.matches, world.leagues, world.as_of)
    clone = DcModel.from_payload(model.to_payload())
    assert np.array_equal(model.grid(2, 14, "EPL"), clone.grid(2, 14, "EPL"))


def test_payload_with_wrong_version_is_rejected(world) -> None:  # type: ignore[no-untyped-def]
    model, _ = fit_dixon_coles(world.matches, world.leagues, world.as_of)
    payload = model.to_payload()
    payload["payload_version"] = 99
    with pytest.raises(ValueError):
        DcModel.from_payload(payload)


def test_too_few_matches_marks_the_model_failed(world) -> None:  # type: ignore[no-untyped-def]
    outcome = fit_dc_outcome(world.matches[:20], world.leagues, world.as_of)
    assert outcome.status == "failed"
    assert outcome.payload is None
    assert "minimum" in (outcome.error or "")


def test_non_convergence_marks_the_model_failed(world) -> None:  # type: ignore[no-untyped-def]
    outcome = fit_dc_outcome(world.matches, world.leagues, world.as_of, FitConfig(max_iterations=2))
    assert outcome.status == "failed"
    assert "converge" in (outcome.error or "")


def test_a_strength_beyond_the_bound_fails_the_sanity_check(world) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ModelFitError, match="exceeds the bound"):
        fit_dixon_coles(world.matches, world.leagues, world.as_of, FitConfig(max_abs_strength=0.05))


def test_team_without_league_group_fails_clearly(world) -> None:  # type: ignore[no-untyped-def]
    leagues = dict(world.leagues)
    del leagues[1]
    outcome = fit_dc_outcome(world.matches, leagues, world.as_of)
    assert outcome.status == "failed"
    assert "no league group" in (outcome.error or "")


def test_stronger_shrinkage_pulls_teams_toward_the_league_mean(world) -> None:  # type: ignore[no-untyped-def]
    loose, _ = fit_dixon_coles(
        world.matches, world.leagues, world.as_of, FitConfig(shrink_team=0.5)
    )
    tight, _ = fit_dixon_coles(
        world.matches, world.leagues, world.as_of, FitConfig(shrink_team=50.0)
    )

    def spread(m: DcModel) -> float:
        return float(np.std([v[0] for v in m.teams.values()]))

    assert spread(tight) < spread(loose)
