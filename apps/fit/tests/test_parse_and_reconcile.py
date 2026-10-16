"""Parsing of football-data.org payloads and the reconcile rules (Stage 2 step 5, ADR-010)."""

from __future__ import annotations

from typing import Any

import pytest

from footy.ingest.parse import parse_matches, parse_team_names, season_for_date, season_label
from footy.reconcile.matches import (
    ExistingMatch,
    MatchRow,
    plan_writes,
    status_move_allowed,
    to_row,
)
from tests.helpers import fd_match


def one(raw: dict[str, Any]) -> Any:
    report = parse_matches({"matches": [raw]}, "EPL")
    assert len(report.matches) == 1, report.skipped
    return report.matches[0]


# -- parsing --------------------------------------------------------------------------------------


def test_parse_valid_match() -> None:
    m = one(fd_match(7, "Arsenal FC", "Chelsea FC", "2025-10-18T14:00:00Z", full=(2, 1)))
    assert (m.fd_match_id, m.season, m.kickoff_utc) == (7, "2025-26", "2025-10-18T14:00:00Z")
    assert (m.full_time.home, m.full_time.away, m.regular_time) == (2, 1, None)


def test_season_labels() -> None:
    assert season_label(2025) == "2025-26"
    assert season_label(2099) == "2099-00"
    assert season_for_date("2026-08-01") == "2026-27"
    assert season_for_date("2027-05-20") == "2026-27"
    assert season_for_date("2026-06-30") == "2025-26"
    m = one(fd_match(1, "A", "B", "2025-11-01T12:00:00Z", season_start=None))
    assert m.season == "2025-26"


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ({"id": "x"}, "bad_id"),
        ({"id": 0}, "bad_id"),
        ({"id": True}, "bad_id"),
        ({"utcDate": "2025-10-18"}, "bad_date"),
        ({"utcDate": "2025-13-45T99:00:00Z"}, "bad_date"),
        ({"utcDate": None}, "bad_date"),
        ({"status": None}, "bad_status"),
        ({"status": ""}, "bad_status"),
        ({"homeTeam": {"name": None}}, "team_not_decided"),
        ({"awayTeam": None}, "team_not_decided"),
        ({"homeTeam": {"name": ""}}, "bad_team"),
        ({"homeTeam": {"name": 5}}, "bad_team"),
        ({"score": "bad"}, "bad_score"),
        ({"score": {"fullTime": {"home": -1, "away": 0}}}, "bad_score"),
        ({"score": {"fullTime": {"home": 1.5, "away": 0}}}, "bad_score"),
        ({"score": {"fullTime": {"home": "2", "away": 0}}}, "bad_score"),
        ({"score": {"fullTime": {"home": True, "away": 0}}}, "bad_score"),
        ({"score": {"fullTime": "x"}}, "bad_score"),
        ({"score": {"duration": 3, "fullTime": {"home": 1, "away": 0}}}, "bad_score"),
    ],
)
def test_parse_skips_and_counts_bad_records(mutation: dict[str, Any], reason: str) -> None:
    raw = fd_match(1, "Arsenal FC", "Chelsea FC")
    raw.update(mutation)
    report = parse_matches({"matches": [raw, fd_match(2, "Arsenal FC", "Chelsea FC")]}, "EPL")
    assert report.skipped == {reason: 1}
    assert [m.fd_match_id for m in report.matches] == [2]


def test_parse_handles_missing_score_and_bad_shapes() -> None:
    raw = fd_match(1, "Arsenal FC", "Chelsea FC", status="SCHEDULED")
    del raw["score"]
    m = one(raw)
    assert (m.full_time.home, m.full_time.away) == (None, None)
    assert parse_matches(None, "EPL").skipped == {"payload_shape": 1}
    assert parse_matches({"matches": "x"}, "EPL").skipped == {"payload_shape": 1}
    assert parse_matches({"matches": [1, "x", None]}, "EPL").skipped == {"record_shape": 3}
    assert parse_matches({"matches": []}, "EPL").matches == []


def test_parse_team_names() -> None:
    assert parse_team_names({"teams": [{"name": "A"}, {"name": " B "}, {"x": 1}, 3]}) == ["A", "B"]
    assert parse_team_names({"teams": "no"}) is None
    assert parse_team_names([]) is None


# -- to_row: the 90-minute rule -------------------------------------------------------------------


