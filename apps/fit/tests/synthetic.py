"""Synthetic league generator (architecture sections 9.5 and ADR-025). Test code only.

Generates matches from KNOWN parameters (attack, defence, home advantage, rho, league offsets) so
that parameter recovery and walk-forward behaviour can be tested against the truth. Several leagues
are linked by a Champions-League-like set of cross-league matches. Seeds make it deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np

from footy.models.grid import GRID_SIZE, dixon_coles_grid
from footy.models.types import TrainingMatch

COMP_CODES = ("EPL", "LL", "BL", "SA", "L1")


@dataclass
class SyntheticWorld:
    matches: list[TrainingMatch]
    leagues: dict[int, str]
    attack: dict[int, float]  # total attack, league offset included
    defence: dict[int, float]
    mu: float
    gamma: float
    rho: float
    as_of: date
    comp_of_team: dict[int, str] = field(default_factory=dict)

    def lambdas(self, home_id: int, away_id: int) -> tuple[float, float]:
        lam1 = float(np.exp(self.mu + self.gamma + self.attack[home_id] + self.defence[away_id]))
        lam2 = float(np.exp(self.mu + self.attack[away_id] + self.defence[home_id]))
        return lam1, lam2


def generate_world(
    seed: int = 7,
    *,
    n_leagues: int = 3,
    teams_per_league: int = 10,
    seasons: int = 2,
    link_top: int = 4,
    as_of: date = date(2026, 5, 31),
    mu: float = 0.15,
    gamma: float = 0.25,
    rho: float = -0.08,
    team_sd: float = 0.25,
    league_sd: float = 0.12,
) -> SyntheticWorld:
    if not 1 <= n_leagues <= len(COMP_CODES):
        raise ValueError("n_leagues out of range")
    rng = np.random.default_rng(seed)
    leagues: dict[int, str] = {}
    comp_of_team: dict[int, str] = {}
    attack: dict[int, float] = {}
    defence: dict[int, float] = {}
    members: dict[str, list[int]] = {}
    next_id = 1
    for li in range(n_leagues):
        code = COMP_CODES[li]
        offset_att = float(rng.normal(0.0, league_sd))
        offset_def = float(rng.normal(0.0, league_sd))
        members[code] = []
        for _ in range(teams_per_league):
            attack[next_id] = offset_att + float(rng.normal(0.0, team_sd))
            defence[next_id] = offset_def + float(rng.normal(0.0, team_sd))
            leagues[next_id] = code
            comp_of_team[next_id] = code
            members[code].append(next_id)
            next_id += 1

    world = SyntheticWorld([], leagues, attack, defence, mu, gamma, rho, as_of, comp_of_team)
    pairs: list[tuple[str, int, int, date]] = []
    for s in range(seasons):
        season_end = as_of - timedelta(days=365 * (seasons - 1 - s))
        season_start = season_end - timedelta(days=270)
        for code, ids in members.items():
            for h in ids:
                for a in ids:
                    if h != a:
                        pairs.append((code, h, a, _random_day(rng, season_start, 270)))
        top: list[int] = []
        for ids in members.values():
            ranked = sorted(ids, key=lambda t: attack[t] - defence[t], reverse=True)
            top.extend(ranked[:link_top])
        for h in top:
            for a in top:
                if h != a and leagues[h] != leagues[a]:
                    pairs.append(("UCL", h, a, _random_day(rng, season_start, 270)))

    pairs.sort(key=lambda p: (p[3], p[1], p[2]))
    for code, h, a, day in pairs:
        gh, ga = _sample_score(rng, world, h, a)
        world.matches.append(
            TrainingMatch(
                comp_code=code,
                goals_home=gh,
                goals_away=ga,
                match_date=day,
                home_id=h,
                away_id=a,
                season=f"{day.year if day.month >= 7 else day.year - 1}",
            )
        )
    return world


def _random_day(rng: np.random.Generator, start: date, span: int) -> date:
    return start + timedelta(days=int(rng.integers(0, span)))


def _sample_score(
    rng: np.random.Generator, world: SyntheticWorld, h: int, a: int
) -> tuple[int, int]:
    lam1, lam2 = world.lambdas(h, a)
    grid = dixon_coles_grid(lam1, lam2, world.rho)
    cell = int(rng.choice(GRID_SIZE * GRID_SIZE, p=grid.ravel()))
    return cell // GRID_SIZE, cell % GRID_SIZE
