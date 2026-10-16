"""Pi-rating model (architecture section 8.2, ADR-006, verify-at-build item 8).

Constantinou and Fenton (2013), "Determining the level of ability of football teams by dynamic
ratings based on the relative discrepancies in scores between adversaries". Every team starts at 0
and has a home rating ``H`` and an away rating ``A``. For a match between home team X and away team
Y, with ratings read BEFORE the match:

* expected goal difference of a team against the average opponent at its ground:
  ``g(R) = sign(R) * (b ** (|R| / c) - 1)`` with b = 10, c = 3;
* predicted match goal difference ``gD = g(H_X) - g(A_Y)``; observed ``D = goals_X - goals_Y``;
* error ``e = |D - gD|``, weighted ``psi(e) = c * log10(1 + e)``;
* ``psi_H = +psi(e)`` if ``gD < D`` else ``-psi(e)`` (the home side did better or worse than
  predicted), and ``psi_A = -psi_H``;
* ``H_X += lambda * psi_H``; ``A_X += gamma * (change in H_X)``;
  ``A_Y += lambda * psi_A``; ``H_Y += gamma * (change in A_Y)``;
* the paper's optimum on five EPL seasons is lambda = 0.035 and gamma = 0.7.

The paper gives expected goal DIFFERENCES, not scorelines. The mapping to a grid is this project's
hypothesis (GR-07, judged by the backtest): with the league's mean total goals ``T`` and the
predicted difference ``d = s * gD`` (``s`` is a scale fitted on the training window by regressing
observed on predicted differences through the origin), ``lambda_home = max(eps, (T + d) / 2)`` and
``lambda_away = max(eps, (T - d) / 2)``, then an independent Poisson grid.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

import numpy as np

from footy.models.grid import Grid, clip_rate, independent_grid
from footy.models.structure import decay_weights, window_matches
from footy.models.types import (
    MODEL_PI,
    FitConfig,
    FitOutcome,
    LeagueMap,
    ModelFitError,
    TrainingMatch,
    run_fit,
)

PAYLOAD_VERSION = 1


@dataclass(frozen=True)
class PiParams:
    """Constants of the paper (lambda, gamma, b, c) plus this project's mapping constants."""

    learning_rate: float = 0.035  # lambda
    catch_up_rate: float = 0.7  # gamma
    base: float = 10.0  # b
    scale: float = 3.0  # c
    min_rate: float = 0.05  # epsilon: floor of a mapped goal rate
    max_abs_rating: float = 3.0  # sanity bound on any rating (3 -> about 9 goals of difference)

    def as_dict(self) -> dict[str, float]:
        return {
            "learning_rate": self.learning_rate,
            "catch_up_rate": self.catch_up_rate,
            "base": self.base,
            "scale": self.scale,
            "min_rate": self.min_rate,
            "max_abs_rating": self.max_abs_rating,
        }


def expected_goal_difference(rating: float, params: PiParams = PiParams()) -> float:  # noqa: B008
    """``g(R)``: the expected goal difference against the average opponent."""
    magnitude = float(params.base ** (abs(rating) / params.scale)) - 1.0
    return magnitude if rating >= 0 else -magnitude


def weighted_error(error: float, params: PiParams = PiParams()) -> float:  # noqa: B008
    """``psi(e) = c * log10(1 + e)``."""
    return params.scale * math.log10(1.0 + error)


def predicted_difference(home_rating_h: float, away_rating_a: float, params: PiParams) -> float:
    return expected_goal_difference(home_rating_h, params) - expected_goal_difference(
        away_rating_a, params
    )


def pi_rates(
    home_rating_h: float, away_rating_a: float, diff_scale: float, total: float, params: PiParams
) -> tuple[float, float]:
    """The hypothesis mapping from two ratings to goal rates: ``d = diff_scale * gD``,
    ``lambda_home = max(eps, (total + d) / 2)``, ``lambda_away = max(eps, (total - d) / 2)``."""
    d = diff_scale * predicted_difference(home_rating_h, away_rating_a, params)
    return max(params.min_rate, (total + d) / 2.0), max(params.min_rate, (total - d) / 2.0)


