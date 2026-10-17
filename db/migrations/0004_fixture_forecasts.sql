-- 0004_fixture_forecasts.sql
-- Stage 5a (ADR-033, ADR-042): the nightly job stores one forecast per scheduled fixture; the
-- Worker only looks it up. Additive-first: nothing is renamed or dropped. Timestamps are UTC
-- ISO-8601 text, dates YYYY-MM-DD, probabilities REAL at full precision.

-- One row per (run, fixture). Immutable once written (the fit job uses INSERT OR IGNORE); deleted
-- with an old run, and kept only for the newest runs (architecture section 8.11).
-- Only a verdict 'ok' row carries probabilities. The other verdicts say why the Worker must omit
-- the match, with the numbers in detail_json.
CREATE TABLE fixture_forecasts (
  run_id        TEXT    NOT NULL REFERENCES model_runs (run_id),
  fixture_key   TEXT    NOT NULL,  -- '<match_date>|<comp>|<home_team_id>|<away_team_id>' (section 8.7)
  comp_code     TEXT    NOT NULL REFERENCES competitions (comp_code),
  match_date    TEXT    NOT NULL,  -- UTC calendar date of kickoff
  kickoff_utc   TEXT,
  home_team_id  INTEGER NOT NULL REFERENCES teams (team_id),
  away_team_id  INTEGER NOT NULL REFERENCES teams (team_id),
  verdict       TEXT    NOT NULL
                CHECK (verdict IN ('ok', 'INSUFFICIENT_HISTORY', 'DRIFT', 'NO_MODEL')),
  p_home        REAL,
  p_draw        REAL,
  p_away        REAL,
  p_over_05     REAL,
  p_over_15     REAL,
  p_over_25     REAL,
  p_over_35     REAL,
  p_over_45     REAL,
  p_over_55     REAL,
  total_json    TEXT,              -- ensemble total-goals pmf, 13 categories (0..11, 12+)
  models_json   TEXT,              -- per model: {"p": [home, draw, away], "total": [13]}
  weights_json  TEXT,              -- weights applied, over the models that produced a grid
  baseline_json TEXT,              -- league-frequency forecast for the competition
  detail_json   TEXT    NOT NULL,  -- drift statistics, team history counts, models left out
  created_at    TEXT    NOT NULL,
  PRIMARY KEY (run_id, fixture_key),
  CHECK (home_team_id <> away_team_id),
  CHECK (verdict <> 'ok' OR (
    p_home IS NOT NULL AND p_draw IS NOT NULL AND p_away IS NOT NULL
    AND p_over_05 IS NOT NULL AND p_over_15 IS NOT NULL AND p_over_25 IS NOT NULL
    AND p_over_35 IS NOT NULL AND p_over_45 IS NOT NULL AND p_over_55 IS NOT NULL
    AND total_json IS NOT NULL AND models_json IS NOT NULL AND weights_json IS NOT NULL
    AND baseline_json IS NOT NULL)),
  CHECK (verdict <> 'ok' OR abs(p_home + p_draw + p_away - 1.0) <= 0.000001),
  CHECK (verdict <> 'ok' OR (
    p_over_05 + 0.000000001 >= p_over_15 AND p_over_15 + 0.000000001 >= p_over_25
    AND p_over_25 + 0.000000001 >= p_over_35 AND p_over_35 + 0.000000001 >= p_over_45
    AND p_over_45 + 0.000000001 >= p_over_55))
);
-- The Worker reads every forecast of one date through the active run.
CREATE INDEX idx_fixture_forecasts_date ON fixture_forecasts (run_id, match_date);
