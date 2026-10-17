/**
 * The ONLY module in the Worker that touches D1 (architecture sections 6.5 and 6.9, locked
 * Database rule). Parameterised statements only; multi-statement work goes through `batch()`.
 * Stage 1 ships the skeleton: update dedupe, the upload record (inserted as `received` first,
 * ADR-029), events and, from Stage 4, the read of the active model run. Later stages add
 * prediction and team repositories here.
 */
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
}

export interface EventRepository {
  record(event: NewEvent): Promise<void>;
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

/** The run `active_run` points at, with every model row (section 8.6). */
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
   */
  readActive(): Promise<ActiveRun | null>;
  /** Only the pointer and run metadata (one small row); cheap enough for every request. */
  readPointer(): Promise<ActivePointer | null>;
  /**
   * The active run with its payloads verified, kept in memory while the pointer is unchanged:
   * each request costs one small read, and the payloads are fetched, hashed and kept only when
   * the active run changes. Runs are immutable once active (ADR-004), so a cached run never goes
   * stale while its `runId` and `activatedAt` are the same.
   */
  readActiveVerified(): Promise<VerifiedActiveRun | null>;
}

let verifiedCache: { key: string; value: VerifiedActiveRun } | null = null;

/** Forget the cached run (tests, or after an explicit rollback drill). */
export function clearActiveRunCache(): void {
  verifiedCache = null;
}

export interface Repositories {
  updates: UpdateRepository;
  uploads: UploadRepository;
  events: EventRepository;
  runs: RunRepository;
}

/** Lower-case hex SHA-256 of the text's UTF-8 bytes, the form `model_params.payload_sha256` uses. */
export async function sha256Hex(text: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** True only for an `ok` row whose stored hash matches its payload text (integrity on read). */
export async function payloadVerifies(params: ModelParams): Promise<boolean> {
  if (params.status !== "ok" || params.payloadJson === null || params.payloadSha256 === null) {
    return false;
  }
  return (await sha256Hex(params.payloadJson)) === params.payloadSha256;
}

const toIso = (date: Date): string => `${date.toISOString().slice(0, 19)}Z`;

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
      const outcome = await db
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
        )
        .run();
      return outcome.meta.changes === 1;
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
  };

  const readPointer = async (): Promise<ActivePointer | null> => {
    const row = await db
      .prepare(
        `SELECT r.run_id, r.data_cutoff_utc, r.config_json, r.ensemble_json, a.activated_at
         FROM active_run a JOIN model_runs r ON r.run_id = a.run_id
         WHERE a.id = 1`,
      )
      .first<{
        run_id: string;
        data_cutoff_utc: string | null;
        config_json: string | null;
        ensemble_json: string | null;
        activated_at: string;
      }>();
    if (!row) return null;
    return {
      runId: row.run_id,
      activatedAt: row.activated_at,
      dataCutoffUtc: row.data_cutoff_utc,
      configJson: row.config_json ?? "{}",
      ensembleJson: row.ensemble_json ?? "{}",
    };
  };

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

  return { updates, uploads, events, runs };
}
