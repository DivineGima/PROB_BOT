"""Repository for the reference tables: competitions, teams and aliases (SQL lives here only).

Writes are idempotent upserts built with ``insert_statements`` (bound parameters only, at most 100
per statement), so a re-run or a resumed run converges to the same state.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from footy.config import Competition
from footy.repo.d1_client import Statement, insert_statements
from footy.repo.ports import Database


class ReferenceRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    # -- statements for the (resumable) bootstrap ------------------------------------------------

    @staticmethod
    def competition_statements(competitions: Iterable[Competition]) -> list[Statement]:
        rows = [(c.comp_code, c.name, c.fd_code, c.uk_div, c.has_shots) for c in competitions]
        return insert_statements(
            "competitions",
            ["comp_code", "name", "fd_code", "uk_div", "has_shots"],
            rows,
            conflict="upsert",
            conflict_target=["comp_code"],
        )

    @staticmethod
    def team_statements(teams: Iterable[tuple[str, str | None, bool, bool]]) -> list[Statement]:
        """``teams``: (canonical_name, home_comp, is_ucl_only, active)."""
        rows = [(name, comp, int(ucl), int(active)) for name, comp, ucl, active in teams]
        return insert_statements(
            "teams",
            ["canonical_name", "home_comp", "is_ucl_only", "active"],
            rows,
            conflict="upsert",
            conflict_target=["canonical_name"],
        )

    @staticmethod
    def alias_statements(aliases: Iterable[tuple[str, str, int]]) -> list[Statement]:
        """``aliases``: (source, alias_norm, team_id)."""
        return insert_statements(
            "team_aliases",
            ["source", "alias_norm", "team_id"],
            list(aliases),
            conflict="upsert",
            conflict_target=["source", "alias_norm"],
        )

    # -- reads -----------------------------------------------------------------------------------

    def team_ids(self) -> dict[str, int]:
        rows = self._db.query("SELECT team_id, canonical_name FROM teams")
        return {str(r["canonical_name"]): int(r["team_id"]) for r in rows}

    def team_names(self) -> dict[int, str]:
        return {team_id: name for name, team_id in self.team_ids().items()}

    def alias_table(self, source: str) -> dict[str, int]:
        rows = self._db.query(
            "SELECT alias_norm, team_id FROM team_aliases WHERE source = ?", (source,)
        )
        return {str(r["alias_norm"]): int(r["team_id"]) for r in rows}

    def counts(self) -> dict[str, int]:
        statements = [
            Statement("SELECT COUNT(*) AS n FROM competitions"),
            Statement("SELECT COUNT(*) AS n FROM teams WHERE active = 1"),
            Statement("SELECT COUNT(*) AS n FROM teams WHERE active = 0"),
            Statement("SELECT COUNT(*) AS n FROM team_aliases"),
        ]
        results = self._db.batch(statements)
        names = ("competitions", "teams_active", "teams_history_only", "aliases")
        return {name: int(rows[0]["n"]) for name, rows in zip(names, results, strict=True)}

    def team_home_comps(self, team_ids: Sequence[int]) -> dict[int, str | None]:
        """Home competition per team id (chunked IN lists, bound parameters)."""
        out: dict[int, str | None] = {}
        ids = list(team_ids)
        for start in range(0, len(ids), 90):
            chunk = ids[start : start + 90]
            marks = ", ".join("?" for _ in chunk)
            rows = self._db.query(
                f"SELECT team_id, home_comp FROM teams WHERE team_id IN ({marks})",  # noqa: S608
                chunk,
            )
            for r in rows:
                comp = r["home_comp"]
                out[int(r["team_id"])] = None if comp is None else str(comp)
        return out
