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

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import minimize
from scipy.special import gammaln

from footy.models.grid import Grid, bivariate_poisson_grid, clip_rate
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


def log_pmf(x: Floats, y: Floats, eta1: Floats, eta2: Floats, theta3: float) -> Floats:
    """log P(x, y) per element; ``-inf`` where x or y is negative."""
    valid = (x >= 0) & (y >= 0)
    xs = np.where(valid, x, 0.0)
    ys = np.where(valid, y, 0.0)
    lam1, lam2, lam3 = np.exp(eta1), np.exp(eta2), float(np.exp(theta3))
    kmax = int(min(xs.max(initial=0.0), ys.max(initial=0.0)))
    terms: list[NDArray[np.float64]] = []
    for k in range(kmax + 1):
        ok = valid & (xs >= k) & (ys >= k)
        term = (
            (xs - k) * eta1
            - lam1
            - gammaln(xs - k + 1.0)
            + (ys - k) * eta2
            - lam2
            - gammaln(ys - k + 1.0)
            + k * theta3
            - lam3
            - gammaln(k + 1.0)
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


class BpModel:
    name = MODEL_BP

    def __init__(
        self,
        mu: float,
        gamma: float,
        lambda3: float,
        league_att: dict[str, float],
        league_def: dict[str, float],
        teams: dict[int, tuple[float, float, str]],
        half_life_days: float,
    ) -> None:
        self.mu, self.gamma, self.lambda3 = mu, gamma, lambda3
        self.league_att, self.league_def = league_att, league_def
        self.teams = teams
        self.half_life_days = half_life_days

    def knows(self, team_id: int) -> bool:
        return team_id in self.teams

    def lambdas(self, home_id: int, away_id: int) -> tuple[float, float]:
        home, away = self.teams[home_id], self.teams[away_id]
        return (
            float(np.exp(self.mu + self.gamma + home[0] + away[1])),
            float(np.exp(self.mu + away[0] + home[1])),
        )

    def grid(self, home_id: int, away_id: int, comp_code: str) -> Grid:
        lam1, lam2 = (clip_rate(x) for x in self.lambdas(home_id, away_id))
        return bivariate_poisson_grid(lam1, lam2, clip_rate(self.lambda3))

    def to_payload(self) -> dict[str, object]:
        return {
            "payload_version": PAYLOAD_VERSION,
            "model": MODEL_BP,
            "mu": self.mu,
            "gamma": self.gamma,
            "lambda3": self.lambda3,
            "half_life_days": self.half_life_days,
            "league_att": self.league_att,
            "league_def": self.league_def,
            "teams": {str(t): [a, d, lg] for t, (a, d, lg) in sorted(self.teams.items())},
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> BpModel:
        if payload.get("payload_version") != PAYLOAD_VERSION or payload.get("model") != MODEL_BP:
            raise ValueError("not a bivariate Poisson payload this code understands")
        teams = payload["teams"]
        league_att, league_def = payload["league_att"], payload["league_def"]
        if not (
            isinstance(teams, dict)
            and isinstance(league_att, dict)
            and isinstance(league_def, dict)
        ):
            raise ValueError("malformed bivariate Poisson payload")
        return cls(
            mu=float(payload["mu"]),  # type: ignore[arg-type]
            gamma=float(payload["gamma"]),  # type: ignore[arg-type]
            lambda3=float(payload["lambda3"]),  # type: ignore[arg-type]
            league_att={str(k): float(v) for k, v in league_att.items()},
            league_def={str(k): float(v) for k, v in league_def.items()},
            teams={int(t): (float(v[0]), float(v[1]), str(v[2])) for t, v in teams.items()},
            half_life_days=float(payload["half_life_days"]),  # type: ignore[arg-type]
        )


def fit_bivariate_poisson(
    matches: Sequence[TrainingMatch],
    leagues: LeagueMap,
    as_of: date,
    config: FitConfig | None = None,
) -> tuple[BpModel, dict[str, object]]:
    cfg = config or FitConfig()
    s = Structure.build(matches, leagues, as_of, cfg)
    x0 = np.append(s.initial(), LOG_LAMBDA3_START)
    bounds = [*s.bounds(), LOG_LAMBDA3_BOUNDS]
    result = minimize(
        objective,
        x0,
        args=(s,),
        jac=True,
        method="L-BFGS-B",
        bounds=bounds,
        options={"maxiter": cfg.max_iterations, "ftol": 1e-12, "gtol": 1e-6},
    )
    if not result.success:
        raise ModelFitError(f"optimiser did not converge: {result.message}")
    if not np.isfinite(result.fun):
        raise ModelFitError("objective is not finite")
    base, theta3 = result.x[:-1], float(result.x[-1])
    lambda3 = float(np.exp(theta3))
    eta1, eta2 = s.log_lambdas(base)
    checks = s.check_strengths(base, eta1, eta2)
    att, dfn = s.strengths(base)
    league_att, league_def = s.league_offsets(base)
    teams = {
        tid: (float(att[i]), float(dfn[i]), s.leagues[int(s.team_league[i])])
        for i, tid in enumerate(s.team_ids)
    }
    model = BpModel(
        float(base[0]), float(base[1]), lambda3, league_att, league_def, teams, cfg.half_life_days
    )
    typical = bivariate_poisson_grid(
        float(np.exp(base[0] + base[1])), float(np.exp(base[0])), lambda3
    )
    if abs(float(typical.sum()) - 1.0) > 1e-9:
        raise ModelFitError("the test grid does not sum to 1")
    diagnostics: dict[str, object] = {
        "iterations": int(result.nit),
        "objective": float(result.fun),
        "n_matches": len(s.x),
        "n_teams": s.n_teams,
        "effective_matches": float(s.w.sum()),
        "lambda3": lambda3,
        "home_advantage": float(base[1]),
        **checks,
    }
    return model, diagnostics


def fit_bp_outcome(
    matches: Sequence[TrainingMatch],
    leagues: LeagueMap,
    as_of: date,
    config: FitConfig | None = None,
) -> FitOutcome:
    return run_fit(MODEL_BP, lambda: fit_bivariate_poisson(matches, leagues, as_of, config))
