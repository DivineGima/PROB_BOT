-- 0003_model_registry.sql
-- Stage 4 (ADR-033): the model registry the fit job writes and the Worker reads (section 5.4).
-- Additive-first: nothing is renamed or dropped. Timestamps are UTC ISO-8601 text, dates
-- YYYY-MM-DD, booleans 0/1.

-- One immutable row per nightly fit. Once `active` only `status` may change (ADR-004); the fit job
-- never updates any other column after promotion.
CREATE TABLE model_runs (
  run_id           TEXT PRIMARY KEY,  -- 'R' + UTC timestamp, e.g. R20261016T011742Z
  status           TEXT NOT NULL
                   CHECK (status IN ('building', 'active', 'superseded', 'rejected', 'failed')),
  started_at       TEXT NOT NULL,
  finished_at      TEXT,
  data_cutoff_utc  TEXT,              -- latest result date included
  training_from    TEXT,              -- window actually used
  training_to      TEXT,
  git_sha          TEXT,
  code_version     TEXT,
  config_json      TEXT,              -- snapshot of thresholds, baselines, flags (unvalidated)
  ensemble_json    TEXT,              -- weights per model, method, scored matches used
  diagnostics_json TEXT               -- convergence, sanity checks, counts, freshness, gate result
);
CREATE INDEX idx_model_runs_status_started ON model_runs (status, started_at);

-- Exactly one row: the pointer the Worker follows (section 8.6). Updated in one statement.
CREATE TABLE active_run (
  id           INTEGER PRIMARY KEY CHECK (id = 1),
  run_id       TEXT    NOT NULL REFERENCES model_runs (run_id),
  activated_at TEXT    NOT NULL
);

-- Per-model parameters for all teams (about 10 to 60 KB of JSON). A failed model is stored with
-- status 'failed' and no payload; it is never silently replaced by yesterday's parameters.
CREATE TABLE model_params (
  run_id          TEXT    NOT NULL REFERENCES model_runs (run_id),
  model           TEXT    NOT NULL CHECK (model IN ('dc', 'pi', 'bp')),
  status          TEXT    NOT NULL CHECK (status IN ('ok', 'failed')),
  payload_version INTEGER,
  payload_json    TEXT,
  payload_sha256  TEXT,
  error           TEXT,
  PRIMARY KEY (run_id, model),
  CHECK (status = 'failed' OR (payload_json IS NOT NULL AND payload_sha256 IS NOT NULL
                               AND payload_version IS NOT NULL))
);

-- Per run and team: the drift filter inputs and the "fewer than 10 matches" rule, precomputed so
-- the Worker needs no recomputation. Goals only in v1: the shots columns stay NULL (ADR-026).
CREATE TABLE team_form (
  run_id            TEXT    NOT NULL REFERENCES model_runs (run_id),
  team_id           INTEGER NOT NULL REFERENCES teams (team_id),
  n_training        INTEGER NOT NULL,
  n_season          INTEGER NOT NULL,
  season_gf         REAL,
  season_ga         REAL,
  l10_n             INTEGER NOT NULL,
  l10_gf            REAL,
  l10_ga            REAL,
  shots_n           INTEGER,
  season_sf         REAL,
  season_sa         REAL,
  l10_sf            REAL,
  l10_sa            REAL,
  latest_match_date TEXT,
  PRIMARY KEY (run_id, team_id)
);
