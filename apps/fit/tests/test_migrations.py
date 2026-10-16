"""Migration tests on plain SQLite (the engine D1 is built on). The same files are applied to
Miniflare's local D1 by the Vitest suite; here they are also applied step by step, which proves
each migration applies on top of the schema left by the one before it."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

MIGRATIONS = Path(__file__).resolve().parents[3] / "db" / "migrations"
STAGE_1_TABLES = {"events", "job_runs", "processed_updates", "uploads"}


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


def test_applies_cleanly_to_an_empty_database_and_creates_only_stage_1_tables(
    db: sqlite3.Connection,
) -> None:
    apply(db, migration_files())
    assert tables(db) >= STAGE_1_TABLES
    # ADR-033: later-stage tables must not exist yet.
    assert not {"matches", "teams", "predictions", "model_runs"} & tables(db)


def test_applies_step_by_step_on_top_of_the_previous_schema(db: sqlite3.Connection) -> None:
    for path in migration_files():
        apply(db, [path])
    assert tables(db) >= STAGE_1_TABLES


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
