"""Grid engine and markets: hand-computed examples and property tests (Stage 3, section 9.5)."""

from __future__ import annotations

import math

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from footy.models.grid import (
    GRID_SIZE,
    OVER_LINES,
    TOTAL_CATEGORIES,
    GridError,
    bivariate_poisson_grid,
    dixon_coles_grid,
    independent_grid,
    markets,
    mix_grids,
    poisson_pmf,
)

rates = st.floats(min_value=0.05, max_value=3.5)
rhos = st.floats(min_value=-0.15, max_value=0.05)


def test_poisson_pmf_matches_the_formula() -> None:
    pmf = poisson_pmf(1.5)
    for k in range(GRID_SIZE):
        assert pmf[k] == pytest.approx(math.exp(-1.5) * 1.5**k / math.factorial(k), rel=1e-12)


def test_zero_rate_puts_all_mass_on_zero_goals() -> None:
    pmf = poisson_pmf(0.0)
    assert pmf[0] == 1.0
    assert pmf[1:].sum() == 0.0


def test_independent_grid_cells_are_products_of_the_marginals() -> None:
    grid = independent_grid(1.2, 0.9)
    raw = np.outer(poisson_pmf(1.2), poisson_pmf(0.9))
    assert np.allclose(grid, raw / raw.sum(), rtol=1e-12, atol=0)
    assert grid.sum() == pytest.approx(1.0, abs=1e-12)


def test_dixon_coles_cells_follow_the_tau_formula() -> None:
    lam1, lam2, rho = 1.4, 1.1, -0.1
    raw = np.outer(poisson_pmf(lam1), poisson_pmf(lam2))
    raw[0, 0] *= 1 - lam1 * lam2 * rho
    raw[0, 1] *= 1 + lam1 * rho
    raw[1, 0] *= 1 + lam2 * rho
    raw[1, 1] *= 1 - rho
    assert np.allclose(dixon_coles_grid(lam1, lam2, rho), raw / raw.sum(), rtol=1e-12, atol=0)


def test_dixon_coles_with_zero_rho_is_the_independent_grid() -> None:
    assert np.allclose(dixon_coles_grid(1.3, 1.0, 0.0), independent_grid(1.3, 1.0), atol=1e-15)


def test_negative_rho_adds_mass_to_draws_at_low_scores() -> None:
    base = independent_grid(1.3, 1.0)
    grid = dixon_coles_grid(1.3, 1.0, -0.12)
    assert grid[0, 0] > base[0, 0]
    assert grid[1, 1] < base[1, 1] or grid[1, 1] > 0  # tau(1,1) = 1 - rho > 1 for rho < 0


def test_bivariate_poisson_with_zero_covariance_is_the_independent_grid() -> None:
    assert np.allclose(
        bivariate_poisson_grid(1.3, 1.0, 0.0), independent_grid(1.3, 1.0), atol=1e-15
    )


def test_bivariate_poisson_matches_the_closed_form() -> None:
    """Karlis-Ntzoufras: e^-(l1+l2+l3) l1^i/i! l2^j/j! sum_k C(i,k)C(j,k) k! (l3/(l1 l2))^k."""
    l1, l2, l3 = 1.1, 0.8, 0.15
    raw = np.zeros((GRID_SIZE, GRID_SIZE))
    for i in range(GRID_SIZE):
        for j in range(GRID_SIZE):
            s = sum(
                math.comb(i, k) * math.comb(j, k) * math.factorial(k) * (l3 / (l1 * l2)) ** k
                for k in range(min(i, j) + 1)
            )
            raw[i, j] = (
                math.exp(-(l1 + l2 + l3))
                * l1**i
                / math.factorial(i)
                * l2**j
                / math.factorial(j)
                * s
            )
    assert np.allclose(bivariate_poisson_grid(l1, l2, l3), raw / raw.sum(), rtol=1e-10, atol=0)


def test_positive_covariance_raises_the_draw_probability() -> None:
    low = markets(bivariate_poisson_grid(1.3, 1.1, 0.0)).p_draw
    high = markets(bivariate_poisson_grid(1.3, 1.1, 0.3)).p_draw
    assert high > low


def test_tail_beyond_twelve_goals_is_negligible_for_realistic_rates() -> None:
    # Section 8.1 says the tail is below 1e-6 before renormalisation. Measured: that holds per side
    # up to about 2.3 goals; above it the grid is still renormalised, so it still sums to 1.
    for rate in (0.3, 1.0, 1.8, 2.3):
        assert 1.0 - poisson_pmf(rate).sum() < 1e-6
    assert 1.0 - poisson_pmf(3.0).sum() > 1e-6
    assert independent_grid(3.0, 3.0).sum() == pytest.approx(1.0, abs=1e-12)


def test_markets_of_a_point_mass_are_exact() -> None:
    grid = np.zeros((GRID_SIZE, GRID_SIZE))
    grid[2, 1] = 1.0  # a 2-1 home win: three goals
    m = markets(grid)
    assert (m.p_home, m.p_draw, m.p_away) == (1.0, 0.0, 0.0)
    assert m.overs == (1.0, 1.0, 1.0, 0.0, 0.0, 0.0)
    assert m.total_pmf[3] == 1.0
    assert sum(m.total_pmf) == 1.0


def test_totals_of_twelve_or_more_share_the_last_category() -> None:
    grid = np.zeros((GRID_SIZE, GRID_SIZE))
    grid[12, 5] = 0.5  # 17 goals
    grid[7, 5] = 0.5  # exactly 12
    m = markets(grid)
    assert m.total_pmf[TOTAL_CATEGORIES - 1] == 1.0
    assert m.overs[-1] == 1.0