def row_for(**kwargs: Any) -> MatchRow:
    raw = one(fd_match(10, "Arsenal FC", "Chelsea FC", **kwargs))
    row, _ = to_row(raw, 1, 2)
    assert row is not None
    return row


def test_regular_duration_uses_full_time_as_ft_90() -> None:
    row = row_for(duration="REGULAR", full=(3, 1))
    assert (row.goals_home, row.goals_away, row.result_basis) == (3, 1, "ft_90")


def test_regular_time_preferred_and_labelled_regular() -> None:
    row = row_for(duration="EXTRA_TIME", full=(3, 2), regular=(1, 1))
    assert (row.goals_home, row.goals_away, row.result_basis) == (1, 1, "regular")
    row = row_for(duration="PENALTY_SHOOTOUT", full=(5, 4), regular=(0, 0))
    assert (row.goals_home, row.goals_away, row.result_basis) == (0, 0, "regular")
    row = row_for(duration="REGULAR", full=(2, 0), regular=(2, 0))
    assert row.result_basis == "regular"


@pytest.mark.parametrize("duration", ["EXTRA_TIME", "PENALTY_SHOOTOUT", None])
def test_extra_time_without_regular_time_is_unverified_with_null_goals(
    duration: str | None,
) -> None:
    row = row_for(duration=duration, full=(3, 2))
    assert (row.goals_home, row.goals_away, row.result_basis) == (None, None, "unverified")


def test_missing_scores_are_unverified() -> None:
    row = row_for(duration="REGULAR", full=(None, None))
    assert row.result_basis == "unverified" and row.goals_home is None
    row = row_for(duration="REGULAR", full=(2, None))
    assert row.result_basis == "unverified"


def test_goals_out_of_range_are_unverified_and_raise_an_anomaly() -> None:
    raw = one(fd_match(10, "Arsenal FC", "Chelsea FC", duration="REGULAR", full=(21, 0)))
    row, anomalies = to_row(raw, 1, 2)
    assert row is not None and row.result_basis == "unverified" and row.goals_home is None
    assert [a.kind for a in anomalies] == ["goals_out_of_range"]
    ok = row_for(duration="REGULAR", full=(20, 0))
    assert ok.goals_home == 20


def test_unfinished_awarded_and_unknown_statuses() -> None:
    sched = row_for(status="SCHEDULED", duration=None, full=(None, None))
    assert (sched.status, sched.goals_home, sched.result_basis) == ("SCHEDULED", None, None)
    live = row_for(status="PAUSED", duration="REGULAR", full=(1, 0))
    assert (live.status, live.goals_home, live.result_basis) == ("IN_PLAY", None, None)
    awarded = row_for(status="AWARDED", duration="REGULAR", full=(3, 0))
    assert (awarded.goals_home, awarded.result_basis) == (None, "unverified")
    raw = one(fd_match(11, "Arsenal FC", "Chelsea FC", status="WEIRD"))
    row, anomalies = to_row(raw, 1, 2)
    assert row is None and anomalies[0].kind == "unknown_status"
    same = to_row(one(fd_match(12, "A", "B")), 5, 5)
    assert same[0] is None and same[1][0].kind == "same_team"


def test_match_date_is_the_utc_date_of_kickoff() -> None:
    row = row_for(utc="2025-10-18T23:30:00Z")
    assert (row.match_date, row.kickoff_utc) == ("2025-10-18", "2025-10-18T23:30:00Z")


# -- status transitions ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("old", "new", "allowed"),
    [
        ("SCHEDULED", "TIMED", True),
        ("TIMED", "IN_PLAY", True),
        ("SCHEDULED", "POSTPONED", True),
        ("POSTPONED", "SCHEDULED", True),
        ("POSTPONED", "FINISHED", True),
        ("IN_PLAY", "FINISHED", True),
        ("IN_PLAY", "SUSPENDED", True),
        ("IN_PLAY", "SCHEDULED", False),
        ("FINISHED", "IN_PLAY", False),
        ("FINISHED", "SCHEDULED", False),
        ("FINISHED", "FINISHED", True),
        ("FINISHED", "POSTPONED", False),
        ("CANCELLED", "SCHEDULED", False),
        ("AWARDED", "FINISHED", False),
        ("SUSPENDED", "FINISHED", True),
    ],
)
def test_status_transitions_are_forward_only(old: str, new: str, allowed: bool) -> None:
    assert status_move_allowed(old, new) is allowed


