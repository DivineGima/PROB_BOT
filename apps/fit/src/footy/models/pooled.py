"""What Dixon-Coles and the bivariate Poisson share (architecture section 8.2): the fitted team
table and its payload, and the L-BFGS-B fit on the pooled structure of ``footy.models.structure``.

A model supplies only what differs: its objective (likelihood and gradient), one extra parameter
(rho, or log lambda3), and how it turns two goal rates into a grid. Keeping the rest here means a
fix to convergence handling or payload parsing reaches both models (an earlier optimiser fix had to
be applied twice).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
from scipy.optimize import minimize

from footy.models.structure import Floats, Structure
from footy.models.types import FitConfig, ModelFitError

Objective = Callable[[Floats, Structure], tuple[float, Floats]]
Teams = dict[int, tuple[float, float, str]]  # team_id -> (attack, defence, league)

GTOL = 1e-6


class PooledStrengthModel:
    """Fitted team strengths on the pooled structure: ``log lambda_home = mu + gamma + att[h] +
    def[a]`` and ``log lambda_away = mu + att[a] + def[h]``, league offsets already inside the
    team values."""

    name = "pooled"

    def __init__(
        self,
        mu: float,
        gamma: float,
        league_att: dict[str, float],
        league_def: dict[str, float],
        teams: Teams,
        half_life_days: float,
    ) -> None:
        self.mu, self.gamma = mu, gamma
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

    def base_payload(self, version: int) -> dict[str, object]:
        return {
            "payload_version": version,
            "model": self.name,
            "mu": self.mu,
            "gamma": self.gamma,
            "half_life_days": self.half_life_days,
            "league_att": self.league_att,
            "league_def": self.league_def,
            "teams": {str(t): [a, d, lg] for t, (a, d, lg) in sorted(self.teams.items())},
        }


def read_number(payload: dict[str, object], key: str) -> float:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"payload field {key!r} is missing or not a number")
    return float(value)


def read_base(payload: dict[str, object], model: str, version: int) -> dict[str, Any]:
    """The constructor arguments shared by every pooled model, validated; raises ``ValueError``
    for a payload of another model or version, or one that is malformed."""
    if payload.get("payload_version") != version or payload.get("model") != model:
        raise ValueError(f"not a {model!r} payload version {version}")
    teams, league_att, league_def = (
        payload.get("teams"),
        payload.get("league_att"),
        payload.get("league_def"),
    )
    if not (
        isinstance(teams, dict) and isinstance(league_att, dict) and isinstance(league_def, dict)
    ):
        raise ValueError(f"malformed {model!r} payload")
    try:
        parsed: Teams = {int(t): (float(v[0]), float(v[1]), str(v[2])) for t, v in teams.items()}
        offsets = (
            {str(k): float(v) for k, v in league_att.items()},
            {str(k): float(v) for k, v in league_def.items()},
        )
    except (TypeError, ValueError, IndexError, KeyError) as exc:
        raise ValueError(f"malformed {model!r} payload: {exc}") from None
    return {
        "mu": read_number(payload, "mu"),
        "gamma": read_number(payload, "gamma"),
        "league_att": offsets[0],
        "league_def": offsets[1],
        "teams": parsed,
        "half_life_days": read_number(payload, "half_life_days"),
    }


def fit_pooled(
    objective: Objective,
    s: Structure,
    extra_start: float,
    extra_bounds: tuple[float, float],
    cfg: FitConfig,
) -> tuple[Floats, float, float, int]:
    """Minimise ``objective`` over the base parameters plus one extra parameter (the last
    element). Returns ``(base, extra, objective value, iterations)``; raises ``ModelFitError``
    when the optimiser does not converge or the objective is not finite."""
    result = minimize(
        objective,
        np.append(s.initial(), extra_start),
        args=(s,),
        jac=True,
        method="L-BFGS-B",
        bounds=[*s.bounds(), extra_bounds],
        options={"maxiter": cfg.max_iterations, "ftol": cfg.tolerance, "gtol": GTOL},
    )
    if not result.success:
        raise ModelFitError(f"optimiser did not converge: {result.message}")
    if not np.isfinite(result.fun):
        raise ModelFitError("objective is not finite")
    return result.x[:-1], float(result.x[-1]), float(result.fun), int(result.nit)


def team_tables(s: Structure, base: Floats) -> tuple[dict[str, float], dict[str, float], Teams]:
    """League offsets and the per-team (attack, defence, league) table of a fitted vector."""
    att, dfn = s.strengths(base)
    league_att, league_def = s.league_offsets(base)
    teams = {
        tid: (float(att[i]), float(dfn[i]), s.leagues[int(s.team_league[i])])
        for i, tid in enumerate(s.team_ids)
    }
    return league_att, league_def, teams


def sanity_and_diagnostics(
    s: Structure, base: Floats, value: float, iterations: int
) -> dict[str, object]:
    """The strength and goal-rate sanity checks of section 8.2 (raising ``ModelFitError``) and the
    diagnostics both models report."""
    eta1, eta2 = s.log_lambdas(base)
    checks = s.check_strengths(base, eta1, eta2)
    return {
        "iterations": iterations,
        "objective": value,
        "n_matches": len(s.x),
        "n_teams": s.n_teams,
        "effective_matches": float(s.w.sum()),
        "home_advantage": float(base[1]),
        **checks,
    }
