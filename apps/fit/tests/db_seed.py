"""Seed a SQLite-backed fake D1 with a synthetic world (test code, ADR-025)."""

from __future__ import annotations

from tests.helpers import SqliteD1
from tests.synthetic import SyntheticWorld

COMPETITION_NAMES = {
    "EPL": "Premier League",
    "LL": "La Liga",
    "BL": "Bundesliga",
    "SA": "Serie A",
    "L1": "Ligue 1",
    "UCL": "Champions League",
}


def seed_world(db: SqliteD1, world: SyntheticWorld, *, active: bool = True) -> None:
    """Insert competitions, teams (id = synthetic id, league as home_comp) and every match as a
    verified finished ``ft_90`` result."""
    conn = db.conn
    for code, name in COMPETITION_NAMES.items():
        conn.execute("INSERT INTO competitions (comp_code, name) VALUES (?, ?)", (code, name))
    for team_id, league in sorted(world.leagues.items()):
        conn.execute(
            "INSERT INTO teams (team_id, canonical_name, home_comp, is_ucl_only, active) "
            "VALUES (?, ?, ?, 0, ?)",
            (team_id, f"Team {team_id}", league, int(active)),
        )
    for number, m in enumerate(world.matches, start=1):
        conn.execute(
            "INSERT INTO matches (comp_code, season, match_date, kickoff_utc, home_team_id, "
            "away_team_id, status, goals_home, goals_away, result_basis, fd_match_id, "
            "goals_source, updated_at) VALUES (?, ?, ?, NULL, ?, ?, 'FINISHED', ?, ?, 'ft_90', ?, "
            "'fd_org', '2026-06-01T00:00:00Z')",
            (
                m.comp_code,
                m.season,
                m.match_date.isoformat(),
                m.home_id,
                m.away_id,
                m.goals_home,
                m.goals_away,
                number,
            ),
        )


def seed_scheduled(db: SqliteD1, fixtures: list[tuple[str, str, int, int]]) -> None:
    """Insert scheduled (not yet played) matches: ``(comp_code, 'YYYY-MM-DD', home_id, away_id)``.
    The kickoff is 15:00 UTC on that date."""
    for number, (comp, day, home, away) in enumerate(fixtures, start=900_000):
        db.conn.execute(
            "INSERT INTO matches (comp_code, season, match_date, kickoff_utc, home_team_id, "
            "away_team_id, status, fd_match_id, goals_source, updated_at) VALUES "
            "(?, '2026-27', ?, ?, ?, ?, 'TIMED', ?, 'fd_org', '2026-06-01T00:00:00Z')",
            (comp, day, f"{day}T15:00:00Z", home, away, number),
        )
