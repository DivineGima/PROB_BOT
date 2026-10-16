"""Repositories on SQLite (the engine D1 is built on): idempotency, keys, dedupe (Stage 2)."""

from __future__ import annotations

import sqlite3

import pytest

from footy.aliases import load_reference
from footy.config import COMPETITIONS
from footy.ingest.fd_org import FetchRecord
from footy.ingest.pipeline import seed_reference
from footy.reconcile.matches import MatchRow
from footy.repo.d1_client import MemoryProgress, execute_resumable
from footy.repo.matches import MatchesRepo
from footy.repo.ops import OpsRepo
from footy.repo.reference import ReferenceRepo
from tests.helpers import SqliteD1


@pytest.fixture
def db() -> SqliteD1:
    return SqliteD1()


@pytest.fixture
def seeded(db: SqliteD1) -> SqliteD1:
    seed_reference(db, load_reference(), MemoryProgress())
    return db


def test_seed_creates_the_expected_counts_and_is_idempotent(db: SqliteD1) -> None:
    ref = load_reference()
    first = seed_reference(db, ref, MemoryProgress())
    assert first["competitions"] == 10
    assert first["teams_active"] == 179
    assert first["teams_history_only"] == len(ref.teams) - 179
    assert first["aliases"] == sum(len(t) for t in ref.aliases.values())
    ids_before = ReferenceRepo(db).team_ids()
    second = seed_reference(db, ref, MemoryProgress())
    assert second == first
    assert ReferenceRepo(db).team_ids() == ids_before  # team ids are stable across re-seeding


def test_competitions_match_section_5_2(seeded: SqliteD1) -> None:
    rows = {r["comp_code"]: r for r in seeded.rows("SELECT * FROM competitions")}
    assert set(rows) == {c.comp_code for c in COMPETITIONS}
    assert rows["SPL"]["fd_code"] is None and rows["UCL"]["uk_div"] is None
    assert rows["UCL"]["has_shots"] == 0 and rows["EPL"]["has_shots"] == 1
    assert rows["CHA"]["fd_code"] == "ELC"


def test_teams_home_comp_and_ucl_only_flags(seeded: SqliteD1) -> None:
    assert seeded.scalar("SELECT home_comp FROM teams WHERE canonical_name = 'Arsenal'") == "EPL"
    assert seeded.scalar("SELECT is_ucl_only FROM teams WHERE canonical_name = 'Viking'") == 1
    assert seeded.scalar("SELECT home_comp FROM teams WHERE canonical_name = 'Viking'") is None
    assert seeded.scalar("SELECT active FROM teams WHERE canonical_name = 'Luton Town'") == 0
    assert seeded.scalar("SELECT COUNT(*) FROM teams WHERE is_ucl_only = 1 AND active = 1") == 11


def test_alias_table_resolves_through_the_database(seeded: SqliteD1) -> None:
    repo = ReferenceRepo(seeded)
    table = repo.alias_table("fd_org")
    ids = repo.team_ids()
    assert table["brighton hove albion"] == ids["Brighton"]
    assert repo.alias_table("manual") == {}
    assert repo.team_names()[ids["Brighton"]] == "Brighton"
    comps = repo.team_home_comps([ids["Brighton"], ids["Viking"], 999999])
    assert comps == {ids["Brighton"]: "EPL", ids["Viking"]: None}
    many = repo.team_home_comps(list(ids.values()))  # more than one IN-list chunk
    assert len(many) == len(ids)


def test_alias_unique_key_and_source_check(seeded: SqliteD1) -> None:
    team = seeded.scalar("SELECT team_id FROM teams WHERE canonical_name = 'Arsenal'")
    with pytest.raises(sqlite3.IntegrityError):
        seeded.conn.execute(
            "INSERT INTO team_aliases (source, alias_norm, team_id) "
            "VALUES ('fd_org', 'arsenal', ?)",
            (team,),
        )
    with pytest.raises(sqlite3.IntegrityError):
        seeded.conn.execute(
            "INSERT INTO team_aliases (source, alias_norm, team_id) VALUES ('bogus', 'x', ?)",
            (team,),
        )


