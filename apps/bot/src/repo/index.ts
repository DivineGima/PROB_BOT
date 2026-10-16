/**
 * The ONLY module in the Worker that touches D1 (architecture sections 6.5 and 6.9, locked
 * Database rule). Parameterised statements only; multi-statement work goes through `batch()`.
 * Stage 1 ships the skeleton: update dedupe, the upload record (inserted as `received` first,
 * ADR-029) and events. Later stages add run/prediction/team repositories here.
 */
export type Clock = () => Date;

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

export interface Repositories {
  updates: UpdateRepository;
  uploads: UploadRepository;
  events: EventRepository;
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
      await db
        .prepare(
          `INSERT INTO events (at, level, source, kind, detail_json, dedupe_key)
           VALUES (?1, ?2, ?3, ?4, ?5, ?6)`,
        )
        .bind(
          toIso(clock()),
          event.level,
          event.source,
          event.kind,
          event.detail === undefined ? null : JSON.stringify(event.detail),
          event.dedupeKey ?? null,
        )
        .run();
    },
  };

  return { updates, uploads, events };
}
