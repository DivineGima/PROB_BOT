"""Loads and validates the reference files: canonical teams, history-only clubs and alias files.

Pure functions over JSON files; nothing here touches the network or the database. Every problem
raises ``DataError`` naming the file and the offending value (never a guess).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from footy.aliases.normalise import normalise
from footy.config import COMPETITIONS, DATA_DIR
from footy.errors import DataError

ALIAS_SOURCES = ("fd_org", "screener")
_COMP_CODES = {c.comp_code for c in COMPETITIONS}


@dataclass(frozen=True)
class TeamSeed:
    canonical_name: str
    home_comp: str | None
    is_ucl_only: bool
    active: bool


@dataclass(frozen=True)
class ReferenceData:
    teams: tuple[TeamSeed, ...]
    # source -> alias_norm -> canonical_name
    aliases: dict[str, dict[str, str]]

    def active_count(self) -> int:
        return sum(1 for t in self.teams if t.active)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise DataError(f"cannot read {path.name}: {type(exc).__name__}") from None
    except ValueError:
        raise DataError(f"{path.name} is not valid JSON") from None
    if not isinstance(loaded, dict):
        raise DataError(f"{path.name} must contain a JSON object")
    return loaded


def _name(value: object, where: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 120:
        raise DataError(f"{where}: expected a non-empty team name, got {value!r}")
    if not normalise(value):
        raise DataError(f"{where}: {value!r} has no usable letters or digits")
    return value.strip()


def _canonical(path: Path) -> list[TeamSeed]:
    data = _read_json(path)
    teams: list[TeamSeed] = []
    competitions = data.get("competitions")
    if not isinstance(competitions, list) or not competitions:
        raise DataError("canonical_teams.json: 'competitions' must be a non-empty list")
    for entry in competitions:
        code = entry.get("code") if isinstance(entry, dict) else None
        if code not in _COMP_CODES:
            raise DataError(f"canonical_teams.json: unknown competition code {code!r}")
        names = entry.get("teams")
        if not isinstance(names, list) or not names:
            raise DataError(f"canonical_teams.json: {code} has no teams")
        for n in names:
            teams.append(TeamSeed(_name(n, f"canonical_teams.json {code}"), code, False, True))
    ucl_only = data.get("ucl_only")
    if not isinstance(ucl_only, list):
        raise DataError("canonical_teams.json: 'ucl_only' must be a list")
    for n in ucl_only:
        teams.append(TeamSeed(_name(n, "canonical_teams.json ucl_only"), None, True, True))
    return teams


def _historical(path: Path) -> list[TeamSeed]:
    data = _read_json(path)
    clubs = data.get("clubs")
    if not isinstance(clubs, list):
        raise DataError("historical_teams.json: 'clubs' must be a list")
    teams: list[TeamSeed] = []
    for club in clubs:
        if not isinstance(club, dict):
            raise DataError("historical_teams.json: every club must be an object")
        name = _name(club.get("canonical_name"), "historical_teams.json")
        comp = club.get("last_competition")
        if comp is not None and comp not in _COMP_CODES:
            raise DataError(f"historical_teams.json: {name}: unknown competition {comp!r}")
        ucl_only = bool(club.get("is_ucl_only", 1 if comp is None else 0))
        teams.append(TeamSeed(name, comp, ucl_only, False))
    return teams


def _alias_file(path: Path, source: str, known: set[str]) -> dict[str, list[str]]:
    if not path.exists():
        return {}
    data = _read_json(path)
    if data.get("source") != source:
        raise DataError(f"{path.name}: 'source' must be {source!r}")
    mapping = data.get("aliases")
    if not isinstance(mapping, dict):
        raise DataError(f"{path.name}: 'aliases' must be an object")
    out: dict[str, list[str]] = {}
    for canonical, spellings in mapping.items():
        if canonical not in known:
            raise DataError(f"{path.name}: {canonical!r} is not a known canonical team")
        if not isinstance(spellings, list):
            raise DataError(f"{path.name}: aliases of {canonical!r} must be a list")
        out[canonical] = [_name(s, f"{path.name} {canonical}") for s in spellings]
    return out


def load_reference(data_dir: Path | None = None) -> ReferenceData:
    root = DATA_DIR if data_dir is None else data_dir
    teams = _canonical(root / "canonical_teams.json") + _historical(root / "historical_teams.json")

    seen: dict[str, str] = {}
    for team in teams:
        key = normalise(team.canonical_name)
        if key in seen:
            raise DataError(
                f"teams {seen[key]!r} and {team.canonical_name!r} are the same team or normalise "
                "to the same spelling"
            )
        seen[key] = team.canonical_name
    known = {t.canonical_name for t in teams}

    aliases: dict[str, dict[str, str]] = {}
    for source in ALIAS_SOURCES:
        table: dict[str, str] = {normalise(t.canonical_name): t.canonical_name for t in teams}
        extra = _alias_file(root / "aliases" / f"{source}.json", source, known)
        for canonical, spellings in extra.items():
            for spelling in spellings:
                key = normalise(spelling)
                owner = table.get(key)
                if owner is not None and owner != canonical:
                    raise DataError(
                        f"{source}: alias {spelling!r} maps to both {owner!r} and {canonical!r}"
                    )
                table[key] = canonical
        aliases[source] = table
    return ReferenceData(tuple(teams), aliases)
