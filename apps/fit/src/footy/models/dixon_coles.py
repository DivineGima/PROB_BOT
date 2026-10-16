"""Dixon-Coles model (architecture section 8.2, ADR-005/007/009/019).

Independent Poisson goal counts with the Dixon-Coles low-score correction tau on (0,0), (0,1),
(1,0), (1,1)::

    P(x, y) = tau(x, y) * Po(x; lambda_home) * Po(y; lambda_away)

fitted by maximising the time-decay-weighted log-likelihood minus a ridge penalty (the team
shrinkage of ``footy.models.structure``). The objective and its analytic gradient are vectorised
over matches and minimised with L-BFGS-B. The correction factors sum to zero over the infinite
support, so the likelihood needs no normalising constant; the 13x13 grid is renormalised only for
the 12-goal cut-off (``footy.models.grid``).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import numpy as np
from scipy.optimize import minimize

from footy.models.grid import Grid, clip_rate, dixon_coles_grid, feasible_rho
from footy.models.structure import Floats, Structure
from footy.models.types import (
    MODEL_DC,
    FitConfig,
    FitOutcome,
    LeagueMap,
    ModelFitError,
    TrainingMatch,
    run_fit,
)

PAYLOAD_VERSION = 1
_TAU_FLOOR = 1e-10


def _tau_terms(
    x: Floats, y: Floats, lam1: Floats, lam2: Floats, rho: float
) -> tuple[Floats, Floats, Floats, Floats]:
    """Return (log tau, d log tau / d eta1, d log tau / d eta2, d log tau / d rho) per match."""
    m00 = (x == 0) & (y == 0)
    m01 = (x == 0) & (y == 1)
    m10 = (x == 1) & (y == 0)
    m11 = (x == 1) & (y == 1)
    tau = np.ones_like(x)
    tau[m00] = 1.0 - lam1[m00] * lam2[m00] * rho
    tau[m01] = 1.0 + lam1[m01] * rho
    tau[m10] = 1.0 + lam2[m10] * rho
    tau[m11] = 1.0 - rho
    tau = np.maximum(tau, _TAU_FLOOR)
    d1 = np.zeros_like(x)
    d2 = np.zeros_like(x)
    dr = np.zeros_like(x)
    d1[m00] = -lam1[m00] * lam2[m00] * rho / tau[m00]
    d2[m00] = d1[m00]
    dr[m00] = -lam1[m00] * lam2[m00] / tau[m00]
    d1[m01] = lam1[m01] * rho / tau[m01]
    dr[m01] = lam1[m01] / tau[m01]
    d2[m10] = lam2[m10] * rho / tau[m10]
    dr[m10] = lam2[m10] / tau[m10]
    dr[m11] = -1.0 / tau[m11]
    return np.log(tau), d1, d2, dr


def objective(theta: Floats, s: Structure) -> tuple[float, Floats]:
    """Negative penalised weighted log-likelihood and its gradient (last element is rho)."""
    base = theta[:-1]
    rho = float(theta[-1])
    eta1, eta2 = s.log_lambdas(base)
    lam1, lam2 = np.exp(eta1), np.exp(eta2)
    log_tau, t1, t2, tr = _tau_terms(s.x, s.y, lam1, lam2, rho)
    ll = s.x * eta1 - lam1 + s.y * eta2 - lam2 + log_tau  # constant log-factorials dropped
    g1 = s.w * (s.x - lam1 + t1)
    g2 = s.w * (s.y - lam2 + t2)
    pen_value, pen_grad = s.penalty(base)
    value = -float(np.dot(s.w, ll)) + pen_value
    grad = np.empty_like(theta)
    grad[:-1] = -s.gradient(g1, g2) + pen_grad
    grad[-1] = -float(np.dot(s.w, tr))
    return value, grad


class DcModel:
    name = MODEL_DC

    def __init__(
        self,
        mu: float,
        gamma: float,
        rho: float,
        league_att: dict[str, float],
        league_def: dict[str, float],
        teams: dict[int, tuple[float, float, str]],
        half_life_days: float,
    ) -> None:
        self.mu, self.gamma, self.rho = mu, gamma, rho
        self.league_att, self.league_def = league_att, league_def
        self.teams = teams  # team_id -> (attack, defence, league), league offset included
        self.half_life_days = half_life_days

    def knows(self, team_id: int) -> bool:
        return team_id in self.teams

    def lambdas(self, home_id: int, away_id: int) -> tuple[float, float]:
        home, away = self.teams[home_id], self.teams[away_id]
        lam1 = float(np.exp(self.mu + self.gamma + home[0] + away[1]))
        lam2 = float(np.exp(self.mu + away[0] + home[1]))
        return lam1, lam2

    def grid(self, home_id: int, away_id: int, comp_code: str) -> Grid:
        lam1, lam2 = (clip_rate(x) for x in self.lambdas(home_id, away_id))
        return dixon_coles_grid(lam1, lam2, feasible_rho(lam1, lam2, self.rho))

    def to_payload(self) -> dict[str, object]:
        return {
            "payload_version": PAYLOAD_VERSION,
            "model": MODEL_DC,
            "mu": self.mu,
            "gamma": self.gamma,
            "rho": self.rho,
            "half_life_days": self.half_life_days,
            "league_att": self.league_att,
            "league_def": self.league_def,
            "teams": {str(t): [a, d, lg] for t, (a, d, lg) in sorted(self.teams.items())},
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> DcModel:
        if payload.get("payload_version") != PAYLOAD_VERSION or payload.get("model") != MODEL_DC:
            raise ValueError("not a Dixon-Coles payload this code understands")
        teams_raw = payload["teams"]
        assert isinstance(teams_raw, dict)  # noqa: S101 (shape was written by to_payload)
        return cls(
            mu=float(payload["mu"]),  # type: ignore[arg-type]
            gamma=float(payload["gamma"]),  # type: ignore[arg-type]
            rho=float(payload["rho"]),  # type: ignore[arg-type]
            league_att=dict(payload["league_att"]),  # type: ignore[call-overload]
            league_def=dict(payload["league_def"]),  # type: ignore[call-overload]
            teams={int(t): (float(v[0]), float(v[1]), str(v[2])) for t, v in teams_raw.items()},
            half_life_days=float(payload["half_life_days"]),  # type: ignore[arg-type]
        )


def fit_dixon_coles(
    matches: Sequence[TrainingMatch],
    leagues: LeagueMap,
    as_of: date,
    config: FitConfig | None = None,
) -> tuple[DcModel, dict[str, object]]:
    """Fit on the matches inside the window ending at ``as_of``. Raises ``ModelFitError`` when the
    data is too thin, the optimiser does not converge or a sanity check fails."""
    cfg = config or FitConfig()
    s = Structure.build(matches, leagues, as_of, cfg)
    x0 = np.append(s.initial(), 0.0)
    bounds = [*s.bounds(), (-cfg.rho_bound, cfg.rho_bound)]
    result = minimize(
        objective,
        x0,
        args=(s,),
        jac=True,
        method="L-BFGS-B",
        bounds=bounds,
        options={"maxiter": cfg.max_iterations, "ftol": 1e-12, "gtol": 1e-6},
    )
    theta = result.x
    if not result.success:
        raise ModelFitError(f"optimiser did not converge: {result.message}")
    if not np.isfinite(result.fun):
        raise ModelFitError("objective is not finite")

    base, rho = theta[:-1], float(theta[-1])
    eta1, eta2 = s.log_lambdas(base)
    checks = s.check_strengths(base, eta1, eta2)
    att, dfn = s.strengths(base)
    league_att, league_def = s.league_offsets(base)
    teams = {
        tid: (float(att[i]), float(dfn[i]), s.leagues[int(s.team_league[i])])
        for i, tid in enumerate(s.team_ids)
    }
    model = DcModel(
        mu=float(base[0]),
        gamma=float(base[1]),
        rho=rho,
        league_att=league_att,
        league_def=league_def,
        teams=teams,
        half_life_days=cfg.half_life_days,
    )
    # A typical fixture must give a valid grid (section 8.2 sanity check).
    typical = dixon_coles_grid(float(np.exp(base[0] + base[1])), float(np.exp(base[0])), rho)
    if abs(float(typical.sum()) - 1.0) > 1e-9:
        raise ModelFitError("the test grid does not sum to 1")
    diagnostics: dict[str, object] = {
        "iterations": int(result.nit),
        "objective": float(result.fun),
        "n_matches": len(s.x),
        "n_teams": s.n_teams,
        "effective_matches": float(s.w.sum()),
        "rho": rho,
        "home_advantage": float(base[1]),
        **checks,
    }
    return model, diagnostics


def fit_dc_outcome(
    matches: Sequence[TrainingMatch],
    leagues: LeagueMap,
    as_of: date,
    config: FitConfig | None = None,
) -> FitOutcome:
    return run_fit(MODEL_DC, lambda: fit_dixon_coles(matches, leagues, as_of, config))
