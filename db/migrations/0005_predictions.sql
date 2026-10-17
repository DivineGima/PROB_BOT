-- 0005_predictions.sql
-- Stage 5b (ADR-033, ADR-042, ADR-045): the prediction log and the omissions of an upload.
-- Additive-first: nothing is renamed or dropped. Timestamps are UTC ISO-8601 text, dates
-- YYYY-MM-DD, probabilities REAL at full precision (display rounding is a presentation concern).

-- One row per published fixture. The Worker COPIES the stored forecast into this row (it computes
-- nothing); the first row for a fixture_key wins (INSERT OR IGNORE) and its forecast columns are
-- never changed afterwards: the only writers are the Worker's insert and `footy score`, which
-- updates the result and scoring columns only (invariant 2, section 5.7, enforced in code and tests). run_id is a plain column, not a foreign key (ADR-045): a prediction copies what it
-- needs, so old runs can be pruned.
CREATE TABLE predictions (
  pred_id       INTEGER PRIMARY KEY AUTOINCREMENT,
  fixture_key   TEXT    NOT NULL UNIQUE,  -- '<match_date>|<comp>|<home_team_id>|<away_team_id>'
  upload_id     INTEGER NOT NULL REFERENCES uploads (upload_id),
  run_id        TEXT    NOT NULL,
  label         TEXT    NOT NULL,         -- the screener's match_id, display only
  comp_code     TEXT    NOT NULL REFERENCES competitions (comp_code),
  match_date    TEXT    NOT NULL,         -- UTC kickoff date, the first part of fixture_key
  kickoff_utc   TEXT    NOT NULL,         -- the screener's time
  home_team_id  INTEGER NOT NULL REFERENCES teams (team_id),
  away_team_id  INTEGER NOT NULL REFERENCES teams (team_id),
  p_home        REAL    NOT NULL,
  p_draw        REAL    NOT NULL,
  p_away        REAL    NOT NULL,
  p_over_05     REAL    NOT NULL,
  p_over_15     REAL    NOT NULL,
  p_over_25     REAL    NOT NULL,
  p_over_35     REAL    NOT NULL,
  p_over_45     REAL    NOT NULL,
  p_over_55     REAL    NOT NULL,
  total_json    TEXT    NOT NULL,         -- ensemble total-goals pmf, 13 categories
  models_json   TEXT    NOT NULL,         -- per model: {"p": [h, d, a], "total": [13]}
  weights_json  TEXT    NOT NULL,         -- weights applied
  drift_json    TEXT    NOT NULL,         -- drift statistics and verdict (from the forecast)
  baseline_json TEXT    NOT NULL,         -- league-frequency forecast for the competition
  inputs_json   TEXT    NOT NULL,         -- screener fields: lineup, absences, rest days, urls
  status        TEXT    NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'scored', 'void')),
  void_reason   TEXT    CHECK (void_reason IS NULL OR void_reason IN
                  ('POSTPONED', 'CANCELLED', 'SUSPENDED', 'AWARDED', 'UNVERIFIED_RESULT',
                   'NO_RESULT')),
  goals_home    INTEGER,
  goals_away    INTEGER,
  rps_1x2       REAL,
  rps_totals    REAL,
  logloss_1x2   REAL,
  created_at    TEXT    NOT NULL,
  scored_at     TEXT,
  CHECK (home_team_id <> away_team_id),
  CHECK (abs(p_home + p_draw + p_away - 1.0) <= 0.000001),
  CHECK (p_over_05 + 0.000000001 >= p_over_15 AND p_over_15 + 0.000000001 >= p_over_25
         AND p_over_25 + 0.000000001 >= p_over_35 AND p_over_35 + 0.000000001 >= p_over_45
         AND p_over_45 + 0.000000001 >= p_over_55),
  CHECK ((status = 'void') = (void_reason IS NOT NULL)),
  CHECK (status <> 'scored' OR (goals_home IS NOT NULL AND goals_away IS NOT NULL
         AND rps_1x2 IS NOT NULL AND rps_totals IS NOT NULL AND logloss_1x2 IS NOT NULL
         AND scored_at IS NOT NULL))
);
CREATE INDEX idx_predictions_status_date ON predictions (status, match_date);
CREATE INDEX idx_predictions_comp_date ON predictions (comp_code, match_date);
CREATE INDEX idx_predictions_date ON predictions (match_date);

-- Matches in an upload that did not produce a prediction, with the reason (ADR-024).
CREATE TABLE omissions (
  omission_id INTEGER PRIMARY KEY AUTOINCREMENT,
  upload_id   INTEGER NOT NULL REFERENCES uploads (upload_id),
  label       TEXT    NOT NULL,
  reason_code TEXT    NOT NULL CHECK (reason_code IN
                ('UNMAPPED_TEAM', 'INSUFFICIENT_HISTORY', 'DRIFT', 'STARTED', 'TOO_FAR',
                 'DATE_MISMATCH', 'NO_MODEL', 'DUPLICATE_PAIR', 'NO_FORECAST')),
  detail_json TEXT,
  UNIQUE (upload_id, label)
);
