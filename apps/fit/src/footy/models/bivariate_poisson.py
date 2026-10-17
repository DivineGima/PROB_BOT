"""Bivariate Poisson model (architecture section 8.2, ADR-007/019): Karlis and Ntzoufras.

``X = X1 + Z`` and ``Y = X2 + Z`` with ``X1 ~ Po(lambda1)``, ``X2 ~ Po(lambda2)`` and a shared
``Z ~ Po(lambda3)``, so ``P(x, y) = sum_k Po(x-k; lambda1) Po(y-k; lambda2) Po(k; lambda3)``, which
equals the closed form of section 8.2. The rates ``lambda1`` and ``lambda2`` use the same pooled
team-strength structure as Dixon-Coles (``footy.models.structure``); ``lambda3`` is one shared
constant (``exp`` of the last parameter).

The gradient needs no finite differences: for this distribution
``dP(x,y)/dlambda1 = P(x-1,y) - P(x,y)``, ``dP/dlambda2 = P(x,y-1) - P(x,y)`` and
``dP/dlambda3 = P(x-1,y-1) - P(x,y)`` (a pmf at a negative index is 0).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

import numpy as np
from numpy.typing import NDArray
from scipy.special import gammaln

from footy.models.grid import Grid, bivariate_poisson_grid, clip_covariance, clip_rate
from footy.models.pooled import (
    PooledStrengthModel,
    fit_pooled,
    read_base,
    read_number,
    sanity_and_diagnostics,
    team_tables,
)
from footy.models.structure import Floats, Structure
from footy.models.types import (
    MODEL_BP,
    FitConfig,
    FitOutcome,
    LeagueMap,
    ModelFitError,
    TrainingMatch,
    run_fit,
)

PAYLOAD_VERSION = 1
LOG_LAMBDA3_BOUNDS = (-8.0, 0.0)  # lambda3 between about 0.0003 and 1
LOG_LAMBDA3_START = float(np.log(0.1))

# log(n!) for n = 0..63 (goals are at most 20): a table lookup replaces ten gammaln calls per
# evaluation of the objective, which runs up to thousands of times per fit.
_LOG_FACTORIAL = gammaln(np.arange(64) + 1.0)


def log_pmf(x: Floats, y: Floats, eta1: Floats, eta2: Floats, theta3: float) -> Floats:
    """log P(x, y) per element; ``-inf`` where x or y is negative."""
    valid = (x >= 0) & (y >= 0)
    xs = np.where(valid, x, 0.0)
    ys = np.where(valid, y, 0.0)
    lam1, lam2, lam3 = np.exp(eta1), np.exp(eta2), float(np.exp(theta3))
    kmax = int(min(xs.max(initial=0.0), ys.max(initial=0.0)))
    ix, iy = xs.astype(np.int64), ys.astype(np.int64)
    terms: list[NDArray[np.float64]] = []
    for k in range(kmax + 1):
        ok = valid & (xs >= k) & (ys >= k)
        rest_x = np.where(ok, ix - k, 0)
        rest_y = np.where(ok, iy - k, 0)
        term = (
            (xs - k) * eta1
            - lam1
            - _LOG_FACTORIAL[rest_x]
            + (ys - k) * eta2
            - lam2
            - _LOG_FACTORIAL[rest_y]
            + k * theta3
            - lam3
            - _LOG_FACTORIAL[k]
        )
        terms.append(np.where(ok, term, -np.inf))
    stacked = np.vstack(terms)
    peak = np.max(stacked, axis=0)
    safe_peak = np.where(np.isfinite(peak), peak, 0.0)
    summed = np.sum(np.exp(stacked - safe_peak), axis=0)
    finite = np.isfinite(peak)
    total = safe_peak + np.log(np.where(finite, summed, 1.0))
    return np.where(finite, total, -np.inf)


def objective(theta: Floats, s: Structure) -> tuple[float, Floats]:
    """Negative penalised weighted log-likelihood and its gradient (last element is log lambda3)."""
    base = theta[:-1]
    theta3 = float(theta[-1])
    eta1, eta2 = s.log_lambdas(base)
    lam1, lam2, lam3 = np.exp(eta1), np.exp(eta2), float(np.exp(theta3))
    log_f = log_pmf(s.x, s.y, eta1, eta2, theta3)
    log_f10 = log_pmf(s.x - 1.0, s.y, eta1, eta2, theta3)
    log_f01 = log_pmf(s.x, s.y - 1.0, eta1, eta2, theta3)
    log_f11 = log_pmf(s.x - 1.0, s.y - 1.0, eta1, eta2, theta3)
    r10 = np.exp(log_f10 - log_f)  # exp(-inf) is 0 where the shifted index is negative
    r01 = np.exp(log_f01 - log_f)
    r11 = np.exp(log_f11 - log_f)
    g1 = s.w * lam1 * (r10 - 1.0)
    g2 = s.w * lam2 * (r01 - 1.0)
    pen_value, pen_grad = s.penalty(base)
    value = -float(np.dot(s.w, log_f)) + pen_value
    grad = np.empty_like(theta)
    grad[:-1] = -s.gradient(g1, g2) + pen_grad
    grad[-1] = -float(np.dot(s.w, lam3 * (r11 - 1.0)))
    return value, grad


class BpModel(PooledStrengthModel):
    name = MODEL_BP

    def __init__(self, lambda3: float, **base: Any) -> None:
        super().__init__(**base)
        self.lambda3 = lambda3

    def grid(self, home_id: int, away_id: int, comp_code: str) -> Grid:
        lam1, lam2 = (clip_rate(x) for x in self.lambdas(home_id, away_id))
        return bivariate_poisson_grid(lam1, lam2, clip_covariance(self.lambda3))

    def to_payload(self) -> dict[str, object]:
        return {**self.base_payload(PAYLOAD_VERSION), "lambda3": self.lambda3}

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> BpModel:
        return cls(
            lambda3=read_number(payload, "lambda3"),
            **read_base(payload, MODEL_BP, PAYLOAD_VERSION),
        )


def fit_bivariate_poisson(
    matches: Sequence[TrainingMatch],
    leagues: LeagueMap,
    as_of: date,
    config: FitConfig | None = None,
) -> tuple[BpModel, dict[str, object]]:
    cfg = config or FitConfig()
    s = Structure.build(matches, leagues, as_of, cfg)
    base, theta3, value, iterations = fit_pooled(
        objective, s, LOG_LAMBDA3_START, LOG_LAMBDA3_BOUNDS, cfg
    )
    lambda3 = float(np.exp(theta3))
    diagnostics = sanity_and_diagnostics(s, base, value, iterations)
    league_att, league_def, teams = team_tables(s, base)
    model = BpModel(
        lambda3=lambda3,
        mu=float(base[0]),
        gamma=float(base[1]),
        league_att=league_att,
        league_def=league_def,
        teams=teams,
        half_life_days=cfg.half_life_days,
    )
    typical = bivariate_poisson_grid(
        float(np.exp(base[0] + base[1])), float(np.exp(base[0])), lambda3
    )
    if abs(float(typical.sum()) - 1.0) > 1e-9:
        raise ModelFitError("the test grid does not sum to 1")
    return model, {**diagnostics, "lambda3": lambda3}


def fit_bp_outcome(
    matches: Sequence[TrainingMatch],
    leagues: LeagueMap,
    as_of: date,
    config: FitConfig | None = None,
) -> FitOutcome:
    return run_fit(MODEL_BP, lambda: fit_bivariate_poisson(matches, leagues, as_of, config))