Ratings = dict[int, list[float]]  # team_id -> [home rating, away rating]


def update_ratings(
    ratings: Ratings, home_id: int, away_id: int, goals_home: int, goals_away: int, params: PiParams
) -> float:
    """Apply one match to ``ratings`` in place; returns the predicted goal difference (read before
    the update)."""
    home = ratings.setdefault(home_id, [0.0, 0.0])
    away = ratings.setdefault(away_id, [0.0, 0.0])
    predicted = predicted_difference(home[0], away[1], params)
    observed = float(goals_home - goals_away)
    psi = weighted_error(abs(observed - predicted), params)
    psi_home = psi if predicted < observed else -psi
    psi_away = -psi_home
    old_home_h, old_away_a = home[0], away[1]
    home[0] = old_home_h + params.learning_rate * psi_home
    home[1] += params.catch_up_rate * (home[0] - old_home_h)
    away[1] = old_away_a + params.learning_rate * psi_away
    away[0] += params.catch_up_rate * (away[1] - old_away_a)
    return predicted


class PiModel:
    name = MODEL_PI

    def __init__(
        self,
        ratings: dict[int, tuple[float, float]],
        league_total: dict[str, float],
        pooled_total: float,
        diff_scale: float,
        params: PiParams,
    ) -> None:
        self.ratings = ratings
        self.league_total = league_total
        self.pooled_total = pooled_total
        self.diff_scale = diff_scale
        self.params = params

    def knows(self, team_id: int) -> bool:
        return team_id in self.ratings

    def rates(self, home_id: int, away_id: int, comp_code: str) -> tuple[float, float]:
        total = self.league_total.get(comp_code, self.pooled_total)
        return pi_rates(
            self.ratings[home_id][0],
            self.ratings[away_id][1],
            self.diff_scale,
            total,
            self.params,
        )

    def grid(self, home_id: int, away_id: int, comp_code: str) -> Grid:
        lam1, lam2 = (clip_rate(x) for x in self.rates(home_id, away_id, comp_code))
        return independent_grid(lam1, lam2)

    def to_payload(self) -> dict[str, object]:
        return {
            "payload_version": PAYLOAD_VERSION,
            "model": MODEL_PI,
            "params": self.params.as_dict(),
            "diff_scale": self.diff_scale,
            "pooled_total": self.pooled_total,
            "league_total": self.league_total,
            "teams": {str(t): [h, a] for t, (h, a) in sorted(self.ratings.items())},
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> PiModel:
        if payload.get("payload_version") != PAYLOAD_VERSION or payload.get("model") != MODEL_PI:
            raise ValueError("not a pi-rating payload this code understands")
        teams = payload["teams"]
        league_total = payload["league_total"]
        params = payload["params"]
        if not (
            isinstance(teams, dict) and isinstance(league_total, dict) and isinstance(params, dict)
        ):
            raise ValueError("malformed pi-rating payload")
        return cls(
            ratings={int(t): (float(v[0]), float(v[1])) for t, v in teams.items()},
            league_total={str(k): float(v) for k, v in league_total.items()},
            pooled_total=float(payload["pooled_total"]),  # type: ignore[arg-type]
            diff_scale=float(payload["diff_scale"]),  # type: ignore[arg-type]
            params=PiParams(**{k: float(v) for k, v in params.items()}),
        )


def fit_pi_rating(
    matches: Sequence[TrainingMatch],
    leagues: LeagueMap,
    as_of: date,
    config: FitConfig | None = None,
    params: PiParams | None = None,
) -> tuple[PiModel, dict[str, object]]:
    """One chronological pass over the window. ``leagues`` is accepted for the common fitter
    signature; the rating is league-agnostic (the average team over all leagues is 0)."""
    cfg = config or FitConfig()
    pp = params or PiParams()
    used = sorted(
        window_matches(matches, as_of, cfg.window_days),
        key=lambda m: (m.match_date, m.comp_code, m.home_id, m.away_id),
    )
    if len(used) < cfg.min_matches:
        raise ModelFitError(
            f"only {len(used)} matches in the {cfg.window_days}-day window "
            f"(minimum {cfg.min_matches})"
        )
    ratings: Ratings = {}
    predicted: list[float] = []
    observed: list[float] = []
    for m in used:
        predicted.append(
            update_ratings(ratings, m.home_id, m.away_id, m.goals_home, m.goals_away, pp)
        )
        observed.append(float(m.goals_home - m.goals_away))

    pred = np.array(predicted)
    obs = np.array(observed)
    weights = decay_weights([m.match_date for m in used], as_of, cfg.half_life_days)
    denominator = float(np.dot(weights, pred * pred))
    if denominator <= 0.0:
        raise ModelFitError("the pi-rating pass produced no predicted differences")
    scale = float(np.clip(np.dot(weights, pred * obs) / denominator, 0.2, 2.0))

    totals: dict[str, list[tuple[float, float]]] = {}
    for m, w in zip(used, weights, strict=True):
        totals.setdefault(m.comp_code, []).append((float(m.goals_home + m.goals_away), float(w)))
    league_total = {
        comp: sum(t * w for t, w in rows) / sum(w for _t, w in rows)
        for comp, rows in sorted(totals.items())
    }
    pooled_total = float(
        np.dot(weights, [m.goals_home + m.goals_away for m in used]) / weights.sum()
    )

    worst = max(max(abs(h), abs(a)) for h, a in ratings.values())
    if not all(math.isfinite(x) for h, a in ratings.values() for x in (h, a)):
        raise ModelFitError("a pi rating is not finite")
    if worst > pp.max_abs_rating:
        raise ModelFitError(f"a pi rating of {worst:.2f} exceeds the bound {pp.max_abs_rating}")
    model = PiModel(
        {t: (h, a) for t, (h, a) in ratings.items()}, league_total, pooled_total, scale, pp
    )

    # Mean mapped goal rate per competition over the training matches (section 8.2 sanity check).
    mapped: dict[str, list[float]] = {}
    for m in used:
        lam1, lam2 = model.rates(m.home_id, m.away_id, m.comp_code)
        mapped.setdefault(m.comp_code, []).append((lam1 + lam2) / 2.0)
    means = {c: float(np.mean(v)) for c, v in sorted(mapped.items())}
    for comp, value in means.items():
        if not cfg.min_mean_lambda <= value <= cfg.max_mean_lambda:
            raise ModelFitError(
                f"mean goal rate {value:.2f} in {comp} is outside "
                f"[{cfg.min_mean_lambda}, {cfg.max_mean_lambda}]"
            )
    any_pair = used[-1]
    if (
        abs(float(model.grid(any_pair.home_id, any_pair.away_id, any_pair.comp_code).sum()) - 1.0)
        > 1e-9
    ):
        raise ModelFitError("the test grid does not sum to 1")

    diagnostics: dict[str, object] = {
        "n_matches": len(used),
        "n_teams": len(ratings),
        "diff_scale": scale,
        "max_abs_rating": float(worst),
        "mean_lambda_by_competition": means,
        "mean_abs_prediction_error": float(np.mean(np.abs(obs - pred))),
    }
    return model, diagnostics


def fit_pi_outcome(
    matches: Sequence[TrainingMatch],
    leagues: LeagueMap,
    as_of: date,
    config: FitConfig | None = None,
) -> FitOutcome:
    return run_fit(MODEL_PI, lambda: fit_pi_rating(matches, leagues, as_of, config))