def test_over_lines_are_the_six_half_goal_lines() -> None:
    assert OVER_LINES == (0.5, 1.5, 2.5, 3.5, 4.5, 5.5)
    assert len(markets(independent_grid(1.3, 1.1)).overs) == 6


def test_mix_is_the_weighted_sum_and_keeps_unit_mass() -> None:
    g1, g2 = independent_grid(1.0, 1.0), independent_grid(2.0, 0.7)
    mixed = mix_grids([g1, g2], [0.25, 0.75])
    assert np.allclose(mixed, 0.25 * g1 + 0.75 * g2, atol=1e-15)
    assert mixed.sum() == pytest.approx(1.0, abs=1e-12)


@pytest.mark.parametrize("weights", [[0.5, 0.6], [1.5, -0.5], [float("nan"), 1.0]])
def test_mix_rejects_bad_weights(weights: list[float]) -> None:
    g = independent_grid(1.0, 1.0)
    with pytest.raises(GridError):
        mix_grids([g, g], weights)


def test_mix_rejects_mismatched_lengths_and_empty_input() -> None:
    g = independent_grid(1.0, 1.0)
    with pytest.raises(GridError):
        mix_grids([g], [0.5, 0.5])
    with pytest.raises(GridError):
        mix_grids([], [])


@pytest.mark.parametrize("bad", [-0.1, float("nan"), float("inf"), 7.0])
def test_invalid_rates_are_rejected(bad: float) -> None:
    with pytest.raises(GridError):
        independent_grid(bad, 1.0)


def test_a_rho_that_makes_tau_negative_is_rejected() -> None:
    with pytest.raises(GridError):
        dixon_coles_grid(3.0, 3.0, 0.2)  # 1 - 9 * 0.2 < 0
    with pytest.raises(GridError):
        dixon_coles_grid(1.0, 1.0, float("nan"))


def test_markets_reject_a_wrong_shape() -> None:
    with pytest.raises(GridError):
        markets(np.zeros((3, 3)))


# -- property tests ------------------------------------------------------------------------------


@settings(max_examples=60, deadline=None)
@given(lam1=rates, lam2=rates, rho=rhos, lam3=st.floats(min_value=0.0, max_value=0.8))
def test_every_grid_is_a_proper_distribution_with_consistent_markets(
    lam1: float, lam2: float, rho: float, lam3: float
) -> None:
    for grid in (
        independent_grid(lam1, lam2),
        dixon_coles_grid(lam1, lam2, rho)
        if lam1 * lam2 * abs(rho) < 0.9
        else independent_grid(lam1, lam2),
        bivariate_poisson_grid(lam1, lam2, lam3),
    ):
        assert (grid >= 0).all()
        assert grid.sum() == pytest.approx(1.0, abs=1e-9)
        m = markets(grid)
        assert m.p_home + m.p_draw + m.p_away == pytest.approx(1.0, abs=1e-9)
        assert sum(m.total_pmf) == pytest.approx(1.0, abs=1e-9)
        assert all(m.overs[k] >= m.overs[k + 1] - 1e-15 for k in range(len(m.overs) - 1))
        assert all(0.0 <= p <= 1.0 + 1e-12 for p in m.overs)


@settings(max_examples=40, deadline=None)
@given(lam1=rates, lam2=rates, rho=rhos)
def test_swapping_sides_mirrors_the_grid(lam1: float, lam2: float, rho: float) -> None:
    if lam1 * lam2 * abs(rho) >= 0.9:
        return
    forward = dixon_coles_grid(lam1, lam2, rho)
    swapped = dixon_coles_grid(lam2, lam1, rho)
    assert np.allclose(forward, swapped.T, atol=1e-12)
    a, b = markets(forward), markets(swapped)
    assert a.p_home == pytest.approx(b.p_away, abs=1e-12)
    assert a.overs == pytest.approx(b.overs, abs=1e-12)


def test_extreme_fixture_guard_keeps_the_grid_valid() -> None:
    from footy.models.grid import clip_rate, feasible_rho

    # rates far outside the supported range are clipped, not rejected
    assert clip_rate(80.0) == 6.0
    assert clip_rate(-1.0) == 0.01
    # the same case that once broke a backtest: lambda 4.7 v 3.4 with a positive rho
    rho = feasible_rho(4.7, 3.4, 0.087)
    assert rho < 0.087
    grid = dixon_coles_grid(4.7, 3.4, rho)
    assert (grid >= 0).all()
    assert grid.sum() == pytest.approx(1.0, abs=1e-12)
    # inside the usual range the guard changes nothing
    assert feasible_rho(1.4, 1.1, -0.09) == -0.09
    assert feasible_rho(1.4, 1.1, 0.02) == 0.02
    # negative rho is limited by the larger rate
    assert feasible_rho(5.0, 1.0, -0.5) == pytest.approx(-0.999 / 5.0)


@settings(max_examples=60, deadline=None)
@given(
    lam1=st.floats(min_value=0.0, max_value=80.0),
    lam2=st.floats(min_value=0.0, max_value=80.0),
    rho=st.floats(min_value=-0.3, max_value=0.3),
)
def test_guarded_dixon_coles_grid_is_always_valid(lam1: float, lam2: float, rho: float) -> None:
    from footy.models.grid import clip_rate, feasible_rho

    a, b = clip_rate(lam1), clip_rate(lam2)
    grid = dixon_coles_grid(a, b, feasible_rho(a, b, rho))
    assert (grid >= 0).all()
    assert grid.sum() == pytest.approx(1.0, abs=1e-9)
