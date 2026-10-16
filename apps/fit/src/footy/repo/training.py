"""Read-only repository for model training data (SQL lives here only): verified finished matches
and the league group of every club. Results are read in keyset pages so one request never has to
carry the whole table, and only rows with a verified 90-minute score are returned (invariant 3,
section 5.7)."""

from __future__ import annotations

from datetime import date

from footy.models.types import UCL_ONLY_LEAGUE, TrainingMatch
from footy.repo.ports import Database

PAGE_SIZE = 2000


class TrainingRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    def finished_matches(
        self, date_from: date | None = None, date_to: date | None = None
    ) -> list[TrainingMatch]:
        """Verified finished matches with ``date_from <= match_date <= date_to`` (either bound
        optional), ordered by date."""
        low = date_from.isoformat() if date_from else "0000-01-01"
        high = date_to.isoformat() if date_to else "9999-12-31"
        out: list[TrainingMatch] = []
        last_id = 0
        while True:
            rows = self._db.query(
                "SELECT match_id, comp_code, season, match_date, home_team_id, away_team_id, "
                "goals_home, goals_away FROM matches "
                "WHERE status = 'FINISHED' AND result_basis IN ('regular', 'ft_90') "
                "AND goals_home IS NOT NULL AND goals_away IS NOT NULL "
                "AND match_date >= ? AND match_date <= ? AND match_id > ? "
                "ORDER BY match_id LIMIT ?",
                (low, high, last_id, PAGE_SIZE),
            )
            for r in rows:
                out.append(
                    TrainingMatch(
                        comp_code=str(r["comp_code"]),
                        goals_home=int(r["goals_home"]),
                        goals_away=int(r["goals_away"]),
                        match_date=date.fromisoformat(str(r["match_date"])),
                        home_id=int(r["home_team_id"]),
                        away_id=int(r["away_team_id"]),
                        season=str(r["season"]),
                    )
                )
            if len(rows) < PAGE_SIZE:
                break
            last_id = int(rows[-1]["match_id"])
        out.sort(key=lambda m: (m.match_date, m.home_id, m.away_id))
        return out

    def league_groups(self) -> dict[int, str]:
        """League group per team: its home competition, or ``UCL_ONLY`` for clubs without one."""
        rows = self._db.query("SELECT team_id, home_comp FROM teams")
        return {
            int(r["team_id"]): str(r["home_comp"]) if r["home_comp"] else UCL_ONLY_LEAGUE
            for r in rows
        }

    def active_team_ids(self) -> list[int]:
        rows = self._db.query("SELECT team_id FROM teams WHERE active = 1 ORDER BY team_id")
        return [int(r["team_id"]) for r in rows]