def _row(fd_id: int, home: int, away: int, date: str = "2025-10-18", **kw: object) -> MatchRow:
    base: dict[str, object] = {
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
    return MatchRow(**base)  # type: ignore[arg-type]


def test_match_upsert_is_idempotent_and_updates_in_place(seeded: SqliteD1) -> None:
    ids = ReferenceRepo(seeded).team_ids()
    a, b, c = ids["Arsenal"], ids["Chelsea"], ids["Liverpool"]
    rows = [_row(1, a, b), _row(2, b, c, "2025-10-19"), _row(3, c, a, "2025-10-20")]
    statements = MatchesRepo.upsert_statements(rows, "2026-10-17T00:00:00Z")
    for _ in range(2):
        execute_resumable(seeded, "t", statements, MemoryProgress())
    assert seeded.scalar("SELECT COUNT(*) FROM matches") == 3

    changed = _row(1, a, b, goals_home=3, goals_away=3)
    execute_resumable(
        seeded,
        "t2",
        MatchesRepo.upsert_statements([changed], "2026-10-18T00:00:00Z"),
        MemoryProgress(),
    )
    row = seeded.rows(
        "SELECT goals_home, goals_away, updated_at FROM matches WHERE fd_match_id = 1"
    )[0]
    assert (row["goals_home"], row["goals_away"], row["updated_at"]) == (
        3,
        3,
        "2026-10-18T00:00:00Z",
    )
    assert seeded.scalar("SELECT COUNT(*) FROM matches") == 3


def test_match_table_enforces_its_checks(seeded: SqliteD1) -> None:
    ids = ReferenceRepo(seeded).team_ids()
    a, b = ids["Arsenal"], ids["Chelsea"]
    for bad in (
        _row(1, a, a),  # a team cannot play itself
        _row(2, a, b, goals_home=21),
        _row(3, a, b, status="PAUSED"),
        _row(4, a, b, result_basis="guess"),
        _row(5, a, 999999),  # unknown team (foreign key)
        _row(6, a, b, comp_code="XXX"),
    ):
        with pytest.raises(Exception, match="sql error"):
            seeded.batch(MatchesRepo.upsert_statements([bad], "t"))
    assert seeded.scalar("SELECT COUNT(*) FROM matches") == 0
    execute_resumable(
        seeded, "ok", MatchesRepo.upsert_statements([_row(7, a, b)], "t"), MemoryProgress()
    )
    with pytest.raises(Exception, match="sql error"):  # same fixture under a different source id
        seeded.batch(MatchesRepo.upsert_statements([_row(8, a, b)], "t"))


def test_load_existing_freshness_and_counts(seeded: SqliteD1) -> None:
    ids = ReferenceRepo(seeded).team_ids()
    a, b, c = ids["Arsenal"], ids["Chelsea"], ids["Liverpool"]
    rows = [
        _row(1, a, b, "2025-10-18"),
        _row(2, b, c, "2025-10-25", result_basis="unverified", goals_home=None, goals_away=None),
        _row(
            3,
            c,
            a,
            "2025-11-01",
            status="SCHEDULED",
            goals_home=None,
            goals_away=None,
            result_basis=None,
        ),
        _row(4, a, c, "2025-09-01", comp_code="UCL", season="2025-26"),
    ]
    seeded.batch(MatchesRepo.upsert_statements(rows, "t"))
    repo = MatchesRepo(seeded)
    existing = repo.load_existing([("EPL", "2025-26"), ("EPL", "2025-26"), ("UCL", "2025-26")])
    assert len(existing) == 4
    assert {m.fd_match_id for m in existing} == {1, 2, 3, 4}
    assert repo.load_existing([("EPL", "1999-00")]) == []
    assert repo.freshness() == {"EPL": "2025-10-18", "UCL": "2025-09-01"}
    counts = repo.counts_by_competition()
    assert counts["EPL"] == {"total": 3, "verified": 1, "unverified": 1}
    assert repo.team_match_counts([a, b, c]) == {a: 2, b: 1, c: 1}
    assert repo.team_match_counts([]) == {}


def test_job_runs_lifecycle(db: SqliteD1) -> None:
    ops = OpsRepo(db)
    job = ops.start_job("ingest", "2026-10-17T01:17:00Z", "abc123")
    other = ops.start_job("ingest", "2026-10-17T01:18:00Z", None)
    assert job != other
    ops.finish_job(job, "2026-10-17T01:19:00Z", "ok", {"rows": 3})
    row = db.rows("SELECT * FROM job_runs WHERE job_id = ?", (job,))[0]
    assert (row["status"], row["git_sha"], row["finished_at"]) == (
        "ok",
        "abc123",
        "2026-10-17T01:19:00Z",
    )
    assert '"rows": 3' in row["summary_json"]
    assert db.scalar("SELECT status FROM job_runs WHERE job_id = ?", (other,)) == "running"


def test_events_dedupe_within_24_hours_only(db: SqliteD1) -> None:
    ops = OpsRepo(db)
    key = "unmapped:fd_org:foo"
    assert ops.record_event(
        "2026-10-17T01:00:00Z", "warn", "fd_org", "unmapped_team", {"n": 1}, key
    )
    assert not ops.record_event(
        "2026-10-17T20:00:00Z", "warn", "fd_org", "unmapped_team", {"n": 2}, key
    )
    assert ops.record_event(
        "2026-10-18T01:00:01Z", "warn", "fd_org", "unmapped_team", {"n": 3}, key
    )
    assert ops.record_event("2026-10-18T01:00:01Z", "warn", "fd_org", "unmapped_team", {}, "other")
    assert ops.record_event("2026-10-18T01:00:01Z", "info", "fd_org", "note", {})
    assert ops.record_event(
        "2026-10-18T01:00:02Z", "info", "fd_org", "note", {}
    )  # no key: never deduped
    assert ops.count_events("unmapped_team") == 3
    assert ops.count_events("note") == 2


def test_fetch_log_rows(db: SqliteD1) -> None:
    records = [
        FetchRecord(
            "/competitions/PL/matches?season=2025",
            "2026-10-17T01:17:00Z",
            200,
            True,
            "ab" * 32,
            380,
            1000,
        ),
        FetchRecord(
            "/competitions/PL/matches?season=2023",
            "2026-10-17T01:17:07Z",
            403,
            False,
            None,
            None,
            None,
        ),
    ]
    OpsRepo(db).log_fetches("fd_org", records)
    OpsRepo(db).log_fetches("fd_org", [])  # nothing to write is fine
    rows = db.rows("SELECT * FROM source_fetch_log ORDER BY fetch_id")
    assert [(r["http_status"], r["ok"], r["rows"]) for r in rows] == [(200, 1, 380), (403, 0, None)]
    assert all(r["source"] == "fd_org" for r in rows)
