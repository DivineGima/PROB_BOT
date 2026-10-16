"""Scoring rules (architecture sections 8.1 and 8.7). Pure functions.

* RPS for the ordered 1X2 outcome (home, draw, away) and for total goals (categories 0 .. 11, 12+);
  the 1/(r-1) normalisation of Constantinou and Fenton is used, so a perfect forecast scores 0 and
  the worst possible forecast scores 1;
* log loss of the 1X2 outcome;
* Brier score of each over line (the stored over probabilities against the observed total).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from footy.models.grid import OVER_LINES, TOTAL_CATEGORIES, Markets

HOME, DRAW, AWAY = 0, 1, 2
MIN_PROBABILITY = 1e-15  # log loss floor: a zero forecast of a real outcome is finite, not inf


def outcome_1x2(goals_home: int, goals_away: int) -> int:
    if goals_home > goals_away:
        return HOME
    return DRAW if goals_home == goals_away else AWAY


def total_category(goals_home: int, goals_away: int) -> int:
    return min(goals_home + goals_away, TOTAL_CATEGORIES - 1)


def rps(probabilities: Sequence[float], observed: int) -> float:
    """Ranked probability score of an ordered categorical forecast; ``observed`` is the index of
    the category that happened."""
    r = len(probabilities)
    if r < 2:
        raise ValueError("RPS needs at least two categories")
    if not 0 <= observed < r:
        raise ValueError("observed category is out of range")
    cumulative_forecast = 0.0
    total = 0.0
    for k in range(r - 1):
        cumulative_forecast += probabilities[k]
        cumulative_observed = 1.0 if k >= observed else 0.0
        total += (cumulative_forecast - cumulative_observed) ** 2
    return total / (r - 1)


def rps_1x2(p_home: float, p_draw: float, p_away: float, goals_home: int, goals_away: int) -> float:
    return rps((p_home, p_draw, p_away), outcome_1x2(goals_home, goals_away))


def rps_totals(total_pmf: Sequence[float], goals_home: int, goals_away: int) -> float:
    if len(total_pmf) != TOTAL_CATEGORIES:
        raise ValueError(f"total pmf needs {TOTAL_CATEGORIES} categories")
    return rps(total_pmf, total_category(goals_home, goals_away))


def log_loss_1x2(
    p_home: float, p_draw: float, p_away: float, goals_home: int, goals_away: int
) -> float:
    p = (p_home, p_draw, p_away)[outcome_1x2(goals_home, goals_away)]
    return -math.log(max(p, MIN_PROBABILITY))


def brier_over(p_over: float, goals_home: int, goals_away: int, line: float) -> float:
    happened = 1.0 if goals_home + goals_away > line else 0.0
    return (p_over - happened) ** 2


@dataclass(frozen=True)
class ScoredForecast:
    rps_1x2: float
    rps_totals: float
    logloss_1x2: float
    brier_overs: tuple[float, ...]  # one per OVER_LINES entry


def score_forecast(forecast: Markets, goals_home: int, goals_away: int) -> ScoredForecast:
    return ScoredForecast(
        rps_1x2=rps_1x2(forecast.p_home, forecast.p_draw, forecast.p_away, goals_home, goals_away),
        rps_totals=rps_totals(forecast.total_pmf, goals_home, goals_away),
        logloss_1x2=log_loss_1x2(
            forecast.p_home, forecast.p_draw, forecast.p_away, goals_home, goals_away
        ),
        brier_overs=tuple(
            brier_over(p, goals_home, goals_away, line)
            for p, line in zip(forecast.overs, OVER_LINES, strict=True)
        ),
    )


@dataclass(frozen=True)
class MeanScores:
    n: int
    rps_1x2: float
    rps_totals: float
    logloss_1x2: float
    brier_overs: tuple[float, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "n": self.n,
            "rps_1x2": self.rps_1x2,
            "rps_totals": self.rps_totals,
            "logloss_1x2": self.logloss_1x2,
            "brier_overs": list(self.brier_overs),
        }


def mean_scores(scored: Sequence[ScoredForecast]) -> MeanScores:
    if not scored:
        raise ValueError("no scored forecasts to average")
    n = len(scored)
    return MeanScores(
        n=n,
        rps_1x2=sum(s.rps_1x2 for s in scored) / n,
        rps_totals=sum(s.rps_totals for s in scored) / n,
        logloss_1x2=sum(s.logloss_1x2 for s in scored) / n,
        brier_overs=tuple(
            sum(s.brier_overs[k] for s in scored) / n for k in range(len(OVER_LINES))
        ),
    )
