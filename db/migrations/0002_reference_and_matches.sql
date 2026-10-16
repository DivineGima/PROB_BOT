-- 0002_reference_and_matches.sql
-- Stage 2 (ADR-033): the tables ingestion first needs. Additive-first: nothing here is renamed or
-- dropped. Timestamps are UTC ISO-8601 text (YYYY-MM-DDTHH:MM:SSZ), dates YYYY-MM-DD, booleans 0/1.
-- `shots_*`, `uk_key` and `goals_source = 'fd_uk'` exist for later additive use (ADR-026, ADR-035);
-- under A-1 path 2 football-data.co.uk is not used and they stay NULL / unused.

-- 10 rows, seeded by `footy bootstrap` (section 5.2).
CREATE TABLE competitions (
  comp_code  TEXT    PRIMARY KEY
             CHECK (comp_code IN ('EPL', 'LL', 'BL', 'SA', 'L1', 'UCL', 'ERE', 'PPL', 'CHA', 'SPL')),
  name       TEXT    NOT NULL,
  fd_code    TEXT,
  uk_div     TEXT,
  has_shots  INTEGER NOT NULL DEFAULT 0 CHECK (has_shots IN (0, 1))
);

-- 179 active clubs (data/canonical_teams.json) plus history-only clubs with active = 0
-- (data/historical_teams.json, ADR-027).
CREATE TABLE teams (
  team_id        INTEGER PRIMARY KEY AUTOINCREMENT,
  canonical_name TEXT    NOT NULL UNIQUE,
  home_comp      TEXT    REFERENCES competitions (comp_code),
  is_ucl_only    INTEGER NOT NULL DEFAULT 0 CHECK (is_ucl_only IN (0, 1)),
  active         INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);
CREATE INDEX idx_teams_home_comp ON teams (home_comp);

-- One row per (source spelling -> team). An alias that would point at two teams is impossible
-- because of the unique key; a source spelling with no row is "unmapped" (reported, never guessed).
CREATE TABLE team_aliases (
  alias_id   INTEGER PRIMARY KEY AUTOINCREMENT,
  source     TEXT    NOT NULL CHECK (source IN ('fd_org', 'fd_uk', 'screener', 'manual')),
  alias_norm TEXT    NOT NULL,
  team_id    INTEGER NOT NULL REFERENCES teams (team_id),
  UNIQUE (source, alias_norm)
);
CREATE INDEX idx_team_aliases_team ON team_aliases (team_id);

-- Results (section 5.3). goals_* are 90 minutes plus stoppage time only, NULL until the result is
-- verified. result_basis says how the 90-minute score was obtained (ADR-010).
CREATE TABLE matches (
  match_id      INTEGER PRIMARY KEY AUTOINCREMENT,
  comp_code     TEXT    NOT NULL REFERENCES competitions (comp_code),
  season        TEXT    NOT NULL,
  match_date    TEXT    NOT NULL,
  kickoff_utc   TEXT,
  home_team_id  INTEGER NOT NULL REFERENCES teams (team_id),
  away_team_id  INTEGER NOT NULL REFERENCES teams (team_id),
  status        TEXT    NOT NULL
                CHECK (status IN ('SCHEDULED', 'TIMED', 'IN_PLAY', 'FINISHED', 'POSTPONED',
                                  'CANCELLED', 'SUSPENDED', 'AWARDED')),
  goals_home    INTEGER CHECK (goals_home IS NULL OR (goals_home BETWEEN 0 AND 20)),
  goals_away    INTEGER CHECK (goals_away IS NULL OR (goals_away BETWEEN 0 AND 20)),
  result_basis  TEXT    CHECK (result_basis IS NULL OR result_basis IN ('regular', 'ft_90', 'unverified')),
  shots_home    INTEGER,
  shots_away    INTEGER,
  fd_match_id   INTEGER UNIQUE,
  uk_key        TEXT,
  goals_source  TEXT    CHECK (goals_source IS NULL OR goals_source IN ('fd_org', 'fd_uk')),
  updated_at    TEXT    NOT NULL,
  CHECK (home_team_id <> away_team_id),
  UNIQUE (comp_code, season, match_date, home_team_id, away_team_id)
);
CREATE INDEX idx_matches_home_date   ON matches (home_team_id, match_date);
CREATE INDEX idx_matches_away_date   ON matches (away_team_id, match_date);
CREATE INDEX idx_matches_comp_date   ON matches (comp_code, match_date);
CREATE INDEX idx_matches_status_date ON matches (status, match_date);

-- Audit of every external fetch; also the cache metadata for conditional GETs (section 5.3).
CREATE TABLE source_fetch_log (
  fetch_id       INTEGER PRIMARY KEY AUTOINCREMENT,
  source         TEXT    NOT NULL,
  resource       TEXT    NOT NULL,
  fetched_at     TEXT    NOT NULL,
  http_status    INTEGER,
  ok             INTEGER NOT NULL CHECK (ok IN (0, 1)),
  etag           TEXT,
  last_modified  TEXT,
  content_sha256 TEXT,
  rows           INTEGER,
  bytes          INTEGER
);
CREATE INDEX idx_source_fetch_log_source_at ON source_fetch_log (source, fetched_at);
