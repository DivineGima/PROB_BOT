import { DEFAULT_STALE_HOURS, MAX_FILE_BYTES } from "../config/constants";
import { ERROR_CODES, type ErrorCode, type OmissionCode } from "../config/errors";
import {
  type ERROR_TEXT,
  type OmittedMatch,
  type PublishedMatch,
  renderError,
  renderReply,
  USAGE_HINT,
} from "../format";
import { countExclusions, guardDocument, parseScreenerFile, timeCheck } from "../intake";
import type { ScreenerMatch } from "../intake/schema";
import type {
  ActivePointer,
  ForecastRow,
  NewOmission,
  NewPrediction,
  Repositories,
  StoredPrediction,
  UploadFinalisation,
} from "../repo";
import type { TelegramClient } from "../telegram/client";
import type { DocumentFields } from "../telegram/update";

/**
 * The upload pipeline (architecture sections 7.10 and 8.7, ADR-042): intake, team resolution, a
 * lookup of the forecasts the nightly job stored, an insert-or-ignore copy into the prediction log,
 * and only then the reply. The Worker computes no probability: a match with no stored forecast is
 * omitted as NO_FORECAST.
 *
 * Order is part of the contract: the `uploads` row is written as `received` before any download
 * (ADR-029), predictions are persisted before anything is sent, and every failure after the
 * acknowledgement ends in either a reply or a `received` row the watchdog will find.
 */

export interface UploadDeps {
  repos: Repositories;
  /** Null when the bot token is missing or malformed: nothing can be sent. */
  telegram: TelegramClient | null;
  now: () => Date;
  /** Short random id shown to Divine for an unexpected error and stored in the event. */
  newErrorId: () => string;
}

export interface UploadRequest {
  updateId: number;
  chatId: number;
  document: DocumentFields;
}

export interface UploadOutcome {
  outcome: string;
  errorCode?: ErrorCode;
  /** Counts for the request log (`n_*`). */
  counts?: Record<string, number>;
}

const MODEL_ORDER = ["dc", "pi", "bp"];
const hourKey = (now: Date): string => now.toISOString().slice(0, 13);

/** The same identity the nightly job uses (section 8.7). */
export function fixtureKey(
  matchDate: string,
  comp: string,
  homeTeamId: number,
  awayTeamId: number,
): string {
  return `${matchDate}|${comp}|${homeTeamId}|${awayTeamId}`;
}

function parseObject(text: string | null | undefined): Record<string, unknown> {
  try {
    const value: unknown = JSON.parse(text ?? "{}");
    return typeof value === "object" && value !== null && !Array.isArray(value)
      ? (value as Record<string, unknown>)
      : {};
  } catch {
    return {};
  }
}

function weightsOf(weightsJson: string): Array<[string, number]> {
  const entries = Object.entries(parseObject(weightsJson)).filter(
    (entry): entry is [string, number] => typeof entry[1] === "number",
  );
  return entries.sort(([a], [b]) => MODEL_ORDER.indexOf(a) - MODEL_ORDER.indexOf(b));
}

/** A short, content-free reason for a forecast that was not ok (numbers come from our own table). */
function verdictNote(detailJson: string): string | undefined {
  const drift = parseObject(detailJson).drift as Record<string, unknown> | undefined;
  if (!drift) return undefined;
  const notes: string[] = [];
  for (const side of ["home", "away"] as const) {
    const team = drift[side] as Record<string, unknown> | undefined;
    if (!team || team.status === "ok") continue;
    const reason = typeof team.reason === "string" ? team.reason : String(team.status);
    const moved = [team.d_gf, team.d_ga].filter((v): v is number => typeof v === "number");
    const detail =
      team.status === "DRIFT" && moved.length
        ? ` moved ${Math.max(...moved).toFixed(2)} vs limit ${String(team.threshold)}`
        : typeof team.n_training === "number"
          ? ` (${team.n_training} matches)`
          : "";
    notes.push(`${side}: ${reason}${detail}`);
  }
  return notes.length ? notes.join("; ") : undefined;
}

