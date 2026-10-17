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


def seed_reference(db: SqliteD1, n_teams: int = 40) -> None:
    """The reference rows the Stage 5b/6 tables point at: the competitions and ``n_teams`` clubs."""
    for code, name in COMPETITION_NAMES.items():
        db.conn.execute(
            "INSERT OR IGNORE INTO competitions (comp_code, name) VALUES (?, ?)", (code, name)
        )
    for team_id in range(1, n_teams + 1):
        db.conn.execute(
            "INSERT OR IGNORE INTO teams (team_id, canonical_name, home_comp, is_ucl_only, active) "
            "VALUES (?, ?, 'EPL', 0, 1)",
            (team_id, f"Club {team_id}"),
        )


TOTAL_PMF = [0.1, 0.2, 0.3, 0.2, 0.1, 0.05, 0.03, 0.01, 0.005, 0.003, 0.001, 0.0005, 0.0005]
OVERS = [0.9, 0.7, 0.4, 0.2, 0.1, 0.05]
BASELINE = {
    "p_home": 0.45,
    "p_draw": 0.27,
    "p_away": 0.28,
    "overs": [0.95, 0.8, 0.5, 0.28, 0.12, 0.05],
    "total_pmf": [
        0.05,
        0.15,
        0.25,
        0.22,
        0.14,
        0.08,
        0.05,
        0.03,
        0.015,
        0.008,
        0.004,
        0.002,
        0.001,
    ],
}


def seed_prediction(
    db: SqliteD1,
    *,
    comp: str = "EPL",
    day: str = "2026-10-17",
    home: int = 1,
    away: int = 2,
    p: tuple[float, float, float] = (0.5, 0.3, 0.2),
    models: dict[str, dict[str, object]] | None = None,
    kickoff: str | None = None,
    run_id: str = "R1",
    baseline: object = BASELINE,
    total: list[float] | None = None,
    status: str = "pending",
    goals: tuple[int, int] | None = None,
    rps: tuple[float, float, float] | None = None,
) -> int:
    """Insert a logged prediction the way the Worker would (plus an upload row for its key)."""
    import json

    conn = db.conn
    conn.execute(
        "INSERT OR IGNORE INTO uploads (upload_id, update_id, received_at, status) "
        "VALUES (1, 1, '2026-10-17T06:00:00Z', 'processed')"
    )
    if models is None:
        models = {
            name: {"p": list(p), "total": list(total or TOTAL_PMF)} for name in ("dc", "pi", "bp")
        }
    key = f"{day}|{comp}|{home}|{away}"
    cursor = conn.execute(
        "INSERT INTO predictions (fixture_key, upload_id, run_id, label, comp_code, match_date, "
        "kickoff_utc, home_team_id, away_team_id, p_home, p_draw, p_away, p_over_05, p_over_15, "
        "p_over_25, p_over_35, p_over_45, p_over_55, total_json, models_json, weights_json, "
        "drift_json, baseline_json, inputs_json, status, void_reason, goals_home, goals_away, "
        "rps_1x2, rps_totals, logloss_1x2, created_at, scored_at) VALUES "
        "(?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '{}', '{}', ?, '{}', "
        "?, NULL, ?, ?, ?, ?, ?, '2026-10-17T06:00:00Z', ?)",
        (
            key,
            run_id,
            f"label-{key}",
            comp,
            day,
            kickoff or f"{day}T15:00:00Z",
            home,
            away,
            *p,
            *OVERS,
            json.dumps(total or TOTAL_PMF),
            json.dumps(models),
            json.dumps(baseline) if baseline is not None else "not json",
            status,
            goals[0] if goals else None,
            goals[1] if goals else None,
            rps[0] if rps else None,
            rps[1] if rps else None,
            rps[2] if rps else None,
            "2026-10-18T01:00:00Z" if status != "pending" else None,
        ),
    )
    return int(cursor.lastrowid or 0)


def seed_match(
    db: SqliteD1,
    *,
    comp: str = "EPL",
    day: str = "2026-10-17",
    home: int = 1,
    away: int = 2,
    status: str = "FINISHED",
    goals: tuple[int, int] | None = (2, 0),
    basis: str | None = "ft_90",
    fd_id: int | None = None,
) -> None:
    db.conn.execute(
        "INSERT INTO matches (comp_code, season, match_date, kickoff_utc, home_team_id, "
        "away_team_id, status, goals_home, goals_away, result_basis, fd_match_id, goals_source, "
        "updated_at) VALUES (?, '2026-27', ?, ?, ?, ?, ?, ?, ?, ?, ?, 'fd_org', "
        "'2026-10-18T00:00:00Z')",
        (
            comp,
            day,
            f"{day}T15:00:00Z",
            home,
            away,
            status,
            goals[0] if goals else None,
            goals[1] if goals else None,
            basis,
            fd_id if fd_id is not None else 700_000 + home * 100 + away,
        ),
    )
