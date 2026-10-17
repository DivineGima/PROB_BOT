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
from typing import Any

import numpy as np

from footy.models.grid import Grid, clip_rate, dixon_coles_grid, feasible_rho
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


class DcModel(PooledStrengthModel):
    name = MODEL_DC

    def __init__(self, rho: float, **base: Any) -> None:
        super().__init__(**base)
        self.rho = rho

    def grid(self, home_id: int, away_id: int, comp_code: str) -> Grid:
        lam1, lam2 = (clip_rate(x) for x in self.lambdas(home_id, away_id))
        return dixon_coles_grid(lam1, lam2, feasible_rho(lam1, lam2, self.rho))

    def to_payload(self) -> dict[str, object]:
        return {**self.base_payload(PAYLOAD_VERSION), "rho": self.rho}

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> DcModel:
        return cls(rho=read_number(payload, "rho"), **read_base(payload, MODEL_DC, PAYLOAD_VERSION))


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
    base, rho, value, iterations = fit_pooled(
        objective, s, 0.0, (-cfg.rho_bound, cfg.rho_bound), cfg
    )
    diagnostics = sanity_and_diagnostics(s, base, value, iterations)
    league_att, league_def, teams = team_tables(s, base)
    model = DcModel(
        rho=rho,
        mu=float(base[0]),
        gamma=float(base[1]),
        league_att=league_att,
        league_def=league_def,
        teams=teams,
        half_life_days=cfg.half_life_days,
    )
    # A typical fixture must give a valid grid (section 8.2 sanity check).
    typical = dixon_coles_grid(float(np.exp(base[0] + base[1])), float(np.exp(base[0])), rho)
    if abs(float(typical.sum()) - 1.0) > 1e-9:
        raise ModelFitError("the test grid does not sum to 1")
    return model, {**diagnostics, "rho": rho}


def fit_dc_outcome(
    matches: Sequence[TrainingMatch],
    leagues: LeagueMap,
    as_of: date,
    config: FitConfig | None = None,
) -> FitOutcome:
    return run_fit(MODEL_DC, lambda: fit_dixon_coles(matches, leagues, as_of, config))
