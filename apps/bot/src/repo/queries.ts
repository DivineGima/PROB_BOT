/**
 * Read-only queries for the bot commands (architecture 3, sections 6.5 and 6.10, ADR-049).
 *
 * READ-ONLY BY CONSTRUCTION: every statement in this file is a SELECT, with bound parameters, and
 * each method is one call or one batch. `scripts/check-sql-locality.mjs` fails CI if a write
 * statement or a `.run(` ever appears here (invariant 9, section 5.7).
 *
 * The verdict read selects no probability column, so `/fixtures` cannot show one (ADR-050).
 */
import type { ForecastVerdict, ModelName } from "./index";
import {
  ACTIVE_RUN_ID,
  type ActivePointer,
  COVERAGE_SQL,
  type CoverageSqlRow,
  POINTER_SQL,
  type PointerSqlRow,
  toPointer,
} from "./sql";

// -- alert definitions (section 6.10), pinned against Python and the watchdog by a repo check --------

/** Kinds `footy alert --flush` delivers besides level 'alert' (`_WARN_ALERT_KINDS` in ops.py). */
export const FLUSH_ALERT_KINDS = ["unmapped_team", "canonical_update_needed"] as const;
/** Source anomalies are alerts too (`kind LIKE 'anomaly\_%'` in ops.py). */
export const FLUSH_ALERT_PREFIX = "anomaly_";
/** The watchdog's findings; recorded only after Telegram accepted them (watchdog/index.ts). */
export const WATCHDOG_FINDING_KINDS = [
  "watchdog_no_active_run",
  "watchdog_stale_run",
  "watchdog_no_forecasts",
  "watchdog_stuck_upload",
] as const;
/** Events that mean an alert could not be sent (`BOT_PROBLEM_KINDS` in health.py). */
export const ALERT_PATH_KINDS = [
  "bot_token_missing",
  "alert_chat_invalid",
  "alert_send_failed",
  "watchdog_failed",
] as const;
/** The nightly steps `/status` reports (`job_runs.kind`). */
export const NIGHTLY_JOB_KINDS = ["ingest", "score", "fit", "publish", "healthcheck"] as const;

const marks = (from: number, n: number): string =>
  Array.from({ length: n }, (_, i) => `?${from + i}`).join(", ");

/** The flush predicate with its kinds bound from parameter `?from` on (2 kinds, then the prefix). */
const flushPredicate = (from: number): string =>
  `(level = 'alert' OR kind IN (${marks(from, FLUSH_ALERT_KINDS.length)}) OR kind LIKE ?${
    from + FLUSH_ALERT_KINDS.length
  } ESCAPE '\\')`;
const watchdogPredicate = (from: number): string =>
  `(source = 'watchdog' AND kind IN (${marks(from, WATCHDOG_FINDING_KINDS.length)}))`;
/** `anomaly\_%`: the underscore is literal, as in ops.py. */
const ANOMALY_LIKE = `${FLUSH_ALERT_PREFIX.slice(0, -1)}\\_%`;
/** Parameters 2.. of an alert query: the flush kinds, the anomaly pattern, the watchdog kinds. */
const ALERT_BINDS: readonly string[] = [
  ...FLUSH_ALERT_KINDS,
  ANOMALY_LIKE,
  ...WATCHDOG_FINDING_KINDS,
];
const FLUSH_FROM = 2;
const WATCHDOG_FROM = FLUSH_FROM + FLUSH_ALERT_KINDS.length + 1;
const ALERT_WHERE = `at >= ?1 AND (${flushPredicate(FLUSH_FROM)} OR ${watchdogPredicate(WATCHDOG_FROM)})`;

// -- result types -------------------------------------------------------------------------------------

export interface RunSummary extends ActivePointer {
  models: Array<{ model: ModelName; status: "ok" | "failed" }>;
}

export interface JobRow {
  kind: string;
  status: string;
  startedAt: string;
  finishedAt: string | null;
}

export interface StatusSnapshot {
  run: RunSummary | null;
  jobs: JobRow[];
  coverage: Array<{ date: string; scheduled: number; forecasts: number }>;
  /** Flush alerts of the window not yet delivered (the nightly sends them). */
  alertsWaiting: number;
  /** Alert-path problem events of the window, by kind. */
  alertPath: Array<{ kind: string; n: number; last: string }>;
}

export interface AlertEventRow {
  at: string;
  kind: string;
  /** `delivered` / `waiting` for flush alerts; `watchdog` for findings the watchdog already sent. */
  state: "delivered" | "waiting" | "watchdog";
}

