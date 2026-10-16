"""``team_form`` snapshot (architecture sections 5.4 and 8.4). Pure functions.

Per team, from the verified results inside the training window: how many matches it has (the
"fewer than 10 matches" rule), its goals for and against per match this season and over its last
10 matches (the goals-only drift inputs, ADR-026), and the date of its latest match.

A row is produced for EVERY active team, including those with no matches (``n_training = 0``): the
Worker then omits them as ``INSUFFICIENT_HISTORY`` instead of treating a missing row as an error,
and the promotion gate's coverage check (95% of active teams) is meaningful. Shots columns exist
in the table but stay NULL in v1.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date

from footy.models.structure import window_matches
from footy.models.types import TrainingMatch

LAST_N = 10


@dataclass(frozen=True)
class TeamForm:
    team_id: int
    n_training: int
    n_season: int
    season_gf: float | None
    season_ga: float | None
    l10_n: int
    l10_gf: float | None
    l10_ga: float | None
    latest_match_date: str | None


def current_season(matches: Sequence[TrainingMatch]) -> str | None:
    """The season label of the most recent match, or None without matches."""
    if not matches:
        return None
    return max(matches, key=lambda m: (m.match_date, m.season)).season


def build_team_form(
    matches: Sequence[TrainingMatch],
    team_ids: Iterable[int],
    as_of: date,
    window_days: int,
) -> list[TeamForm]:
    """One ``TeamForm`` per team in ``team_ids`` plus any other team with matches in the window,
    ordered by team id."""
    used = window_matches(matches, as_of, window_days)
    season = current_season(used)
    played: dict[int, list[tuple[date, str, int, int]]] = defaultdict(list)
    for m in used:
        played[m.home_id].append((m.match_date, m.season, m.goals_home, m.goals_away))
        played[m.away_id].append((m.match_date, m.season, m.goals_away, m.goals_home))

    forms: list[TeamForm] = []
    for team_id in sorted(set(team_ids) | set(played)):
        games = sorted(played.get(team_id, []), key=lambda g: g[0])
        in_season = [g for g in games if season is not None and g[1] == season]
        last = games[-LAST_N:]
        forms.append(
            TeamForm(
                team_id=team_id,
                n_training=len(games),
                n_season=len(in_season),
                season_gf=_mean([g[2] for g in in_season]),
                season_ga=_mean([g[3] for g in in_season]),
                l10_n=len(last),
                l10_gf=_mean([g[2] for g in last]),
                l10_ga=_mean([g[3] for g in last]),
                latest_match_date=games[-1][0].isoformat() if games else None,
            )
        )
    return forms


def _mean(values: Sequence[int]) -> float | None:
    return sum(values) / len(values) if values else None