# -- plan_writes ----------------------------------------------------------------------------------


def mrow(fd_id: int, date: str = "2025-10-18", home: int = 1, away: int = 2, **kw: Any) -> MatchRow:
    base: dict[str, Any] = {
        "comp_code": "EPL",
        "season": "2025-26",
        "match_date": date,
        "kickoff_utc": f"{date}T14:00:00Z",
        "home_team_id": home,
        "away_team_id": away,
        "status": "FINISHED",
        "goals_home": 2,
        "goals_away": 1,
        "result_basis": "ft_90",
        "fd_match_id": fd_id,
    }
    base.update(kw)
    return MatchRow(**base)


def stored(row: MatchRow, match_id: int = 1, fd_id: int | None = None) -> ExistingMatch:
    return ExistingMatch(
        match_id=match_id,
        fd_match_id=row.fd_match_id if fd_id is None else fd_id,
        comp_code=row.comp_code,
        season=row.season,
        match_date=row.match_date,
        kickoff_utc=row.kickoff_utc,
        home_team_id=row.home_team_id,
        away_team_id=row.away_team_id,
        status=row.status,
        goals_home=row.goals_home,
        goals_away=row.goals_away,
        result_basis=row.result_basis,
    )


def test_plan_insert_unchanged_and_update() -> None:
    old = mrow(1, status="SCHEDULED", goals_home=None, goals_away=None, result_basis=None)
    plan = plan_writes(
        [mrow(1), mrow(2, home=3, away=4), mrow(3, date="2025-10-19", home=5, away=6)],
        [stored(old), stored(mrow(3, date="2025-10-19", home=5, away=6), 3)],
    )
    assert (plan.inserted, plan.updated, plan.unchanged) == (1, 1, 1)
    assert sorted(r.fd_match_id for r in plan.to_write) == [1, 2]
    assert plan.disagreements == [] and plan.anomalies == []


def test_plan_blocks_status_regression_and_result_downgrade() -> None:
    finished = mrow(1)
    plan = plan_writes(
        [mrow(1, status="IN_PLAY", goals_home=None, goals_away=None, result_basis=None)],
        [stored(finished)],
    )
    assert plan.to_write == [] and [a.kind for a in plan.anomalies] == ["status_regression"]

    downgraded = mrow(1, goals_home=None, goals_away=None, result_basis="unverified")
    plan = plan_writes([downgraded], [stored(finished)])
    assert plan.to_write == [] and [a.kind for a in plan.anomalies] == ["result_downgrade"]


def test_plan_reports_changed_verified_results_as_disagreements() -> None:
    plan = plan_writes([mrow(1, goals_home=0, goals_away=0)], [stored(mrow(1))])
    assert plan.to_write == [] and len(plan.disagreements) == 1


def test_plan_allows_unverified_to_become_verified_without_a_disagreement() -> None:
    old = mrow(1, goals_home=None, goals_away=None, result_basis="unverified")
    plan = plan_writes([mrow(1, result_basis="regular")], [stored(old)])
    assert plan.disagreements == [] and plan.updated == 1


def test_plan_handles_reschedule_and_natural_key_clashes() -> None:
    sched = mrow(1, status="SCHEDULED", goals_home=None, goals_away=None, result_basis=None)
    moved = mrow(
        1,
        date="2025-11-02",
        status="SCHEDULED",
        goals_home=None,
        goals_away=None,
        result_basis=None,
    )
    plan = plan_writes([moved], [stored(sched)])
    assert plan.updated == 1  # a postponed match moves to a new date

    other = stored(mrow(9, date="2025-11-02"), 9)
    plan = plan_writes([moved], [stored(sched), other])
    assert plan.to_write == [] and [a.kind for a in plan.anomalies] == ["natural_key_conflict"]

    plan = plan_writes([mrow(5)], [stored(mrow(9), 9)])
    assert plan.to_write == [] and [a.kind for a in plan.anomalies] == ["natural_key_conflict"]


def test_plan_flags_two_source_ids_for_one_fixture() -> None:
    plan = plan_writes([mrow(1), mrow(2)], [])
    assert [r.fd_match_id for r in plan.to_write] == [1]
    assert [a.kind for a in plan.anomalies] == ["duplicate_fixture"]
