-- 0006_calibration_snapshots.sql
-- Stage 6 (ADR-033, ADR-046): one row per weekly report, so calibration and scores can be compared
-- over time (architecture sections 5.6 and 8.7). Additive-first: nothing is renamed or dropped.
-- Timestamps are UTC ISO-8601 text, dates YYYY-MM-DD.

CREATE TABLE calibration_snapshots (
  snapshot_id  INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at   TEXT    NOT NULL,
  window_from  TEXT    NOT NULL,            -- first fixture date among the scored predictions
  window_to    TEXT    NOT NULL,            -- last fixture date among the scored predictions
  n_scored     INTEGER NOT NULL CHECK (n_scored > 0),
  metrics_json TEXT    NOT NULL,            -- scores, paired interval, per-model, per-competition,
                                            -- calibration bins, omission rates
  run_id       TEXT                         -- the active run at the time; a plain column (ADR-045)
);
CREATE INDEX idx_calibration_snapshots_created ON calibration_snapshots (created_at);