export interface AlertRead {
  rows: AlertEventRow[];
  total: number;
  waiting: number;
  byKind: Array<{ kind: string; n: number }>;
}

export interface VerdictRow {
  kickoffUtc: string | null;
  compCode: string;
  home: string;
  away: string;
  verdict: ForecastVerdict;
  detailJson: string;
}

export interface VerdictRead {
  runId: string;
  rows: VerdictRow[];
  /** Scheduled fixtures on that date with no forecast row in the active run (would be NO_FORECAST). */
  unforecast: number;
}

export interface LoggedRow {
  compCode: string;
  home: string;
  away: string;
  kickoffUtc: string;
  p1x2: [number, number, number];
  overs: number[];
  weightsJson: string;
  status: "pending" | "scored" | "void";
  voidReason: string | null;
  goals: [number, number] | null;
  createdAt: string;
}

export interface SettledRow {
  compCode: string;
  home: string;
  away: string;
  matchDate: string;
  status: "scored" | "void";
  voidReason: string | null;
  goals: [number, number] | null;
  p1x2: [number, number, number];
  rps1x2: number | null;
}

export interface PendingRow {
  compCode: string;
  home: string;
  away: string;
  kickoffUtc: string;
}

export interface SnapshotRow {
  createdAt: string;
  windowFrom: string;
  windowTo: string;
  nScored: number;
  metricsJson: string;
  runId: string | null;
}

export interface UploadRow {
  uploadId: number;
  receivedAt: string;
  status: "received" | "rejected" | "processed" | "failed";
  runDateUtc: string | null;
  nMatchesIn: number | null;
  nExcludedIn: number | null;
  nPublished: number | null;
  nOmitted: number | null;
  nDuplicate: number | null;
  runId: string | null;
  errorCode: string | null;
}

export interface TeamRef {
  id: number;
  name: string;
  homeComp: string | null;
  active: boolean;
}

export interface TeamCandidates {
  teams: TeamRef[];
  /** Teams whose stored alias (any source) equals the normalised text. */
  aliasTeamIds: number[];
}

export interface TeamFormRow {
  nTraining: number;
  nSeason: number;
  seasonGf: number | null;
  seasonGa: number | null;
  l10N: number;
  l10Gf: number | null;
  l10Ga: number | null;
  latestMatchDate: string | null;
}

export interface NextFixture {
  matchDate: string;
  kickoffUtc: string | null;
  compCode: string;
  home: string;
  away: string;
  verdict: ForecastVerdict;
}

export interface TeamFormRead {
  runId: string;
  form: TeamFormRow | null;
  nextFixture: NextFixture | null;
}

export interface QueryRepository {
  /** `/status`: run summary, newest nightly steps, coverage, waiting alerts, alert-path events. */
  statusSnapshot(dates: string[], alertsSince: string, pathSince: string): Promise<StatusSnapshot>;
  /** `/alerts`: alert events since `since`, newest first. */
  alertEvents(since: string, limit: number): Promise<AlertRead>;
  /** `/fixtures`: the active run's verdicts for a date (no probabilities); null without a run. */
  forecastVerdicts(date: string): Promise<VerdictRead | null>;
  /** `/logged`: the predictions of a fixture date, with names, result and logging time. */
  loggedForDate(date: string): Promise<LoggedRow[]>;
  /** `/results`: the newest settled (scored or void) predictions by kickoff. */
  settled(limit: number): Promise<SettledRow[]>;
  /** `/pending`: predictions waiting for a result, soonest first, and how many there are. */
  pending(limit: number): Promise<{ rows: PendingRow[]; total: number }>;
  /** `/report`: the newest calibration snapshot. */
  latestSnapshot(): Promise<SnapshotRow | null>;
  /** `/last`: the newest upload. */
  latestUpload(): Promise<UploadRow | null>;
  /** `/team`: every team, and the teams whose alias equals the normalised text. */
  teamCandidates(aliasNorm: string): Promise<TeamCandidates>;
  /** `/team`: the active run's form row and the team's next stored fixture; null without a run. */
  teamForm(teamId: number, fromDate: string): Promise<TeamFormRead | null>;
}

// -- implementation -----------------------------------------------------------------------------------

const TEAM_NAMES = `JOIN teams h ON h.team_id = p.home_team_id JOIN teams a ON a.team_id = p.away_team_id`;

type Row = Record<string, unknown>;
const rowsOf = (result: D1Result | undefined): Row[] => (result?.results ?? []) as Row[];
const num = (v: unknown): number | null => (typeof v === "number" ? v : null);
const str = (v: unknown): string | null => (typeof v === "string" ? v : null);
const goalsOf = (r: Row): [number, number] | null => {
  const h = num(r.goals_home);
  const a = num(r.goals_away);
  return h === null || a === null ? null : [h, a];
};

