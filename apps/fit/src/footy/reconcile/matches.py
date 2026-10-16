"""Turns validated source matches into ``matches`` rows and decides what may be written
(architecture sections 5.3, 5.7 and 8.5, ADR-010).

Rules implemented here:

* goals are the 90-minute score: ``score.regularTime`` -> ``result_basis='regular'``; else
  ``score.fullTime`` when ``score.duration == 'REGULAR'`` -> ``'ft_90'``; any other finished
  match is ``'unverified'`` with NULL goals (excluded from training and scoring);
* goals must be integers 0..20, otherwise the result is ``unverified`` and an anomaly is raised;
* status only moves forward (a final state never reverts);
* a stored verified result that the source now reports differently is a *disagreement*; more than
  ``MAX_DISAGREEMENTS`` in one run means a parsing or mapping bug and fails the run (exit code 2);
* a row whose natural key is already used by another source match id is a conflict and is skipped.

Pure functions: no I/O, no SQL.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from footy.ingest.parse import RawMatch

STATUS_MAP: dict[str, str] = {
    "SCHEDULED": "SCHEDULED",
    "TIMED": "TIMED",
    "IN_PLAY": "IN_PLAY",
    "PAUSED": "IN_PLAY",
    "LIVE": "IN_PLAY",
    "FINISHED": "FINISHED",
    "POSTPONED": "POSTPONED",
    "CANCELLED": "CANCELLED",
    "SUSPENDED": "SUSPENDED",
    "AWARDED": "AWARDED",
}
FINAL_STATES = frozenset({"FINISHED", "AWARDED", "CANCELLED"})
PRE_PLAY_STATES = frozenset({"SCHEDULED", "TIMED"})
MAX_GOALS = 20

NaturalKey = tuple[str, str, str, int, int]  # comp_code, season, match_date, home_id, away_id


@dataclass(frozen=True)
class MatchRow:
    comp_code: str
    season: str
    match_date: str
    kickoff_utc: str
    home_team_id: int
    away_team_id: int
    status: str
    goals_home: int | None
    goals_away: int | None
    result_basis: str | None
    fd_match_id: int
    goals_source: str = "fd_org"

    @property
    def natural_key(self) -> NaturalKey:
        return (self.comp_code, self.season, self.match_date, self.home_team_id, self.away_team_id)


@dataclass(frozen=True)
class ExistingMatch:
    match_id: int
    fd_match_id: int | None
    comp_code: str
    season: str
    match_date: str
    kickoff_utc: str | None
    home_team_id: int
    away_team_id: int
    status: str
    goals_home: int | None
    goals_away: int | None
    result_basis: str | None

    @property
    def natural_key(self) -> NaturalKey:
        return (self.comp_code, self.season, self.match_date, self.home_team_id, self.away_team_id)


@dataclass(frozen=True)
class Anomaly:
    kind: str
    detail: dict[str, object]


def _goals(raw: RawMatch, anomalies: list[Anomaly]) -> tuple[int | None, int | None, str | None]:
    regular = raw.regular_time
    if regular is not None and regular.home is not None and regular.away is not None:
        home, away, basis = regular.home, regular.away, "regular"
    elif (
        raw.duration == "REGULAR"
        and raw.full_time.home is not None
        and raw.full_time.away is not None
    ):
        home, away, basis = raw.full_time.home, raw.full_time.away, "ft_90"
    else:
        return None, None, "unverified"
    if not (0 <= home <= MAX_GOALS and 0 <= away <= MAX_GOALS):
        anomalies.append(
            Anomaly("goals_out_of_range", {"fd_match_id": raw.fd_match_id, "comp": raw.comp_code})
        )
        return None, None, "unverified"
    return home, away, basis


def to_row(
    raw: RawMatch, home_team_id: int, away_team_id: int
) -> tuple[MatchRow | None, list[Anomaly]]:
    """Build the row for one source match; ``None`` when it cannot be stored."""
    anomalies: list[Anomaly] = []
    status = STATUS_MAP.get(raw.status)
    if status is None:
        return None, [
            Anomaly("unknown_status", {"fd_match_id": raw.fd_match_id, "status": raw.status})
        ]
    if home_team_id == away_team_id:
        return None, [Anomaly("same_team", {"fd_match_id": raw.fd_match_id})]
    goals_home: int | None = None
    goals_away: int | None = None
    basis: str | None = None
    if status == "FINISHED":
        goals_home, goals_away, basis = _goals(raw, anomalies)
    elif status == "AWARDED":
        # An awarded result is administrative, not a played score: never trained or scored on.
        basis = "unverified"
    return (
        MatchRow(
            comp_code=raw.comp_code,
            season=raw.season,
            match_date=raw.kickoff_utc[:10],
            kickoff_utc=raw.kickoff_utc,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            status=status,
            goals_home=goals_home,
            goals_away=goals_away,
            result_basis=basis,
            fd_match_id=raw.fd_match_id,
        ),
        anomalies,
    )


def status_move_allowed(old: str, new: str) -> bool:
    """Forward-only status transitions (section 8.5)."""
    if old == new:
        return True
    if old in FINAL_STATES:
        return False
    if old == "IN_PLAY":
        return new not in PRE_PLAY_STATES
    return True  # pre-play, POSTPONED and SUSPENDED matches may move to any state


@dataclass
class Plan:
    to_write: list[MatchRow] = field(default_factory=list)
    unchanged: int = 0
    inserted: int = 0
    updated: int = 0
    disagreements: list[tuple[MatchRow, ExistingMatch]] = field(default_factory=list)
    anomalies: list[Anomaly] = field(default_factory=list)


def _same(row: MatchRow, old: ExistingMatch) -> bool:
    return (
        row.match_date == old.match_date
        and row.kickoff_utc == old.kickoff_utc
        and row.status == old.status
        and row.goals_home == old.goals_home
        and row.goals_away == old.goals_away
        and row.result_basis == old.result_basis
        and row.home_team_id == old.home_team_id
        and row.away_team_id == old.away_team_id
        and row.season == old.season
        and row.comp_code == old.comp_code
    )


def plan_writes(rows: Iterable[MatchRow], existing: Iterable[ExistingMatch]) -> Plan:
    """Compare incoming rows with stored rows and decide what to write.

    Disagreements are *not* in ``to_write``: the caller applies them only while the run stays within
    ``MAX_DISAGREEMENTS``.
    """
    plan = Plan()
    by_fd: dict[int, ExistingMatch] = {}
    by_key: dict[NaturalKey, ExistingMatch] = {}
    for stored in existing:
        by_key[stored.natural_key] = stored
        if stored.fd_match_id is not None:
            by_fd[stored.fd_match_id] = stored

    claimed: dict[NaturalKey, int] = {}
    for row in rows:
        other = claimed.get(row.natural_key)
        if other is not None and other != row.fd_match_id:
            plan.anomalies.append(
                Anomaly("duplicate_fixture", {"fd_match_ids": [other, row.fd_match_id]})
            )
            continue
        claimed[row.natural_key] = row.fd_match_id

        old = by_fd.get(row.fd_match_id)
        if old is None:
            clash = by_key.get(row.natural_key)
            if clash is not None:
                plan.anomalies.append(
                    Anomaly(
                        "natural_key_conflict",
                        {"fd_match_id": row.fd_match_id, "stored_fd_match_id": clash.fd_match_id},
                    )
                )
                continue
            plan.to_write.append(row)
            plan.inserted += 1
            continue

        if _same(row, old):
            plan.unchanged += 1
            continue
        if not status_move_allowed(old.status, row.status):
            plan.anomalies.append(
                Anomaly(
                    "status_regression",
                    {"fd_match_id": row.fd_match_id, "from": old.status, "to": row.status},
                )
            )
            continue
        holder = by_key.get(row.natural_key)
        if holder is not None and holder.fd_match_id != row.fd_match_id:
            plan.anomalies.append(Anomaly("natural_key_conflict", {"fd_match_id": row.fd_match_id}))
            continue
        if old.result_basis in ("regular", "ft_90") and row.status == "FINISHED":
            if row.result_basis == "unverified":
                plan.anomalies.append(Anomaly("result_downgrade", {"fd_match_id": row.fd_match_id}))
                continue
            if (row.goals_home, row.goals_away) != (old.goals_home, old.goals_away):
                plan.disagreements.append((row, old))
                continue
        plan.to_write.append(row)
        plan.updated += 1
    return plan


def index_by_key(existing: Iterable[ExistingMatch]) -> Mapping[NaturalKey, ExistingMatch]:
    return {m.natural_key: m for m in existing}
