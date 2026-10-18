/**
 * The ONLY module in the Worker that touches D1 (architecture sections 6.5 and 6.9, locked
 * Database rule). Parameterised statements only; multi-statement work goes through `batch()`.
 * Stage 1 ships the skeleton: update dedupe, the upload record (inserted as `received` first,
 * ADR-029), events and, from Stage 4, the read of the active model run. Stage 5b (version 2,
 * ADR-042) adds the stored-forecast read, the prediction log, omissions and team resolution. The
 * Worker never reads model parameters any more: the nightly job stores finished numbers.
 */
import type { OmissionCode } from "../config/errors";

export type Clock = () => Date;

const EVENT_DEDUPE_MS = 24 * 60 * 60 * 1000;

export type UploadStatus = "received" | "rejected" | "processed" | "failed";
export type EventLevel = "info" | "warn" | "error";

export interface NewUpload {
  updateId: number;
  tgFileUniqueId?: string;
  sizeBytes?: number;
}

export interface UploadFinalisation {
  status: Exclude<UploadStatus, "received">;
  errorCode?: string;
  runDateUtc?: string;
  schemaVersion?: number;
  nMatchesIn?: number;
  nExcludedIn?: number;
  nPublished?: number;
  nOmitted?: number;
  nDuplicate?: number;
  runId?: string;
  fileSha256?: string;
}

export interface StaleUpload {
  uploadId: number;
  updateId: number;
  receivedAt: string;
}

export interface NewEvent {
  level: EventLevel;
  source: string;
  kind: string;
  detail?: Record<string, unknown>;
  dedupeKey?: string;
}

export interface UpdateRepository {
  /** Insert-once on `update_id`. Returns true only the first time (S3, section 9.6). */
  markProcessed(updateId: number, kind?: string): Promise<boolean>;
}

export interface UploadRepository {
  /** Inserts the row as `received` and returns its id; idempotent per `update_id`. */
  record(upload: NewUpload): Promise<number>;
  /** Moves a `received` upload to its final state. Returns false if it was no longer `received`. */
  finalise(uploadId: number, result: UploadFinalisation): Promise<boolean>;
  /** Uploads still `received` after `olderThanMinutes` (the watchdog, ADR-029). */
  findStale(olderThanMinutes: number): Promise<StaleUpload[]>;
  /**
   * ONE batch (one transaction): insert the new predictions (first one wins), insert the
   * omissions, finalise the upload. Returns false if the upload was no longer `received`.
   */
  commit(commit: UploadCommit): Promise<boolean>;
}

export interface EventRepository {
  record(event: NewEvent): Promise<void>;
  /** True when an event with this dedupe key was written in the last 24 hours (section 9.2). */
  hasRecent(dedupeKey: string): Promise<boolean>;
}

/** One day of the watchdog's coverage question: fixtures still to play, forecasts stored for them. */
export interface DayCoverage {
  date: string;
  scheduled: number;
  forecasts: number;
}

export interface HealthRepository {
  /** For each date: scheduled matches, and the active run's forecast rows (0 without an active run). */
  forecastCoverage(dates: string[]): Promise<DayCoverage[]>;
}

export type ModelName = "dc" | "pi" | "bp";

export interface ModelParams {
  model: ModelName;
  status: "ok" | "failed";
  payloadVersion: number | null;
  payloadJson: string | null;
  payloadSha256: string | null;
  error: string | null;
}

/**
 * The run `active_run` points at, with every model row (section 8.6).
 * @deprecated since v2 (ADR-042): the Worker no longer reads model payloads. Kept, not removed.
 */
export interface ActiveRun {
  runId: string;
  activatedAt: string;
  dataCutoffUtc: string | null;
  configJson: string;
  ensembleJson: string;
  params: ModelParams[];
}

/** The small part of the active run: no model payloads. */
export interface ActivePointer {
  runId: string;
  activatedAt: string;
  dataCutoffUtc: string | null;
  configJson: string;
  ensembleJson: string;
}

/** The active run with the integrity result of each model payload, computed once per run. */
export interface VerifiedActiveRun {
  run: ActiveRun;
  verified: Partial<Record<ModelName, boolean>>;
}