async function sha256Bytes(bytes: Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export async function sendUsageHint(deps: UploadDeps, chatId: number): Promise<UploadOutcome> {
  if (!deps.telegram) return { outcome: "no_telegram_client" };
  const sent = await deps.telegram.send(chatId, USAGE_HINT);
  return { outcome: sent.ok ? "usage_hint" : "usage_hint_failed" };
}

export async function handleDocument(
  deps: UploadDeps,
  request: UploadRequest,
): Promise<UploadOutcome> {
  const state: { uploadId: number | null } = { uploadId: null };
  try {
    return await run(deps, request, (id) => {
      state.uploadId = id;
    });
  } catch {
    // Unexpected failure after the acknowledgement: one reply with an id, one event, the upload
    // closed as failed if we got that far (otherwise the `received` row is the watchdog's signal).
    const errorId = deps.newErrorId();
    await safely(() =>
      deps.repos.events.record({
        level: "error",
        source: "bot",
        kind: "internal_error",
        detail: { error_id: errorId },
      }),
    );
    if (state.uploadId !== null) {
      const id = state.uploadId;
      await safely(() =>
        deps.repos.uploads.finalise(id, { status: "failed", errorCode: ERROR_CODES.E_INTERNAL }),
      );
    }
    if (deps.telegram) {
      const telegram = deps.telegram;
      await safely(() => telegram.send(request.chatId, `Internal error, id=${errorId}`));
    }
    return { outcome: "internal_error", errorCode: ERROR_CODES.E_INTERNAL };
  }
}

async function safely(action: () => Promise<unknown>): Promise<void> {
  try {
    await action();
  } catch {
    // Best effort only: the original failure is what matters.
  }
}

async function run(
  deps: UploadDeps,
  request: UploadRequest,
  setUploadId: (id: number) => void,
): Promise<UploadOutcome> {
  const { repos, telegram } = deps;
  const { document } = request;
  const now = deps.now();

  const uploadId = await repos.uploads.record({
    updateId: request.updateId,
    ...(document.fileUniqueId !== undefined ? { tgFileUniqueId: document.fileUniqueId } : {}),
    ...(document.fileSize !== undefined ? { sizeBytes: document.fileSize } : {}),
  });
  setUploadId(uploadId);

  if (!telegram) {
    await repos.events.record({
      level: "error",
      source: "bot",
      kind: "bot_token_missing",
      dedupeKey: `bot_token_missing:${hourKey(now)}`,
    });
    await repos.uploads.finalise(uploadId, { status: "failed", errorCode: ERROR_CODES.E_INTERNAL });
    return { outcome: "no_telegram_client", errorCode: ERROR_CODES.E_INTERNAL };
  }

  /** Persist the final state first, then tell Divine (persist, then reply). */
  const finishWithError = async (
    code: keyof typeof ERROR_TEXT,
    status: "rejected" | "failed",
    detail: string[] = [],
  ): Promise<UploadOutcome> => {
    await repos.uploads.finalise(uploadId, { status, errorCode: code });
    await telegram.send(request.chatId, renderError(code, detail));
    return { outcome: status === "rejected" ? "rejected" : "failed", errorCode: code };
  };

  const guard = guardDocument({
    ...(document.fileName !== undefined ? { fileName: document.fileName } : {}),
    ...(document.mimeType !== undefined ? { mimeType: document.mimeType } : {}),
    ...(document.fileSize !== undefined ? { fileSize: document.fileSize } : {}),
  });
  if (!guard.ok) return finishWithError(guard.error.code as keyof typeof ERROR_TEXT, "rejected");

  const file = await telegram.getFile(document.fileId);
  if (!file.ok) return finishWithError(ERROR_CODES.E_DOWNLOAD_FAILED, "failed");
  if (file.value.size !== null && file.value.size > MAX_FILE_BYTES) {
    return finishWithError(ERROR_CODES.E_TOO_LARGE, "rejected");
  }
  const bytes = await telegram.download(file.value.filePath, MAX_FILE_BYTES);
  if (!bytes.ok) {
    return bytes.error.kind === "too_large"
      ? finishWithError(ERROR_CODES.E_TOO_LARGE, "rejected")
      : finishWithError(ERROR_CODES.E_DOWNLOAD_FAILED, "failed");
  }

  const parsed = parseScreenerFile(bytes.value);
  if (!parsed.ok) {
    return finishWithError(
      parsed.error.code as keyof typeof ERROR_TEXT,
      "rejected",
      parsed.error.detail,
    );
  }
  const screener = parsed.value;
  const fileSha256 = await sha256Bytes(bytes.value);
  const runDate = screener.run_date_utc;

  const [teamIds, read, existing] = await Promise.all([
    repos.teams.resolveCanonical(screener.matches.flatMap((m) => [m.home, m.away])),
    repos.forecasts.readActiveForDate(runDate),
    repos.predictions.findByDate(runDate),
  ]);

  const pointer = read.pointer;
  if (!pointer) {
    await repos.events.record({
      level: "error",
      source: "bot",
      kind: "no_run",
      dedupeKey: `no_run:${hourKey(now)}`,
    });
    return finishWithError(ERROR_CODES.E_NO_RUN, "failed");
  }

  const forecastByKey = new Map<string, ForecastRow>(read.forecasts.map((f) => [f.fixtureKey, f]));
  const existingByKey = new Map<string, StoredPrediction>(existing.map((p) => [p.fixtureKey, p]));
  const seenKeys = new Set<string>();
  const usedLabels = new Set<string>();
  const fileLabels = new Set(screener.matches.map((x) => x.match_id));

  const created: NewPrediction[] = [];
  const omissions: NewOmission[] = [];
  const omitted: OmittedMatch[] = [];
  /** Published matches in file order; `key` ties a view to the stored row after the insert. */
  const plan: Array<{ key: string; comp: string; home: string; away: string; fresh: boolean }> = [];

  for (const m of screener.matches) {
    const omit = (reason: OmissionCode, note?: string, label = m.match_id) => {
      omissions.push({ label, reason, ...(note ? { detail: { note } } : {}) });
      omitted.push({
        comp: m.competition,
        home: m.home,
        away: m.away,
        reason,
        ...(note ? { note } : {}),
      });
    };

    if (usedLabels.has(m.match_id)) {
      // Omission labels are unique per upload: a repeated match_id gets the next free numbered
      // label, which cannot collide with another match that really has that id.
      let n = 2;
      while (usedLabels.has(`${m.match_id}#${n}`) || fileLabels.has(`${m.match_id}#${n}`)) n++;
      const label = `${m.match_id}#${n}`;
      usedLabels.add(label);
      omit("DUPLICATE_PAIR", "the match_id is repeated in the file", label);
      continue;
    }
    usedLabels.add(m.match_id);

    const homeId = teamIds.get(m.home);
    const awayId = teamIds.get(m.away);
    const matchDate = m.kickoff_utc.slice(0, 10);

    // A fixture that is already logged is shown from the log, whatever the clock says now.
    if (homeId !== undefined && awayId !== undefined && matchDate === runDate) {
      const key = fixtureKey(matchDate, m.competition, homeId, awayId);
      if (seenKeys.has(key)) {
        omit("DUPLICATE_PAIR", "the same fixture is listed twice");
        continue;
      }
      if (existingByKey.has(key)) {
        seenKeys.add(key);
        plan.push({ key, comp: m.competition, home: m.home, away: m.away, fresh: false });
        continue;
      }
    }

    const late = timeCheck(m, runDate, now);
    if (late) {
      omit(late);
      continue;
    }
    if (homeId === undefined || awayId === undefined) {
      const unknown = [homeId === undefined ? "home" : null, awayId === undefined ? "away" : null];
      omit(
        "UNMAPPED_TEAM",
        `${unknown.filter(Boolean).join(" and ")} team not in the canonical list`,
      );
      continue;
    }
    const key = fixtureKey(matchDate, m.competition, homeId, awayId);
    if (seenKeys.has(key)) {
      omit("DUPLICATE_PAIR", "the same fixture is listed twice");
      continue;
    }
    seenKeys.add(key);

    const forecast = forecastByKey.get(key);
    if (!forecast) {
      omit("NO_FORECAST");
      continue;
    }
    if (
      forecast.verdict !== "ok" ||
      !forecast.p1x2 ||
      !forecast.overs ||
      !forecast.totalJson ||
      !forecast.modelsJson ||
      !forecast.weightsJson ||
      !forecast.baselineJson
    ) {
      omit(
        forecast.verdict === "ok" ? "NO_MODEL" : forecast.verdict,
        verdictNote(forecast.detailJson),
      );
      continue;
    }

    created.push(newPrediction(m, key, forecast, forecast.p1x2, forecast.overs, homeId, awayId));
    plan.push({ key, comp: m.competition, home: m.home, away: m.away, fresh: true });
  }

  const finalisation: UploadFinalisation = {
    status: "processed",
    runDateUtc: runDate,
    schemaVersion: 1,
    nMatchesIn: screener.matches.length,
    nExcludedIn: screener.excluded.length,
    nPublished: plan.length,
    nOmitted: omissions.length,
    nDuplicate: plan.filter((p) => !p.fresh).length,
    runId: pointer.runId,
    fileSha256,
  };
  // ONE batch: predictions (first one wins), omissions, the upload closed.
  await repos.uploads.commit({
    uploadId,
    runId: pointer.runId,
    predictions: created,
    omissions,
    finalisation,
  });

  // Render from what is STORED, so the reply can never differ from the log (also under a race).
  const stored = created.length > 0 ? await repos.predictions.findByDate(runDate) : existing;
  const storedByKey = new Map(stored.map((p) => [p.fixtureKey, p]));
  const published: PublishedMatch[] = [];
  for (const item of plan) {
    const row = storedByKey.get(item.key);
    if (!row) throw new Error("a prediction that was just inserted cannot be read back");
    published.push({
      comp: item.comp,
      home: item.home,
      away: item.away,
      kickoffUtc: row.kickoffUtc,
      p1x2: row.p1x2,
      overs: row.overs,
      weights: weightsOf(row.weightsJson),
      alreadyLogged: !item.fresh || row.uploadId !== uploadId,
    });
  }

  const banners = await bannersFor(deps, pointer, read.runHasForecasts, now);
  const messages = renderReply({
    runDateUtc: runDate,
    runId: pointer.runId,
    dataCutoff: pointer.dataCutoffUtc,
    published,
    omitted,
    excluded: countExclusions(screener.excluded),
    banners,
    hasUcl: published.some((p) => p.comp === "UCL"),
  });

  let sentAll = true;
  for (const text of messages) {
    const sent = await telegram.send(request.chatId, text);
    if (!sent.ok) {
      sentAll = false;
      await safely(() =>
        repos.events.record({
          level: "warn",
          source: "bot",
          kind: "reply_failed",
          detail: {
            upload_id: uploadId,
            failure: sent.error.kind,
            status: sent.error.status ?? null,
          },
        }),
      );
      break; // a re-upload is answered from the log with identical numbers
    }
  }

  return {
    outcome: sentAll ? "processed" : "reply_failed",
    counts: {
      n_published: plan.length,
      n_omitted: omissions.length,
      n_duplicate: finalisation.nDuplicate ?? 0,
      n_messages: messages.length,
    },
  };
}

function newPrediction(
  m: ScreenerMatch,
  key: string,
  forecast: ForecastRow,
  p1x2: [number, number, number],
  overs: number[],
  homeId: number,
  awayId: number,
): NewPrediction {
  return {
    fixtureKey: key,
    label: m.match_id,
    compCode: m.competition,
    matchDate: m.kickoff_utc.slice(0, 10),
    kickoffUtc: m.kickoff_utc,
    homeTeamId: homeId,
    awayTeamId: awayId,
    p1x2,
    overs,
    totalJson: forecast.totalJson as string,
    modelsJson: forecast.modelsJson as string,
    weightsJson: forecast.weightsJson as string,
    driftJson: forecast.detailJson,
    baselineJson: forecast.baselineJson as string,
    inputsJson: JSON.stringify({
      lineup_status: m.lineup_status,
      absences_home: m.absences_home,
      absences_away: m.absences_away,
      rest_days_home: m.rest_days_home,
      rest_days_away: m.rest_days_away,
      source_urls: m.source_urls,
    }),
  };
}

async function bannersFor(
  deps: UploadDeps,
  pointer: ActivePointer,
  runHasForecasts: boolean,
  now: Date,
): Promise<string[]> {
  const banners: string[] = [];
  const config = parseObject(pointer.configJson);
  const ensemble = parseObject(pointer.ensembleJson);

  const staleHours =
    typeof config.stale_hours === "number" ? config.stale_hours : DEFAULT_STALE_HOURS;
  const ageHours = (now.getTime() - Date.parse(pointer.activatedAt)) / 3_600_000;
  if (Number.isFinite(ageHours) && ageHours > staleHours) {
    banners.push(
      `STALE MODELS: the active run is ${Math.floor(ageHours)} h old (limit ${staleHours} h).`,
    );
    await safely(() =>
      deps.repos.events.record({
        level: "warn",
        source: "bot",
        kind: "stale_models",
        detail: { run_id: pointer.runId, age_hours: Math.floor(ageHours) },
        dedupeKey: `stale_models:${hourKey(now)}`,
      }),
    );
  }

  const attempted = Array.isArray(config.models) ? (config.models as unknown[]) : [];
  const weights = (ensemble.weights ?? {}) as Record<string, unknown>;
  for (const model of attempted) {
    if (typeof model === "string" && !(model in weights)) {
      banners.push(`Model ${model} unavailable in this run (it failed to fit).`);
    }
  }
  if (!runHasForecasts) {
    banners.push(
      "No forecasts are stored for this run, so every match is omitted: run fit and publish.",
    );
  }
  return banners;
}
