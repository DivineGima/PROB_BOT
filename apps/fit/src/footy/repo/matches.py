"""Repository for ``matches`` (SQL lives here only). Upserts are keyed on ``fd_match_id`` and are
idempotent; the reconcile layer decides *what* may be written (forward-only status, no clashes)."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from footy.reconcile.matches import ExistingMatch, MatchRow
from footy.repo.d1_client import Statement, insert_statements
from footy.repo.ports import Database

_COLUMNS = [
    "comp_code",
    "season",
    "match_date",
    "kickoff_utc",
    "home_team_id",
    "away_team_id",
    "status",
    "goals_home",
    "goals_away",
    "result_basis",
    "fd_match_id",
    "goals_source",
    "updated_at",
]


class MatchesRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    @staticmethod
    def upsert_statements(rows: Iterable[MatchRow], updated_at: str) -> list[Statement]:
        values = [
            (
                r.comp_code,
                r.season,
                r.match_date,
                r.kickoff_utc,
                r.home_team_id,
                r.away_team_id,
                r.status,
                r.goals_home,
                r.goals_away,
                r.result_basis,
                r.fd_match_id,
                r.goals_source,
                updated_at,
            )
            for r in rows
        ]
        return insert_statements(
            "matches", _COLUMNS, values, conflict="upsert", conflict_target=["fd_match_id"]
        )

    def load_existing(self, pairs: Iterable[tuple[str, str]]) -> list[ExistingMatch]:
        """All stored matches for the given (comp_code, season) pairs, in one request."""
        statements = [
            Statement(
                "SELECT match_id, fd_match_id, comp_code, season, match_date, kickoff_utc, "
                "home_team_id, away_team_id, status, goals_home, goals_away, result_basis "
                "FROM matches WHERE comp_code = ? AND season = ?",
                (comp, season),
            )
            for comp, season in sorted(set(pairs))
        ]
        found: list[ExistingMatch] = []
        for rows in self._db.batch(statements):
            for r in rows:
                found.append(
                    ExistingMatch(
                        match_id=int(r["match_id"]),
                        fd_match_id=None if r["fd_match_id"] is None else int(r["fd_match_id"]),
                        comp_code=str(r["comp_code"]),
                        season=str(r["season"]),
                        match_date=str(r["match_date"]),
                        kickoff_utc=None if r["kickoff_utc"] is None else str(r["kickoff_utc"]),
                        home_team_id=int(r["home_team_id"]),
                        away_team_id=int(r["away_team_id"]),
                        status=str(r["status"]),
                        goals_home=None if r["goals_home"] is None else int(r["goals_home"]),
                        goals_away=None if r["goals_away"] is None else int(r["goals_away"]),
                        result_basis=None if r["result_basis"] is None else str(r["result_basis"]),
                    )
                )
        return found

    def freshness(self) -> dict[str, str]:
        """Latest verified finished match date per competition (section 8.5 'Freshness')."""
        rows = self._db.query(
            "SELECT comp_code, MAX(match_date) AS latest FROM matches "
            "WHERE status = 'FINISHED' AND result_basis IN ('regular', 'ft_90') "
            "GROUP BY comp_code"
        )
        return {str(r["comp_code"]): str(r["latest"]) for r in rows}

    def counts_by_competition(self) -> dict[str, dict[str, int]]:
        """Row counts per competition: total, verified results, unverified results."""
        rows = self._db.query(
            "SELECT comp_code, COUNT(*) AS total, "
            "SUM(CASE WHEN result_basis IN ('regular', 'ft_90') THEN 1 ELSE 0 END) AS verified, "
            "SUM(CASE WHEN result_basis = 'unverified' THEN 1 ELSE 0 END) AS unverified "
            "FROM matches GROUP BY comp_code"
        )
        return {
            str(r["comp_code"]): {
                "total": int(r["total"]),
                "verified": int(r["verified"] or 0),
                "unverified": int(r["unverified"] or 0),
            }
            for r in rows
        }

    def team_match_counts(self, team_ids: Sequence[int]) -> dict[int, int]:
        """Verified matches per team (for the 'fewer than 10 matches' warm-up report)."""
        out: dict[int, int] = {}
        ids = list(team_ids)
        for start in range(0, len(ids), 45):
            chunk = ids[start : start + 45]
            marks = ", ".join("?" for _ in chunk)
            rows = self._db.query(
                "SELECT team_id, COUNT(*) AS n FROM ("  # noqa: S608
                "SELECT home_team_id AS team_id FROM matches "
                "WHERE result_basis IN ('regular', 'ft_90') "
                f"AND home_team_id IN ({marks}) "
                "UNION ALL SELECT away_team_id FROM matches "
                "WHERE result_basis IN ('regular', 'ft_90') "
                f"AND away_team_id IN ({marks})) GROUP BY team_id",
                [*chunk, *chunk],
            )
            for r in rows:
                out[int(r["team_id"])] = int(r["n"])
        return out