export interface RunRepository {
  /**
   * One consistent read keyed through the pointer, so a half-published run is never seen
   * (section 8.6 step 4). Null when nothing has been published yet. Reads every payload.
   * @deprecated since v2 (ADR-042); use `ForecastRepository.readActiveForDate`.
   */
  readActive(): Promise<ActiveRun | null>;
  /** Only the pointer and run metadata (one small row); cheap enough for every request. */
  readPointer(): Promise<ActivePointer | null>;
  /**
   * The active run with its payloads verified, kept in memory while the pointer is unchanged:
   * each request costs one small read, and the payloads are fetched, hashed and kept only when
   * the active run changes. Runs are immutable once active (ADR-004), so a cached run never goes
   * stale while its `runId` and `activatedAt` are the same.
   * @deprecated since v2 (ADR-042); the Worker reads stored forecasts instead of payloads.
   */
  readActiveVerified(): Promise<VerifiedActiveRun | null>;
}

let verifiedCache: { key: string; value: VerifiedActiveRun } | null = null;

/** Forget the cached run (tests, or after an explicit rollback drill). */
export function clearActiveRunCache(): void {
  verifiedCache = null;
}

export type ForecastVerdict = "ok" | "INSUFFICIENT_HISTORY" | "DRIFT" | "NO_MODEL";

/** One stored forecast (section 5.4): numbers only when `verdict` is `ok`. */
export interface ForecastRow {
  fixtureKey: string;
  compCode: string;
  matchDate: string;
  kickoffUtc: string | null;
  homeTeamId: number;
  awayTeamId: number;
  verdict: ForecastVerdict;
  /** [home, draw, away] */
  p1x2: [number, number, number] | null;
  /** P(over 0.5) .. P(over 5.5) */
  overs: number[] | null;
  totalJson: string | null;
  modelsJson: string | null;
  weightsJson: string | null;
  baselineJson: string | null;
  detailJson: string;
}

export interface ForecastRead {
  /** The active run, or null when nothing has been published (E_NO_RUN). */
  pointer: ActivePointer | null;
  /** Forecasts of that run for the requested date. */
  forecasts: ForecastRow[];
  /** False when the active run has no forecast rows at all (an older run, or none fitted). */
  runHasForecasts: boolean;
}

export interface ForecastRepository {
  /** ONE batch through the `active_run` pointer, so pointer and forecasts are the same state. */
  readActiveForDate(matchDate: string): Promise<ForecastRead>;
}

/** The forecast values a prediction copies, plus the screener's own fields (section 5.5). */
export interface NewPrediction {
  fixtureKey: string;
  label: string;
  compCode: string;
  matchDate: string;
  kickoffUtc: string;
  homeTeamId: number;
  awayTeamId: number;
  p1x2: [number, number, number];
  overs: number[];
  totalJson: string;
  modelsJson: string;
  weightsJson: string;
  driftJson: string;
  baselineJson: string;
  inputsJson: string;
}

export interface StoredPrediction extends NewPrediction {
  predId: number;
  uploadId: number;
  runId: string;
  status: "pending" | "scored" | "void";
}

export interface NewOmission {
  label: string;
  reason: OmissionCode;
  detail?: Record<string, unknown>;
}

export interface UploadCommit {
  uploadId: number;
  runId: string;
  predictions: NewPrediction[];
  omissions: NewOmission[];
  finalisation: UploadFinalisation;
}

export interface PredictionRepository {
  /** Insert-or-ignore on `fixture_key`: the first prediction for a fixture is never replaced. */
  insertManyIgnoreDuplicates(
    uploadId: number,
    runId: string,
    rows: NewPrediction[],
  ): Promise<number>;
  /** Every prediction whose fixture date is `matchDate`, whichever upload made it. */
  findByDate(matchDate: string): Promise<StoredPrediction[]>;
}

export interface TeamRepository {
  /** Exact canonical names that exist in `teams` -> team id. Unknown names are absent. */
  resolveCanonical(names: string[]): Promise<Map<string, number>>;
}

