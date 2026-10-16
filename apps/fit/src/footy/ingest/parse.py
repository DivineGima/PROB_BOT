"""Parsing and validation of football-data.org v4 match payloads (architecture section 6.8).

Source data is untrusted (S9): every field is type-checked and a bad record is counted and skipped,
never repaired or guessed. Only the fields listed in section 6.8 are read.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

_UTC_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")
MAX_REASONABLE_SCORE = 1000  # parse-level sanity only; the 0..20 rule is applied in reconcile


@dataclass(frozen=True)
class Score:
    home: int | None
    away: int | None


@dataclass(frozen=True)
class RawMatch:
    fd_match_id: int
    comp_code: str
    season: str
    kickoff_utc: str  # YYYY-MM-DDTHH:MM:SSZ
    status: str
    home_name: str
    away_name: str
    duration: str | None
    full_time: Score
    regular_time: Score | None


@dataclass
class ParseReport:
    matches: list[RawMatch] = field(default_factory=list)
    skipped: dict[str, int] = field(default_factory=dict)

    def skip(self, reason: str) -> None:
        self.skipped[reason] = self.skipped.get(reason, 0) + 1


def season_label(start_year: int) -> str:
    return f"{start_year}-{(start_year + 1) % 100:02d}"


def season_for_date(day: str) -> str:
    """Fallback when the payload carries no season block: seasons run August to May."""
    year, month = int(day[:4]), int(day[5:7])
    return season_label(year if month >= 7 else year - 1)


def _score_value(value: object) -> int | bool | None:
    """Return the int, None for null, or False when the value is not a usable score."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        return False
    if value < 0 or value > MAX_REASONABLE_SCORE:
        return False
    return value


def _score(block: object) -> Score | bool | None:
    """None when the block is absent or null; False when it is malformed."""
    if block is None:
        return None
    if not isinstance(block, dict):
        return False
    home, away = _score_value(block.get("home")), _score_value(block.get("away"))
    if isinstance(home, bool) or isinstance(away, bool):
        return False
    return Score(home, away)


def _season(raw: dict[str, Any], kickoff: str) -> str:
    block = raw.get("season")
    if isinstance(block, dict):
        start = block.get("startDate")
        if isinstance(start, str) and _DATE.match(start):
            return season_label(int(start[:4]))
    return season_for_date(kickoff)


def parse_matches(payload: object, comp_code: str) -> ParseReport:
    """Turn a ``/competitions/{code}/matches`` payload into validated ``RawMatch`` objects."""
    report = ParseReport()
    if not isinstance(payload, dict) or not isinstance(payload.get("matches"), list):
        report.skip("payload_shape")
        return report
    for raw in payload["matches"]:
        if not isinstance(raw, dict):
            report.skip("record_shape")
            continue
        match_id = raw.get("id")
        if isinstance(match_id, bool) or not isinstance(match_id, int) or match_id <= 0:
            report.skip("bad_id")
            continue
        kickoff = raw.get("utcDate")
        if not isinstance(kickoff, str) or not _UTC_DATE.match(kickoff):
            report.skip("bad_date")
            continue
        try:
            datetime.strptime(kickoff, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        except ValueError:
            report.skip("bad_date")
            continue
        status = raw.get("status")
        if not isinstance(status, str) or not status:
            report.skip("bad_status")
            continue
        home = (
            (raw.get("homeTeam") or {}).get("name")
            if isinstance(raw.get("homeTeam"), dict)
            else None
        )
        away = (
            (raw.get("awayTeam") or {}).get("name")
            if isinstance(raw.get("awayTeam"), dict)
            else None
        )
        if home is None or away is None:
            report.skip("team_not_decided")  # knockout fixtures before the draw
            continue
        if (
            not isinstance(home, str)
            or not isinstance(away, str)
            or not home.strip()
            or not away.strip()
        ):
            report.skip("bad_team")
            continue
        score_block = raw.get("score")
        if score_block is None:
            score_block = {}
        if not isinstance(score_block, dict):
            report.skip("bad_score")
            continue
        full = _score(score_block.get("fullTime"))
        regular = _score(score_block.get("regularTime"))
        if full is False or regular is False:
            report.skip("bad_score")
            continue
        duration = score_block.get("duration")
        if duration is not None and not isinstance(duration, str):
            report.skip("bad_score")
            continue
        report.matches.append(
            RawMatch(
                fd_match_id=match_id,
                comp_code=comp_code,
                season=_season(raw, kickoff),
                kickoff_utc=kickoff,
                status=status,
                home_name=home.strip(),
                away_name=away.strip(),
                duration=duration,
                full_time=full if isinstance(full, Score) else Score(None, None),
                regular_time=regular if isinstance(regular, Score) else None,
            )
        )
    return report


def parse_team_names(payload: object) -> list[str] | None:
    """Names from a ``/competitions/{code}/teams`` payload; None when the shape is wrong."""
    if not isinstance(payload, dict) or not isinstance(payload.get("teams"), list):
        return None
    names: list[str] = []
    for team in payload["teams"]:
        name = team.get("name") if isinstance(team, dict) else None
        if isinstance(name, str) and name.strip():
            names.append(name.strip())
    return names
