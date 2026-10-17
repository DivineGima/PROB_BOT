"""Grid engine and markets: the Python numerical reference (architecture section 8.1, ADR-005).

One 13x13 grid per match and model: ``grid[i, j]`` is P(home scores i, away scores j) for
0 <= i, j <= 12. The mass beyond 12 goals is dropped and the grid renormalised, so it sums to 1.
Every market is derived from the (pooled) grid, never computed separately:

* P(home) = sum over i > j, P(draw) = sum over i = j, P(away) = sum over i < j;
* P(over L) = sum over i + j > L for L in 0.5 .. 5.5 (Under is 1 - Over, never stored);
* the total-goals pmf has categories 0 .. 11 and 12+ (used for the totals RPS).

All functions are pure. The TypeScript engine of the Worker must match these within 1e-9 (golden
vectors in ``packages/contracts/golden``).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

Grid = NDArray[np.float64]

GRID_SIZE = 13
OVER_LINES: tuple[float, ...] = (0.5, 1.5, 2.5, 3.5, 4.5, 5.5)
TOTAL_CATEGORIES = 13  # totals 0 .. 11 and "12 or more"

_LOG_FACTORIAL = np.array([math.lgamma(k + 1) for k in range(GRID_SIZE)], dtype=np.float64)
_IDX_I, _IDX_J = np.indices((GRID_SIZE, GRID_SIZE))
_HOME_MASK = _IDX_I > _IDX_J
_DRAW_MASK = _IDX_I == _IDX_J
_AWAY_MASK = _IDX_I < _IDX_J
_RAW_TOTAL = _IDX_I + _IDX_J  # 0 .. 24
_TOTAL_CATEGORY = np.minimum(_RAW_TOTAL, TOTAL_CATEGORIES - 1)

# Largest rate the grid is meant for; far beyond it the 12-goal cut-off loses real mass.
MAX_RATE = 6.0


class GridError(ValueError):
    """The inputs cannot produce a valid grid (negative or non-finite rate, tau below zero)."""


@dataclass(frozen=True)
class Markets:
    p_home: float
    p_draw: float
    p_away: float
    overs: tuple[float, ...]  # P(over L) for L in OVER_LINES
    total_pmf: tuple[float, ...]  # TOTAL_CATEGORIES values

    def as_dict(self) -> dict[str, object]:
        return {
            "p_home": self.p_home,
            "p_draw": self.p_draw,
            "p_away": self.p_away,
            "overs": list(self.overs),
            "total_pmf": list(self.total_pmf),
        }

    @classmethod
    def from_dict(cls, data: object) -> Markets:
        """Rebuild markets from ``as_dict`` output (for example a stored baseline snapshot).
        Raises ``GridError`` for anything that is not a complete, finite set of probabilities."""
        if not isinstance(data, dict):
            raise GridError("markets must be an object")
        try:
            p = [float(data[k]) for k in ("p_home", "p_draw", "p_away")]
            overs = tuple(float(v) for v in data["overs"])
            total = tuple(float(v) for v in data["total_pmf"])
        except (KeyError, TypeError, ValueError):
            raise GridError("markets are incomplete or not numeric") from None
        if len(overs) != len(OVER_LINES) or len(total) != TOTAL_CATEGORIES:
            raise GridError("markets have the wrong number of lines or total categories")
        if not all(math.isfinite(v) and 0.0 <= v <= 1.0 for v in (*p, *overs, *total)):
            raise GridError("market probabilities must be finite and within 0..1")
        return cls(p[0], p[1], p[2], overs, total)


MIN_RATE = 0.01
# Floor of the bivariate Poisson covariance rate. It sits BELOW the fit's own lower bound
# (exp(-8), about 0.0003), so a fitted covariance is never changed when a grid is built.
MIN_COVARIANCE = 1e-4


def clip_rate(rate: float) -> float:
    """Guard for extreme fixtures (a very strong side against a very weak one, or a rate from a
    barely identified team): keep a fitted rate inside the range the 12-goal grid supports."""
    return min(max(rate, MIN_RATE), MAX_RATE)


def clip_covariance(rate: float) -> float:
    """Like ``clip_rate`` for the shared bivariate Poisson term, whose legitimate values reach far
    below the 0.01 goal-rate floor (a fitted 0.002 must stay 0.002)."""
    return min(max(rate, MIN_COVARIANCE), MAX_RATE)


def feasible_rho(lam_home: float, lam_away: float, rho: float) -> float:
    """Clamp rho to the interval where every Dixon-Coles factor stays positive for these rates:
    -1/max(lam) < rho < min(1, 1/(lam_home*lam_away)). Inside the usual range it changes nothing."""
    low = -0.999 / max(lam_home, lam_away, 1.0)
    high = min(0.999, 0.999 / (lam_home * lam_away))
    return min(max(rho, low), high)


def _check_rate(name: str, value: float) -> float:
    if not math.isfinite(value) or value < 0 or value > MAX_RATE:
        raise GridError(f"{name}={value!r} is outside 0..{MAX_RATE}")
    return float(value)


def poisson_pmf(rate: float) -> NDArray[np.float64]:
    """P(X = k) for k = 0 .. 12 (not renormalised)."""
    rate = _check_rate("rate", rate)
    if rate == 0.0:
        out = np.zeros(GRID_SIZE, dtype=np.float64)
        out[0] = 1.0
        return out
    k = np.arange(GRID_SIZE, dtype=np.float64)
    return np.exp(k * math.log(rate) - rate - _LOG_FACTORIAL)


def _normalise(grid: Grid) -> Grid:
    total = float(grid.sum())
    if not math.isfinite(total) or total <= 0.0:
        raise GridError("grid has no probability mass")
    return grid / total


def independent_grid(lam_home: float, lam_away: float) -> Grid:
    """Independent Poisson grid, renormalised (the pi-rating model's grid, ADR-006)."""
    return _normalise(np.outer(poisson_pmf(lam_home), poisson_pmf(lam_away)))


def dc_tau(lam_home: float, lam_away: float, rho: float) -> tuple[float, float, float, float]:
    """Dixon-Coles correction for the cells (0,0), (0,1), (1,0), (1,1)."""
    return (
        1.0 - lam_home * lam_away * rho,
        1.0 + lam_home * rho,
        1.0 + lam_away * rho,
        1.0 - rho,
    )


def dixon_coles_grid(lam_home: float, lam_away: float, rho: float) -> Grid:
    """Independent Poisson with the Dixon-Coles tau on the four low-score cells, renormalised."""
    if not math.isfinite(rho):
        raise GridError("rho is not finite")
    grid = np.outer(poisson_pmf(lam_home), poisson_pmf(lam_away))
    t00, t01, t10, t11 = dc_tau(lam_home, lam_away, rho)
    if min(t00, t01, t10, t11) < 0.0:
        raise GridError("rho makes a Dixon-Coles correction factor negative")
    grid[0, 0] *= t00
    grid[0, 1] *= t01
    grid[1, 0] *= t10
    grid[1, 1] *= t11
    return _normalise(grid)


def bivariate_poisson_grid(lam1: float, lam2: float, lam3: float) -> Grid:
    """Karlis-Ntzoufras bivariate Poisson: X = X1 + Z, Y = X2 + Z with X1~Po(lam1), X2~Po(lam2)
    and the shared Z~Po(lam3). P(i, j) = sum_k Po(i-k; lam1) Po(j-k; lam2) Po(k; lam3), which
    equals the closed form of section 8.2 but is built from stable pmf terms. Renormalised after
    the 12-goal cut."""
    p1, p2, p3 = poisson_pmf(lam1), poisson_pmf(lam2), poisson_pmf(lam3)
    grid = np.zeros((GRID_SIZE, GRID_SIZE), dtype=np.float64)
    for k in range(GRID_SIZE):
        grid[k:, k:] += p3[k] * np.outer(p1[: GRID_SIZE - k], p2[: GRID_SIZE - k])
    return _normalise(grid)


def mix_grids(grids: Sequence[Grid], weights: Sequence[float]) -> Grid:
    """Weighted linear pool G = sum w_m G_m with sum w_m = 1 (section 8.1)."""
    if not grids or len(grids) != len(weights):
        raise GridError("need one weight per grid and at least one grid")
    w = np.asarray(weights, dtype=np.float64)
    if not np.all(np.isfinite(w)) or np.any(w < 0) or abs(float(w.sum()) - 1.0) > 1e-9:
        raise GridError("weights must be non-negative and sum to 1")
    mixed = np.zeros((GRID_SIZE, GRID_SIZE), dtype=np.float64)
    for grid, weight in zip(grids, w, strict=True):
        mixed += weight * grid
    return mixed


def markets(grid: Grid) -> Markets:
    """Every market the bot reports, derived from the one grid."""
    if grid.shape != (GRID_SIZE, GRID_SIZE):
        raise GridError(f"grid must be {GRID_SIZE}x{GRID_SIZE}")
    raw = np.bincount(_RAW_TOTAL.ravel(), weights=grid.ravel(), minlength=2 * GRID_SIZE - 1)
    # P(total > L) for L = k + 0.5 is the mass of totals >= k + 1.
    tail = np.cumsum(raw[::-1])[::-1]
    overs = tuple(float(tail[int(line + 0.5)]) for line in OVER_LINES)
    pmf = np.bincount(_TOTAL_CATEGORY.ravel(), weights=grid.ravel(), minlength=TOTAL_CATEGORIES)
    return Markets(
        p_home=float(grid[_HOME_MASK].sum()),
        p_draw=float(grid[_DRAW_MASK].sum()),
        p_away=float(grid[_AWAY_MASK].sum()),
        overs=overs,
        total_pmf=tuple(float(x) for x in pmf),
    )