export interface Repositories {
  updates: UpdateRepository;
  uploads: UploadRepository;
  events: EventRepository;
  runs: RunRepository;
  forecasts: ForecastRepository;
  predictions: PredictionRepository;
  teams: TeamRepository;
  health: HealthRepository;
}

/** Lower-case hex SHA-256 of the text's UTF-8 bytes, the form `model_params.payload_sha256` uses. */
export async function sha256Hex(text: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/**
 * True only for an `ok` row whose stored hash matches its payload text (integrity on read).
 * @deprecated since v2 (ADR-042): only the deprecated payload reads use it.
 */
export async function payloadVerifies(params: ModelParams): Promise<boolean> {
  if (params.status !== "ok" || params.payloadJson === null || params.payloadSha256 === null) {
    return false;
  }
  return (await sha256Hex(params.payloadJson)) === params.payloadSha256;
}

const toIso = (date: Date): string => `${date.toISOString().slice(0, 19)}Z`;

/** Bound-parameter cap of one D1 statement is 100; stay below it for `IN (...)` lists. */
const IN_CHUNK = 90;

/**
 * Only a clash on the fixture key is ignored (the first prediction for a fixture wins). A row that
 * breaks a CHECK or NOT NULL constraint RAISES, which rolls the whole batch back and leaves the
 * upload `received`, so the pipeline answers with an error instead of finalising an upload whose
 * predictions were silently dropped (code review of PR 21). `INSERT OR IGNORE` would skip those too.
 */
const PREDICTION_INSERT = `
INSERT INTO predictions (
  fixture_key, upload_id, run_id, label, comp_code, match_date, kickoff_utc, home_team_id,
  away_team_id, p_home, p_draw, p_away, p_over_05, p_over_15, p_over_25, p_over_35, p_over_45,
  p_over_55, total_json, models_json, weights_json, drift_json, baseline_json, inputs_json,
  created_at)
SELECT json_extract(j.value, '$.fixture_key'), ?2, ?3, json_extract(j.value, '$.label'),
  json_extract(j.value, '$.comp_code'), json_extract(j.value, '$.match_date'),
  json_extract(j.value, '$.kickoff_utc'), json_extract(j.value, '$.home_team_id'),
  json_extract(j.value, '$.away_team_id'), json_extract(j.value, '$.p[0]'),
  json_extract(j.value, '$.p[1]'), json_extract(j.value, '$.p[2]'),
  json_extract(j.value, '$.overs[0]'), json_extract(j.value, '$.overs[1]'),
  json_extract(j.value, '$.overs[2]'), json_extract(j.value, '$.overs[3]'),
  json_extract(j.value, '$.overs[4]'), json_extract(j.value, '$.overs[5]'),
  json_extract(j.value, '$.total_json'), json_extract(j.value, '$.models_json'),
  json_extract(j.value, '$.weights_json'), json_extract(j.value, '$.drift_json'),
  json_extract(j.value, '$.baseline_json'), json_extract(j.value, '$.inputs_json'), ?4
FROM json_each(?1) AS j
WHERE 1
ON CONFLICT (fixture_key) DO NOTHING`;

/** Plain INSERT: labels are unique per upload by construction, so a clash is a bug and must raise. */
const OMISSION_INSERT = `
INSERT INTO omissions (upload_id, label, reason_code, detail_json)
SELECT ?2, json_extract(j.value, '$.label'), json_extract(j.value, '$.reason'),
  json_extract(j.value, '$.detail')
FROM json_each(?1) AS j`;

/** The active run's metadata, read through the pointer (one definition for every reader). */
const POINTER_SQL = `SELECT r.run_id, r.data_cutoff_utc, r.config_json, r.ensemble_json, a.activated_at
  FROM active_run a JOIN model_runs r ON r.run_id = a.run_id
  WHERE a.id = 1`;

interface PointerSqlRow {
  run_id: string;
  data_cutoff_utc: string | null;
  config_json: string | null;
  ensemble_json: string | null;
  activated_at: string;
}

function toPointer(row: PointerSqlRow | null | undefined): ActivePointer | null {
  if (!row) return null;
  return {
    runId: row.run_id,
    activatedAt: row.activated_at,
    dataCutoffUtc: row.data_cutoff_utc,
    configJson: row.config_json ?? "{}",
    ensembleJson: row.ensemble_json ?? "{}",
  };
}

const FORECAST_COLUMNS = `fixture_key, comp_code, match_date, kickoff_utc, home_team_id,
  away_team_id, verdict, p_home, p_draw, p_away, p_over_05, p_over_15, p_over_25, p_over_35,
  p_over_45, p_over_55, total_json, models_json, weights_json, baseline_json, detail_json`;

interface ForecastSqlRow {
  fixture_key: string;
  comp_code: string;
  match_date: string;
  kickoff_utc: string | null;
  home_team_id: number;
  away_team_id: number;
  verdict: ForecastVerdict;
  p_home: number | null;
  p_draw: number | null;
  p_away: number | null;
  p_over_05: number | null;
  p_over_15: number | null;
  p_over_25: number | null;
  p_over_35: number | null;
  p_over_45: number | null;
  p_over_55: number | null;
  total_json: string | null;
  models_json: string | null;
  weights_json: string | null;
  baseline_json: string | null;
  detail_json: string;
}

function toForecast(r: ForecastSqlRow): ForecastRow {
  const overs = [r.p_over_05, r.p_over_15, r.p_over_25, r.p_over_35, r.p_over_45, r.p_over_55];
  const ok = r.p_home !== null && r.p_draw !== null && r.p_away !== null;
  return {
    fixtureKey: r.fixture_key,
    compCode: r.comp_code,
    matchDate: r.match_date,
    kickoffUtc: r.kickoff_utc,
    homeTeamId: r.home_team_id,
    awayTeamId: r.away_team_id,
    verdict: r.verdict,
    p1x2: ok ? [r.p_home as number, r.p_draw as number, r.p_away as number] : null,
    overs: overs.every((v) => v !== null) ? (overs as number[]) : null,
    totalJson: r.total_json,
    modelsJson: r.models_json,
    weightsJson: r.weights_json,
    baselineJson: r.baseline_json,
    detailJson: r.detail_json,
  };
}

interface PredictionSqlRow {
  pred_id: number;
  fixture_key: string;
  upload_id: number;
  run_id: string;
  label: string;
  comp_code: string;
  match_date: string;
  kickoff_utc: string;
  home_team_id: number;
  away_team_id: number;
  p_home: number;
  p_draw: number;
  p_away: number;
  p_over_05: number;
  p_over_15: number;
  p_over_25: number;
  p_over_35: number;
  p_over_45: number;
  p_over_55: number;
  total_json: string;
  models_json: string;
  weights_json: string;
  drift_json: string;
  baseline_json: string;
  inputs_json: string;
  status: "pending" | "scored" | "void";
}

function toPrediction(r: PredictionSqlRow): StoredPrediction {
  return {
    predId: r.pred_id,
    uploadId: r.upload_id,
    runId: r.run_id,
    status: r.status,
    fixtureKey: r.fixture_key,
    label: r.label,
    compCode: r.comp_code,
    matchDate: r.match_date,
    kickoffUtc: r.kickoff_utc,
    homeTeamId: r.home_team_id,
    awayTeamId: r.away_team_id,
    p1x2: [r.p_home, r.p_draw, r.p_away],
    overs: [r.p_over_05, r.p_over_15, r.p_over_25, r.p_over_35, r.p_over_45, r.p_over_55],
    totalJson: r.total_json,
    modelsJson: r.models_json,
    weightsJson: r.weights_json,
    driftJson: r.drift_json,
    baselineJson: r.baseline_json,
    inputsJson: r.inputs_json,
  };
}

/** The JSON document the insert statement unpacks with `json_each` (one bound parameter). */
function predictionDocument(rows: NewPrediction[]): string {
  return JSON.stringify(
    rows.map((r) => ({
      fixture_key: r.fixtureKey,
      label: r.label,
      comp_code: r.compCode,
      match_date: r.matchDate,
      kickoff_utc: r.kickoffUtc,
      home_team_id: r.homeTeamId,
      away_team_id: r.awayTeamId,
      p: r.p1x2,
      overs: r.overs,
      total_json: r.totalJson,
      models_json: r.modelsJson,
      weights_json: r.weightsJson,
      drift_json: r.driftJson,
      baseline_json: r.baselineJson,
      inputs_json: r.inputsJson,
    })),
  );
}

function omissionDocument(rows: NewOmission[]): string {
  return JSON.stringify(
    rows.map((r) => ({
      label: r.label,
      reason: r.reason,
      detail: r.detail === undefined ? null : JSON.stringify(r.detail),
    })),
  );
}

export function createRepositories(db: D1Database, clock: Clock = () => new Date()): Repositories {
  const updates: UpdateRepository = {
    async markProcessed(updateId, kind = "unknown") {
      const result = await db
        .prepare(
          "INSERT OR IGNORE INTO processed_updates (update_id, received_at, kind) VALUES (?1, ?2, ?3)",
        )
        .bind(updateId, toIso(clock()), kind)
        .run();
      return result.meta.changes === 1;
    },
  };

  const predictionStatement = (
    uploadId: number,
    runId: string,
    rows: NewPrediction[],
  ): D1PreparedStatement =>
    db.prepare(PREDICTION_INSERT).bind(predictionDocument(rows), uploadId, runId, toIso(clock()));

  const finaliseStatement = (uploadId: number, result: UploadFinalisation): D1PreparedStatement =>
    db
      .prepare(
        `UPDATE uploads SET
           status = ?2, error_code = ?3, run_date_utc = ?4, schema_version = ?5,
           n_matches_in = ?6, n_excluded_in = ?7, n_published = ?8, n_omitted = ?9,
           n_duplicate = ?10, run_id = ?11, file_sha256 = ?12
         WHERE upload_id = ?1 AND status = 'received'`,
      )
      .bind(
        uploadId,
        result.status,
        result.errorCode ?? null,
        result.runDateUtc ?? null,
        result.schemaVersion ?? null,
        result.nMatchesIn ?? null,
        result.nExcludedIn ?? null,
        result.nPublished ?? null,
        result.nOmitted ?? null,
        result.nDuplicate ?? null,
        result.runId ?? null,
        result.fileSha256 ?? null,
      );

  const uploads: UploadRepository = {
    async record(upload) {
      const row = await db
        .prepare(
          `INSERT INTO uploads (update_id, received_at, tg_file_unique_id, size_bytes, status)
           VALUES (?1, ?2, ?3, ?4, 'received')
           ON CONFLICT (update_id) DO UPDATE SET update_id = excluded.update_id
           RETURNING upload_id`,
        )
        .bind(
          upload.updateId,
          toIso(clock()),
          upload.tgFileUniqueId ?? null,
          upload.sizeBytes ?? null,
        )
        .first<{ upload_id: number }>();
      if (!row) throw new Error("uploads insert returned no row");
      return row.upload_id;
    },

    async finalise(uploadId, result) {
      const outcome = await finaliseStatement(uploadId, result).run();
      return outcome.meta.changes === 1;
    },

    async commit(commit) {
      const statements: D1PreparedStatement[] = [];
      if (commit.predictions.length > 0) {
        statements.push(predictionStatement(commit.uploadId, commit.runId, commit.predictions));
      }
      if (commit.omissions.length > 0) {
        statements.push(
          db.prepare(OMISSION_INSERT).bind(omissionDocument(commit.omissions), commit.uploadId),
        );
      }
      statements.push(finaliseStatement(commit.uploadId, commit.finalisation));
      const results = await db.batch(statements);
      return results[results.length - 1]?.meta.changes === 1;
    },

    async findStale(olderThanMinutes) {
      const cutoff = toIso(new Date(clock().getTime() - olderThanMinutes * 60_000));
      const { results } = await db
        .prepare(
          `SELECT upload_id, update_id, received_at FROM uploads
           WHERE status = 'received' AND received_at <= ?1
           ORDER BY received_at`,
        )
        .bind(cutoff)
        .all<{ upload_id: number; update_id: number; received_at: string }>();
      return results.map((r) => ({
        uploadId: r.upload_id,
        updateId: r.update_id,
        receivedAt: r.received_at,
      }));
    },
  };

  const events: EventRepository = {
    async record(event) {
      const at = clock();
      const detail = event.detail === undefined ? null : JSON.stringify(event.detail);
      if (event.dedupeKey === undefined) {
        await db
          .prepare(
            `INSERT INTO events (at, level, source, kind, detail_json, dedupe_key)
             VALUES (?1, ?2, ?3, ?4, ?5, NULL)`,
          )
          .bind(toIso(at), event.level, event.source, event.kind, detail)
          .run();
        return;
      }
      // At most one event per key per 24 hours (section 9.2); a repeat costs one indexed read.
      const cutoff = toIso(new Date(at.getTime() - EVENT_DEDUPE_MS));
      await db
        .prepare(
          `INSERT INTO events (at, level, source, kind, detail_json, dedupe_key)
           SELECT ?1, ?2, ?3, ?4, ?5, ?6
           WHERE NOT EXISTS (SELECT 1 FROM events WHERE dedupe_key = ?6 AND at >= ?7)`,
        )
        .bind(toIso(at), event.level, event.source, event.kind, detail, event.dedupeKey, cutoff)
        .run();
    },

    async hasRecent(dedupeKey) {
      const cutoff = toIso(new Date(clock().getTime() - EVENT_DEDUPE_MS));
      const row = await db
        .prepare("SELECT 1 AS found FROM events WHERE dedupe_key = ?1 AND at >= ?2 LIMIT 1")
        .bind(dedupeKey, cutoff)
        .first<{ found: number }>();
      return row !== null;
    },
  };

  const readPointer = async (): Promise<ActivePointer | null> =>
    toPointer(await db.prepare(POINTER_SQL).first<PointerSqlRow>());

  const runs: RunRepository = {
    readPointer,

    async readActiveVerified() {
      const pointer = await readPointer();
      if (!pointer) {
        verifiedCache = null;
        return null;
      }
      const key = `${pointer.runId}|${pointer.activatedAt}`;
      if (verifiedCache?.key === key) return verifiedCache.value;
      const run = await runs.readActive();
      if (!run) {
        verifiedCache = null;
        return null;
      }
      const verified: Partial<Record<ModelName, boolean>> = {};
      for (const params of run.params) verified[params.model] = await payloadVerifies(params);
      const value = { run, verified };
      // The pointer may have moved between the two reads; key by what was actually read.
      verifiedCache = { key: `${run.runId}|${run.activatedAt}`, value };
      return value;
    },

    async readActive() {
      // A batch is one transaction, so the run row and its parameters come from the same state.
      const [runResult, paramResult] = await db.batch([
        db.prepare(
          `SELECT r.run_id, r.data_cutoff_utc, r.config_json, r.ensemble_json, a.activated_at
           FROM active_run a JOIN model_runs r ON r.run_id = a.run_id
           WHERE a.id = 1`,
        ),
        db.prepare(
          `SELECT model, status, payload_version, payload_json, payload_sha256, error
           FROM model_params
           WHERE run_id = (SELECT run_id FROM active_run WHERE id = 1)
           ORDER BY model`,
        ),
      ]);
      const run = runResult?.results[0] as
        | {
            run_id: string;
            data_cutoff_utc: string | null;
            config_json: string | null;
            ensemble_json: string | null;
            activated_at: string;
          }
        | undefined;
      if (!run) return null;
      const rows = (paramResult?.results ?? []) as Array<{
        model: ModelName;
        status: "ok" | "failed";
        payload_version: number | null;
        payload_json: string | null;
        payload_sha256: string | null;
        error: string | null;
      }>;
      return {
        runId: run.run_id,
        activatedAt: run.activated_at,
        dataCutoffUtc: run.data_cutoff_utc,
        configJson: run.config_json ?? "{}",
        ensembleJson: run.ensemble_json ?? "{}",
        params: rows.map((r) => ({
          model: r.model,
          status: r.status,
          payloadVersion: r.payload_version,
          payloadJson: r.payload_json,
          payloadSha256: r.payload_sha256,
          error: r.error,
        })),
      };
    },
  };

  const forecasts: ForecastRepository = {
    async readActiveForDate(matchDate) {
      // One batch = one transaction: the pointer, the day's forecasts and the "does this run have
      // any forecasts" probe all describe the same active run.
      const [pointerResult, forecastResult, countResult] = await db.batch([
        db.prepare(POINTER_SQL),
        db
          .prepare(
            `SELECT ${FORECAST_COLUMNS} FROM fixture_forecasts
             WHERE run_id = (SELECT run_id FROM active_run WHERE id = 1) AND match_date = ?1
             ORDER BY fixture_key`,
          )
          .bind(matchDate),
        db.prepare(
          `SELECT EXISTS (SELECT 1 FROM fixture_forecasts
             WHERE run_id = (SELECT run_id FROM active_run WHERE id = 1)) AS has_any`,
        ),
      ]);
      const pointer = toPointer(pointerResult?.results[0] as PointerSqlRow | undefined);
      const rows = (forecastResult?.results ?? []) as unknown as ForecastSqlRow[];
      const hasAny = (countResult?.results[0] as { has_any: number } | undefined)?.has_any === 1;
      return { pointer, forecasts: rows.map(toForecast), runHasForecasts: hasAny };
    },
  };

  const predictions: PredictionRepository = {
    async insertManyIgnoreDuplicates(uploadId, runId, rows) {
      if (rows.length === 0) return 0;
      const outcome = await predictionStatement(uploadId, runId, rows).run();
      return outcome.meta.changes;
    },

    async findByDate(matchDate) {
      const { results } = await db
        .prepare(
          `SELECT pred_id, fixture_key, upload_id, run_id, label, comp_code, match_date, kickoff_utc,
             home_team_id, away_team_id, p_home, p_draw, p_away, p_over_05, p_over_15, p_over_25,
             p_over_35, p_over_45, p_over_55, total_json, models_json, weights_json, drift_json,
             baseline_json, inputs_json, status
           FROM predictions WHERE match_date = ?1 ORDER BY pred_id`,
        )
        .bind(matchDate)
        .all<PredictionSqlRow>();
      return results.map(toPrediction);
    },
  };

  const teams: TeamRepository = {
    async resolveCanonical(names) {
      const unique = [...new Set(names)];
      const found = new Map<string, number>();
      if (unique.length === 0) return found;
      const statements: D1PreparedStatement[] = [];
      for (let start = 0; start < unique.length; start += IN_CHUNK) {
        const chunk = unique.slice(start, start + IN_CHUNK);
        const marks = chunk.map((_, i) => `?${i + 1}`).join(", ");
        statements.push(
          db
            .prepare(`SELECT team_id, canonical_name FROM teams WHERE canonical_name IN (${marks})`)
            .bind(...chunk),
        );
      }
      for (const result of await db.batch(statements)) {
        for (const row of (result.results ?? []) as Array<{
          team_id: number;
          canonical_name: string;
        }>) {
          found.set(row.canonical_name, row.team_id);
        }
      }
      return found;
    },
  };

  const health: HealthRepository = {
    async forecastCoverage(dates) {
      if (dates.length === 0) return [];
      // One batch = one transaction, so every day is read against the same active run.
      const results = await db.batch(
        dates.map((date) =>
          db
            .prepare(
              `SELECT
                 (SELECT COUNT(*) FROM matches
                   WHERE match_date = ?1 AND status IN ('SCHEDULED', 'TIMED')) AS scheduled,
                 (SELECT COUNT(*) FROM fixture_forecasts
                   WHERE run_id = (SELECT run_id FROM active_run WHERE id = 1)
                     AND match_date = ?1) AS forecasts`,
            )
            .bind(date),
        ),
      );
      return dates.map((date, i) => {
        const row = results[i]?.results[0] as { scheduled: number; forecasts: number } | undefined;
        return { date, scheduled: row?.scheduled ?? 0, forecasts: row?.forecasts ?? 0 };
      });
    },
  };

  return { updates, uploads, events, runs, forecasts, predictions, teams, health };
}
