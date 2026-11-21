/**
 * SQL shared by more than one repository file, so each statement has one definition
 * (`index.ts` for the upload and watchdog paths, `queries.ts` for the read-only commands).
 */

/** The active run's metadata, read through the pointer (one definition for every reader). */
export const POINTER_SQL = `SELECT r.run_id, r.data_cutoff_utc, r.config_json, r.ensemble_json, a.activated_at
  FROM active_run a JOIN model_runs r ON r.run_id = a.run_id
  WHERE a.id = 1`;

export interface PointerSqlRow {
  run_id: string;
  data_cutoff_utc: string | null;
  config_json: string | null;
  ensemble_json: string | null;
  activated_at: string;
}

/** The small part of the active run: no model payloads. */
export interface ActivePointer {
  runId: string;
  activatedAt: string;
  dataCutoffUtc: string | null;
  configJson: string;
  ensembleJson: string;
}

export function toPointer(row: PointerSqlRow | null | undefined): ActivePointer | null {
  if (!row) return null;
  return {
    runId: row.run_id,
    activatedAt: row.activated_at,
    dataCutoffUtc: row.data_cutoff_utc,
    configJson: row.config_json ?? "{}",
    ensembleJson: row.ensemble_json ?? "{}",
  };
}

/** One day of coverage: scheduled matches, and the active run's forecast rows (bind: the date). */
export const COVERAGE_SQL = `SELECT
  (SELECT COUNT(*) FROM matches
    WHERE match_date = ?1 AND status IN ('SCHEDULED', 'TIMED')) AS scheduled,
  (SELECT COUNT(*) FROM fixture_forecasts
    WHERE run_id = (SELECT run_id FROM active_run WHERE id = 1)
      AND match_date = ?1) AS forecasts`;

export interface CoverageSqlRow {
  scheduled: number;
  forecasts: number;
}

/** The active run's id, as a scalar subquery. */
export const ACTIVE_RUN_ID = "(SELECT run_id FROM active_run WHERE id = 1)";
