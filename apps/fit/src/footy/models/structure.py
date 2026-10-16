"""The pooled team-strength structure shared by Dixon-Coles and the bivariate Poisson (section 8.2,
ADR-007).

For a match with home team h and away team a::

    log lambda_home = mu + gamma + att[h] + def[a]
    log lambda_away = mu + att[a] + def[h]
    att[t] = A[league(t)] + alpha[t]      def[t] = D[league(t)] + beta[t]

``A`` and ``D`` are league offsets; ``alpha`` and ``beta`` are the team deviations, ridge-shrunk
toward their league mean (zero). A ridge on the league offsets too makes the overall level
identifiable. Leagues are connected only through Champions League matches and clubs that moved
between divisions in the window (a hypothesis, judged by the per-competition backtest).

Parameter vector: ``[mu, gamma, A (G), D (G), alpha (T), beta (T)]`` followed by model-specific
extra parameters that the model appends itself.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

import numpy as np
from numpy.typing import NDArray

from footy.models.types import FitConfig, LeagueMap, ModelFitError, TrainingMatch

Floats = NDArray[np.float64]
Ints = NDArray[np.int64]


def decay_weights(match_dates: Sequence[date], as_of: date, half_life_days: float) -> Floats:
    """Weight of a match = 0.5 ** (age_days / half_life) (ADR-009, section 8.2)."""
    if half_life_days <= 0:
        raise ValueError("half_life_days must be positive")
    ages = np.array([(as_of - d).days for d in match_dates], dtype=np.float64)
    return np.power(0.5, ages / half_life_days)


def window_matches(
    matches: Sequence[TrainingMatch], as_of: date, window_days: int
) -> list[TrainingMatch]:
    """Matches with ``as_of - window_days < date <= as_of`` (the rolling 1,095-day window)."""
    return [m for m in matches if 0 <= (as_of - m.match_date).days < window_days]


@dataclass
class Structure:
    team_ids: list[int]
    leagues: list[str]
    team_league: Ints  # league index per team index
    comps: list[str]
    home: Ints  # team index per match
    away: Ints
    comp: Ints  # competition index per match
    x: Floats  # home goals
    y: Floats  # away goals
    w: Floats  # time-decay weight
    config: FitConfig

    @classmethod
    def build(
        cls,
        matches: Sequence[TrainingMatch],
        leagues: LeagueMap,
        as_of: date,
        config: FitConfig,
    ) -> Structure:
        used = window_matches(matches, as_of, config.window_days)
        if len(used) < config.min_matches:
            raise ModelFitError(
                f"only {len(used)} matches in the {config.window_days}-day window "
                f"(minimum {config.min_matches})"
            )
        team_ids = sorted({m.home_id for m in used} | {m.away_id for m in used})
        missing = [t for t in team_ids if t not in leagues]
        if missing:
            raise ModelFitError(f"{len(missing)} teams have no league group (first: {missing[0]})")
        team_index = {t: i for i, t in enumerate(team_ids)}
        league_names = sorted({leagues[t] for t in team_ids})
        league_index = {name: i for i, name in enumerate(league_names)}
        comps = sorted({m.comp_code for m in used})
        comp_index = {c: i for i, c in enumerate(comps)}
        return cls(
            team_ids=team_ids,
            leagues=league_names,
            team_league=np.array([league_index[leagues[t]] for t in team_ids], dtype=np.int64),
            comps=comps,
            home=np.array([team_index[m.home_id] for m in used], dtype=np.int64),
            away=np.array([team_index[m.away_id] for m in used], dtype=np.int64),
            comp=np.array([comp_index[m.comp_code] for m in used], dtype=np.int64),
            x=np.array([m.goals_home for m in used], dtype=np.float64),
            y=np.array([m.goals_away for m in used], dtype=np.float64),
            w=decay_weights([m.match_date for m in used], as_of, config.half_life_days),
            config=config,
        )

    # -- layout ---------------------------------------------------------------------------------

    @property
    def n_teams(self) -> int:
        return len(self.team_ids)

    @property
    def n_leagues(self) -> int:
        return len(self.leagues)

    @property
    def n_base(self) -> int:
        return 2 + 2 * self.n_leagues + 2 * self.n_teams

    def _slices(self) -> tuple[slice, slice, slice, slice]:
        g, t = self.n_leagues, self.n_teams
        a = slice(2, 2 + g)
        d = slice(2 + g, 2 + 2 * g)
        alpha = slice(2 + 2 * g, 2 + 2 * g + t)
        beta = slice(2 + 2 * g + t, 2 + 2 * g + 2 * t)
        return a, d, alpha, beta

    def initial(self) -> Floats:
        theta = np.zeros(self.n_base, dtype=np.float64)
        mean_goals = float(np.average(self.x + self.y, weights=self.w)) / 2.0
        theta[0] = float(np.log(max(mean_goals, 0.1)))
        theta[1] = 0.2
        return theta

    def bounds(self) -> list[tuple[float, float]]:
        b = self.config.param_bound
        return [(-b, b)] * self.n_base

    # -- linear predictor -----------------------------------------------------------------------

    def strengths(self, theta: Floats) -> tuple[Floats, Floats]:
        """Total attack and defence per team index (league offset plus team deviation)."""
        a, d, alpha, beta = self._slices()
        att = theta[a][self.team_league] + theta[alpha]
        dfn = theta[d][self.team_league] + theta[beta]
        return att, dfn

    def log_lambdas(self, theta: Floats) -> tuple[Floats, Floats]:
        att, dfn = self.strengths(theta)
        eta1 = theta[0] + theta[1] + att[self.home] + dfn[self.away]
        eta2 = theta[0] + att[self.away] + dfn[self.home]
        return eta1, eta2

    def gradient(self, g1: Floats, g2: Floats) -> Floats:
        """Map d(objective)/d(eta1) and d/d(eta2) per match onto the base parameters."""
        t, g = self.n_teams, self.n_leagues
        a, d, alpha, beta = self._slices()
        out = np.zeros(self.n_base, dtype=np.float64)
        out[0] = g1.sum() + g2.sum()
        out[1] = g1.sum()
        d_alpha = np.bincount(self.home, weights=g1, minlength=t) + np.bincount(
            self.away, weights=g2, minlength=t
        )
        d_beta = np.bincount(self.away, weights=g1, minlength=t) + np.bincount(
            self.home, weights=g2, minlength=t
        )
        out[alpha] = d_alpha
        out[beta] = d_beta
        out[a] = np.bincount(self.team_league, weights=d_alpha, minlength=g)
        out[d] = np.bincount(self.team_league, weights=d_beta, minlength=g)
        return out

    def penalty(self, theta: Floats) -> tuple[float, Floats]:
        """Ridge penalty and its gradient over the base parameters."""
        a, d, alpha, beta = self._slices()
        cfg = self.config
        grad = np.zeros(self.n_base, dtype=np.float64)
        grad[alpha] = cfg.shrink_team * theta[alpha]
        grad[beta] = cfg.shrink_team * theta[beta]
        grad[a] = cfg.shrink_league * theta[a]
        grad[d] = cfg.shrink_league * theta[d]
        value = 0.5 * float(np.dot(grad, theta))
        return value, grad

    # -- reading a fitted vector ----------------------------------------------------------------

    def league_offsets(self, theta: Floats) -> tuple[dict[str, float], dict[str, float]]:
        a, d, _alpha, _beta = self._slices()
        return (
            {name: float(theta[a][i]) for i, name in enumerate(self.leagues)},
            {name: float(theta[d][i]) for i, name in enumerate(self.leagues)},
        )

    def mean_lambda_by_competition(self, eta1: Floats, eta2: Floats) -> dict[str, float]:
        """Mean fitted goal rate per competition (both sides), the sanity check of section 8.2."""
        lam = np.exp(eta1) + np.exp(eta2)
        counts = np.bincount(self.comp, minlength=len(self.comps))
        sums = np.bincount(self.comp, weights=lam, minlength=len(self.comps))
        return {c: float(sums[i] / counts[i] / 2.0) for i, c in enumerate(self.comps)}

    def check_strengths(self, theta: Floats, eta1: Floats, eta2: Floats) -> dict[str, object]:
        """Sanity checks shared by both models (section 8.2); raises ``ModelFitError``."""
        cfg = self.config
        if not np.all(np.isfinite(theta)):
            raise ModelFitError("a fitted parameter is not finite")
        att, dfn = self.strengths(theta)
        worst = float(max(np.max(np.abs(att)), np.max(np.abs(dfn))))
        if worst > cfg.max_abs_strength:
            raise ModelFitError(
                f"a team strength of {worst:.2f} exceeds the bound {cfg.max_abs_strength}"
            )
        means = self.mean_lambda_by_competition(eta1, eta2)
        for comp, value in means.items():
            if not cfg.min_mean_lambda <= value <= cfg.max_mean_lambda:
                raise ModelFitError(
                    f"mean goal rate {value:.2f} in {comp} is outside "
                    f"[{cfg.min_mean_lambda}, {cfg.max_mean_lambda}]"
                )
        return {"max_abs_strength": worst, "mean_lambda_by_competition": means}
