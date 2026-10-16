-- 0001_foundations.sql
-- Stage 1 (ADR-033): only the tables Stage 1 needs. Every later stage creates its own tables
-- in its own migration. Additive-first: nothing here is ever renamed or dropped in the same
-- migration that adds a replacement. Timestamps are UTC ISO-8601 text, booleans 0/1.

-- Telegram update dedupe (S3, section 9.6). `kind` and `outcome` are deliberately free text so
-- later stages can add values without a table rebuild.
CREATE TABLE processed_updates (
  update_id   INTEGER PRIMARY KEY,
  received_at TEXT    NOT NULL,
  kind        TEXT    NOT NULL DEFAULT 'unknown',
  outcome     TEXT    NOT NULL DEFAULT 'received'
);

-- One row per accepted Telegram upload. Inserted as 'received' before any heavy work (ADR-029) so
-- the watchdog can find an upload that was acknowledged but never finalised.
-- run_id has no foreign key because `model_runs` does not exist until Stage 4 (ADR-033).
CREATE TABLE uploads (
  upload_id         INTEGER PRIMARY KEY AUTOINCREMENT,
  update_id         INTEGER NOT NULL UNIQUE,
  received_at       TEXT    NOT NULL,
  tg_file_unique_id TEXT,
  file_sha256       TEXT,
  size_bytes        INTEGER,
  run_date_utc      TEXT,
  schema_version    INTEGER,
  n_matches_in      INTEGER,
  n_excluded_in     INTEGER,
  n_published       INTEGER,
  n_omitted         INTEGER,
  n_duplicate       INTEGER,
  run_id            TEXT,
  status            TEXT    NOT NULL DEFAULT 'received'
                    CHECK (status IN ('received', 'rejected', 'processed', 'failed')),
  error_code        TEXT
);
CREATE INDEX idx_uploads_status_received ON uploads (status, received_at);

-- Durable, compact structured events (section 5.6). Pruned at 90 days by a later stage.
CREATE TABLE events (
  event_id    INTEGER PRIMARY KEY AUTOINCREMENT,
  at          TEXT    NOT NULL,
  level       TEXT    NOT NULL,
  source      TEXT    NOT NULL,
  kind        TEXT    NOT NULL,
  detail_json TEXT,
  dedupe_key  TEXT
);
CREATE INDEX idx_events_at ON events (at);
CREATE INDEX idx_events_dedupe ON events (dedupe_key, at) WHERE dedupe_key IS NOT NULL;

-- One row per nightly/backtest/report/bootstrap job (section 5.6).
CREATE TABLE job_runs (
  job_id       INTEGER PRIMARY KEY AUTOINCREMENT,
  kind         TEXT    NOT NULL,
  started_at   TEXT    NOT NULL,
  finished_at  TEXT,
  status       TEXT    NOT NULL,
  git_sha      TEXT,
  summary_json TEXT,
  error        TEXT
);
CREATE INDEX idx_job_runs_kind_started ON job_runs (kind, started_at);