export function createQueries(db: D1Database): QueryRepository {
  return {
    async statusSnapshot(dates, alertsSince, pathSince) {
      const results = await db.batch([
        db.prepare(POINTER_SQL),
        db.prepare(
          `SELECT model, status FROM model_params WHERE run_id = ${ACTIVE_RUN_ID} ORDER BY model`,
        ),
        db
          .prepare(
            `SELECT kind, status, started_at, finished_at FROM job_runs
             WHERE job_id IN (SELECT MAX(job_id) FROM job_runs
                              WHERE kind IN (${marks(1, NIGHTLY_JOB_KINDS.length)}) GROUP BY kind)`,
          )
          .bind(...NIGHTLY_JOB_KINDS),
        db
          .prepare(
            `SELECT COUNT(*) AS n FROM events
             WHERE at >= ?1 AND delivered_at IS NULL AND ${flushPredicate(FLUSH_FROM)}`,
          )
          .bind(alertsSince, ...FLUSH_ALERT_KINDS, ANOMALY_LIKE),
        db
          .prepare(
            `SELECT kind, COUNT(*) AS n, MAX(at) AS last FROM events
             WHERE at >= ?1 AND kind IN (${marks(2, ALERT_PATH_KINDS.length)})
             GROUP BY kind ORDER BY kind`,
          )
          .bind(pathSince, ...ALERT_PATH_KINDS),
        ...dates.map((date) => db.prepare(COVERAGE_SQL).bind(date)),
      ]);
      const pointer = toPointer(rowsOf(results[0])[0] as PointerSqlRow | undefined);
      const run: RunSummary | null = pointer
        ? {
            ...pointer,
            models: rowsOf(results[1]).map((r) => ({
              model: r.model as ModelName,
              status: r.status as "ok" | "failed",
            })),
          }
        : null;
      const order = NIGHTLY_JOB_KINDS as readonly string[];
      const jobs = rowsOf(results[2])
        .map((r) => ({
          kind: String(r.kind),
          status: String(r.status),
          startedAt: String(r.started_at),
          finishedAt: str(r.finished_at),
        }))
        .sort((x, y) => order.indexOf(x.kind) - order.indexOf(y.kind));
      return {
        run,
        jobs,
        alertsWaiting: num(rowsOf(results[3])[0]?.n) ?? 0,
        alertPath: rowsOf(results[4]).map((r) => ({
          kind: String(r.kind),
          n: num(r.n) ?? 0,
          last: String(r.last),
        })),
        coverage: dates.map((date, i) => {
          const row = rowsOf(results[5 + i])[0] as CoverageSqlRow | undefined;
          return { date, scheduled: row?.scheduled ?? 0, forecasts: row?.forecasts ?? 0 };
        }),
      };
    },

    async alertEvents(since, limit) {
      const [rowsResult, countResult, kindResult] = await db.batch([
        db
          .prepare(
            `SELECT at, kind, source, delivered_at FROM events WHERE ${ALERT_WHERE}
             ORDER BY at DESC, event_id DESC LIMIT ?${2 + ALERT_BINDS.length}`,
          )
          .bind(since, ...ALERT_BINDS, limit),
        db
          .prepare(
            `SELECT COUNT(*) AS total,
               COALESCE(SUM(CASE WHEN source <> 'watchdog' AND delivered_at IS NULL THEN 1 ELSE 0 END), 0)
                 AS waiting
             FROM events WHERE ${ALERT_WHERE}`,
          )
          .bind(since, ...ALERT_BINDS),
        db
          .prepare(
            `SELECT kind, COUNT(*) AS n FROM events WHERE ${ALERT_WHERE}
             GROUP BY kind ORDER BY n DESC, kind`,
          )
          .bind(since, ...ALERT_BINDS),
      ]);
      const counts = rowsOf(countResult)[0] ?? {};
      return {
        rows: rowsOf(rowsResult).map((r) => ({
          at: String(r.at),
          kind: String(r.kind),
          state:
            r.source === "watchdog" &&
            (WATCHDOG_FINDING_KINDS as readonly unknown[]).includes(r.kind)
              ? "watchdog"
              : r.delivered_at
                ? "delivered"
                : "waiting",
        })),
        total: num(counts.total) ?? 0,
        waiting: num(counts.waiting) ?? 0,
        byKind: rowsOf(kindResult).map((r) => ({ kind: String(r.kind), n: num(r.n) ?? 0 })),
      };
    },

    async forecastVerdicts(date) {
      const [pointerResult, rowsResult, missingResult] = await db.batch([
        db.prepare(POINTER_SQL),
        db
          .prepare(
            `SELECT p.kickoff_utc, p.comp_code, p.verdict, p.detail_json,
               h.canonical_name AS home, a.canonical_name AS away
             FROM fixture_forecasts p ${TEAM_NAMES}
             WHERE p.run_id = ${ACTIVE_RUN_ID} AND p.match_date = ?1
             ORDER BY p.kickoff_utc, p.comp_code, h.canonical_name`,
          )
          .bind(date),
        db
          .prepare(
            `SELECT COUNT(*) AS n FROM matches m
             WHERE m.match_date = ?1 AND m.status IN ('SCHEDULED', 'TIMED')
               AND NOT EXISTS (SELECT 1 FROM fixture_forecasts f
                 WHERE f.run_id = ${ACTIVE_RUN_ID}
                   AND f.fixture_key = m.match_date || '|' || m.comp_code || '|' ||
                       m.home_team_id || '|' || m.away_team_id)`,
          )
          .bind(date),
      ]);
      const pointer = toPointer(rowsOf(pointerResult)[0] as PointerSqlRow | undefined);
      if (!pointer) return null;
      return {
        runId: pointer.runId,
        rows: rowsOf(rowsResult).map((r) => ({
          kickoffUtc: str(r.kickoff_utc),
          compCode: String(r.comp_code),
          home: String(r.home),
          away: String(r.away),
          verdict: r.verdict as ForecastVerdict,
          detailJson: String(r.detail_json ?? "{}"),
        })),
        unforecast: num(rowsOf(missingResult)[0]?.n) ?? 0,
      };
    },

    async loggedForDate(date) {
      const { results } = await db
        .prepare(
          `SELECT p.comp_code, p.kickoff_utc, p.p_home, p.p_draw, p.p_away, p.p_over_05,
             p.p_over_15, p.p_over_25, p.p_over_35, p.p_over_45, p.p_over_55, p.weights_json,
             p.status, p.void_reason, p.goals_home, p.goals_away, p.created_at,
             h.canonical_name AS home, a.canonical_name AS away
           FROM predictions p ${TEAM_NAMES}
           WHERE p.match_date = ?1 ORDER BY p.kickoff_utc, p.pred_id`,
        )
        .bind(date)
        .all<Row>();
      return results.map((r) => ({
        compCode: String(r.comp_code),
        home: String(r.home),
        away: String(r.away),
        kickoffUtc: String(r.kickoff_utc),
        p1x2: [Number(r.p_home), Number(r.p_draw), Number(r.p_away)],
        overs: [r.p_over_05, r.p_over_15, r.p_over_25, r.p_over_35, r.p_over_45, r.p_over_55].map(
          Number,
        ),
        weightsJson: String(r.weights_json ?? "{}"),
        status: r.status as LoggedRow["status"],
        voidReason: str(r.void_reason),
        goals: goalsOf(r),
        createdAt: String(r.created_at),
      }));
    },

    async settled(limit) {
      const { results } = await db
        .prepare(
          `SELECT p.comp_code, p.match_date, p.status, p.void_reason, p.goals_home, p.goals_away,
             p.p_home, p.p_draw, p.p_away, p.rps_1x2,
             h.canonical_name AS home, a.canonical_name AS away
           FROM predictions p ${TEAM_NAMES}
           WHERE p.status IN ('scored', 'void')
           ORDER BY p.kickoff_utc DESC, p.pred_id DESC LIMIT ?1`,
        )
        .bind(limit)
        .all<Row>();
      return results.map((r) => ({
        compCode: String(r.comp_code),
        home: String(r.home),
        away: String(r.away),
        matchDate: String(r.match_date),
        status: r.status as SettledRow["status"],
        voidReason: str(r.void_reason),
        goals: goalsOf(r),
        p1x2: [Number(r.p_home), Number(r.p_draw), Number(r.p_away)],
        rps1x2: num(r.rps_1x2),
      }));
    },

    async pending(limit) {
      const [rowsResult, countResult] = await db.batch([
        db
          .prepare(
            `SELECT p.comp_code, p.kickoff_utc, h.canonical_name AS home, a.canonical_name AS away
             FROM predictions p ${TEAM_NAMES}
             WHERE p.status = 'pending' ORDER BY p.kickoff_utc, p.pred_id LIMIT ?1`,
          )
          .bind(limit),
        db.prepare("SELECT COUNT(*) AS n FROM predictions WHERE status = 'pending'"),
      ]);
      return {
        rows: rowsOf(rowsResult).map((r) => ({
          compCode: String(r.comp_code),
          home: String(r.home),
          away: String(r.away),
          kickoffUtc: String(r.kickoff_utc),
        })),
        total: num(rowsOf(countResult)[0]?.n) ?? 0,
      };
    },

    async latestSnapshot() {
      const r = await db
        .prepare(
          `SELECT created_at, window_from, window_to, n_scored, metrics_json, run_id
           FROM calibration_snapshots ORDER BY snapshot_id DESC LIMIT 1`,
        )
        .first<Row>();
      if (!r) return null;
      return {
        createdAt: String(r.created_at),
        windowFrom: String(r.window_from),
        windowTo: String(r.window_to),
        nScored: num(r.n_scored) ?? 0,
        metricsJson: String(r.metrics_json ?? "{}"),
        runId: str(r.run_id),
      };
    },

    async latestUpload() {
      const r = await db
        .prepare(
          `SELECT upload_id, received_at, status, run_date_utc, n_matches_in, n_excluded_in,
             n_published, n_omitted, n_duplicate, run_id, error_code
           FROM uploads ORDER BY upload_id DESC LIMIT 1`,
        )
        .first<Row>();
      if (!r) return null;
      return {
        uploadId: Number(r.upload_id),
        receivedAt: String(r.received_at),
        status: r.status as UploadRow["status"],
        runDateUtc: str(r.run_date_utc),
        nMatchesIn: num(r.n_matches_in),
        nExcludedIn: num(r.n_excluded_in),
        nPublished: num(r.n_published),
        nOmitted: num(r.n_omitted),
        nDuplicate: num(r.n_duplicate),
        runId: str(r.run_id),
        errorCode: str(r.error_code),
      };
    },

    async teamCandidates(aliasNorm) {
      const [teamResult, aliasResult] = await db.batch([
        db.prepare("SELECT team_id, canonical_name, home_comp, active FROM teams ORDER BY team_id"),
        db
          .prepare("SELECT DISTINCT team_id FROM team_aliases WHERE alias_norm = ?1")
          .bind(aliasNorm),
      ]);
      return {
        teams: rowsOf(teamResult).map((r) => ({
          id: Number(r.team_id),
          name: String(r.canonical_name),
          homeComp: str(r.home_comp),
          active: r.active === 1,
        })),
        aliasTeamIds: rowsOf(aliasResult).map((r) => Number(r.team_id)),
      };
    },

    async teamForm(teamId, fromDate) {
      const [pointerResult, formResult, nextResult] = await db.batch([
        db.prepare(POINTER_SQL),
        db
          .prepare(
            `SELECT n_training, n_season, season_gf, season_ga, l10_n, l10_gf, l10_ga,
               latest_match_date
             FROM team_form WHERE run_id = ${ACTIVE_RUN_ID} AND team_id = ?1`,
          )
          .bind(teamId),
        db
          .prepare(
            `SELECT p.match_date, p.kickoff_utc, p.comp_code, p.verdict,
               h.canonical_name AS home, a.canonical_name AS away
             FROM fixture_forecasts p ${TEAM_NAMES}
             WHERE p.run_id = ${ACTIVE_RUN_ID} AND p.match_date >= ?2
               AND (p.home_team_id = ?1 OR p.away_team_id = ?1)
             ORDER BY p.match_date, p.kickoff_utc LIMIT 1`,
          )
          .bind(teamId, fromDate),
      ]);
      const pointer = toPointer(rowsOf(pointerResult)[0] as PointerSqlRow | undefined);
      if (!pointer) return null;
      const f = rowsOf(formResult)[0];
      const n = rowsOf(nextResult)[0];
      return {
        runId: pointer.runId,
        form: f
          ? {
              nTraining: num(f.n_training) ?? 0,
              nSeason: num(f.n_season) ?? 0,
              seasonGf: num(f.season_gf),
              seasonGa: num(f.season_ga),
              l10N: num(f.l10_n) ?? 0,
              l10Gf: num(f.l10_gf),
              l10Ga: num(f.l10_ga),
              latestMatchDate: str(f.latest_match_date),
            }
          : null,
        nextFixture: n
          ? {
              matchDate: String(n.match_date),
              kickoffUtc: str(n.kickoff_utc),
              compCode: String(n.comp_code),
              home: String(n.home),
              away: String(n.away),
              verdict: n.verdict as ForecastVerdict,
            }
          : null,
      };
    },
  };
}
