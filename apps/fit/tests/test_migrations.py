"""Migration tests on plain SQLite (the engine D1 is built on). The same files are applied to
Miniflare's local D1 by the Vitest suite; here they are also applied step by step, which proves
each migration applies on top of the schema left by the one before it."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

MIGRATIONS = Path(__file__).resolve().parents[3] / "db" / "migrations"
STAGE_1_TABLES = {"events", "job_runs", "processed_updates", "uploads"}
STAGE_2_TABLES = {"competitions", "teams", "team_aliases", "matches", "source_fetch_log"}


def migration_files() -> list[Path]:
    return sorted(MIGRATIONS.glob("*.sql"))


def apply(connection: sqlite3.Connection, files: list[Path]) -> None:
    for path in files:
        connection.executescript(path.read_text(encoding="utf-8"))


@pytest.fixture
def db() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def tables(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {r[0] for r in rows}


def test_migration_files_are_sequential_and_named() -> None:
    names = [p.name for p in migration_files()]
    assert names, "no migrations found"
    for index, name in enumerate(names, start=1):
        assert name.startswith(f"{index:04d}_"), f"gap or misnumbering at {name}"


def test_applies_cleanly_to_an_empty_database_and_creates_only_stage_1_and_2_tables(
    db: sqlite3.Connection,
) -> None:
    apply(db, migration_files())
    assert tables(db) >= STAGE_1_TABLES | STAGE_2_TABLES
    # ADR-033: later-stage tables must not exist yet.
    assert not {"predictions", "omissions", "model_runs", "active_run", "model_params"} & tables(db)


def test_applies_step_by_step_on_top_of_the_previous_schema(db: sqlite3.Connection) -> None:
    for path in migration_files():
        apply(db, [path])
    assert tables(db) >= STAGE_1_TABLES | STAGE_2_TABLES


def test_uploads_defaults_to_received_and_checks_status(db: sqlite3.Connection) -> None:
    apply(db, migration_files())
    db.execute("INSERT INTO uploads (update_id, received_at) VALUES (1, 't')")
    assert db.execute("SELECT status FROM uploads").fetchone() == ("received",)
    for status in ("rejected", "processed", "failed"):
        db.execute("UPDATE uploads SET status = ? WHERE update_id = 1", (status,))
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE uploads SET status = 'bogus' WHERE update_id = 1")


def test_unique_keys(db: sqlite3.Connection) -> None:
    apply(db, migration_files())
    db.execute("INSERT INTO uploads (update_id, received_at) VALUES (1, 't')")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO uploads (update_id, received_at) VALUES (1, 't')")
    db.execute("INSERT INTO processed_updates (update_id, received_at) VALUES (5, 't')")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO processed_updates (update_id, received_at) VALUES (5, 't')")
    db.execute("INSERT OR IGNORE INTO processed_updates (update_id, received_at) VALUES (5, 't')")
    assert db.execute("SELECT COUNT(*) FROM processed_updates").fetchone() == (1,)


def test_required_columns_reject_nulls(db: sqlite3.Connection) -> None:
    apply(db, migration_files())
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO events (at, level, source) VALUES ('t', 'info', 's')")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO job_runs (kind, started_at) VALUES ('nightly', 't')")


def test_expected_indexes_exist(db: sqlite3.Connection) -> None:
    apply(db, migration_files())
    rows = db.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
    names = {r[0] for r in rows}
    assert {
        "idx_uploads_status_received",
        "idx_events_at",
        "idx_events_dedupe",
        "idx_job_runs_kind_started",
    } <= names


def test_stage_2_schema_has_the_expected_indexes_and_keys(db: sqlite3.Connection) -> None:
    apply(db, migration_files())
    indexes = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert {
        "idx_matches_home_date",
        "idx_matches_away_date",
        "idx_matches_comp_date",
        "idx_matches_status_date",
        "idx_team_aliases_team",
        "idx_source_fetch_log_source_at",
    } <= indexes
    db.execute("INSERT INTO competitions (comp_code, name) VALUES ('EPL', 'Premier League')")
    with pytest.raises(sqlite3.IntegrityError):  # comp_code is restricted to the ten codes
        db.execute("INSERT INTO competitions (comp_code, name) VALUES ('XXX', 'Nope')")
    db.execute("INSERT INTO teams (canonical_name, home_comp) VALUES ('A', 'EPL'), ('B', 'EPL')")
    with pytest.raises(sqlite3.IntegrityError):  # canonical names are unique
        db.execute("INSERT INTO teams (canonical_name) VALUES ('A')")
    with pytest.raises(sqlite3.IntegrityError):  # foreign key to competitions
        db.execute("INSERT INTO teams (canonical_name, home_comp) VALUES ('C', 'LL')")


def test_matches_rules_in_the_schema(db: sqlite3.Connection) -> None:
    apply(db, migration_files())
    db.execute("INSERT INTO competitions (comp_code, name) VALUES ('EPL', 'Premier League')")
    db.execute("INSERT INTO teams (canonical_name) VALUES ('A'), ('B')")
    insert = (
        "INSERT INTO matches (comp_code, season, match_date, home_team_id, away_team_id, status, "
        "goals_home, goals_away, result_basis, fd_match_id, updated_at) "
        "VALUES ('EPL', '2025-26', '2025-10-18', ?, ?, ?, ?, ?, ?, ?, 't')"
    )
    db.execute(insert, (1, 2, "FINISHED", 2, 1, "ft_90", 100))
    for args in [
        (1, 1, "FINISHED", 2, 1, "ft_90", 101),  # a team cannot play itself
        (2, 1, "PAUSED", None, None, None, 102),  # status outside the allowed list
        (2, 1, "FINISHED", 21, 0, "ft_90", 103),  # goals above 20
        (2, 1, "FINISHED", -1, 0, "ft_90", 104),
        (2, 1, "FINISHED", 1, 0, "guess", 105),  # unknown result basis
        (1, 2, "FINISHED", 0, 0, "ft_90", 106),  # same fixture again (natural key)
        (2, 1, "FINISHED", 0, 0, "ft_90", 100),  # same source id again
    ]:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(insert, args)
    db.execute(insert, (2, 1, "SCHEDULED", None, None, None, None))  # goals may be NULL
    db.execute(
        insert.replace("'2025-10-18'", "'2025-10-25'"), (1, 2, "SCHEDULED", None, None, None, None)
    )
    assert db.execute("SELECT COUNT(*) FROM matches").fetchone() == (
        3,
    )  # several NULL fd ids are fine
