import { alertChatId } from "../auth";
import {
  DEFAULT_STALE_HOURS,
  STUCK_UPLOAD_MINUTES,
  WATCHDOG_FORECAST_DAYS,
} from "../config/constants";
import type { Env } from "../config/env";
import { ERROR_CODES } from "../config/errors";
import type { Repositories } from "../repo";
import { type Sleep, type TelegramClient, telegramFromEnv } from "../telegram/client";

/**
 * The watchdog (architecture sections 9.2 and 10, ADR-015, ADR-029). The Worker's cron trigger runs it
 * every six hours. It asks the questions the nightly workflow cannot ask about itself, because the
 * workflow may never have started: is a model run published and fresh, does it hold forecasts for
 * today and tomorrow when fixtures are scheduled, and is an upload stuck (acknowledged, never answered).
 *
 * Each finding is sent to Divine once per 24 hours (an event with the key `alert:<key>` marks it).
 * The event is written only after Telegram accepted the message, so a failed send is retried at the
 * next run. Reads and one Telegram call per finding. The one write besides the events: once the
 * stuck-upload alert was accepted, those uploads are closed as `failed` (E_INTERNAL), so a single
 * silent upload is reported once instead of every day and no longer fails the nightly health check.
 */

export interface Finding {
  key: string;
  kind: string;
  text: string;
  /** Uploads to close as failed once this finding was sent (the stuck-upload finding only). */
  closeUploads?: number[];
}

export interface WatchdogDeps {
  repos: Repositories;
  telegram: TelegramClient | null;
  chatId: number | null;
  now: () => Date;
}

export interface WatchdogOutcome {
  findings: number;
  sent: number;
  skipped: number;
  failed: number;
}

const HOUR_MS = 3_600_000;
const isoDate = (d: Date): string => d.toISOString().slice(0, 10);
const hourKey = (d: Date): string => d.toISOString().slice(0, 13);

/** The run's stale limit from its `config_json` (also used by `/status`). */
export function staleHoursOf(configJson: string): number {
  try {
    const value = (JSON.parse(configJson) as { stale_hours?: unknown }).stale_hours;
    return typeof value === "number" && value > 0 ? value : DEFAULT_STALE_HOURS;
  } catch {
    return DEFAULT_STALE_HOURS;
  }
}

/** What is wrong right now. Pure over the repositories: no sending, no writing. */
export async function collectFindings(repos: Repositories, now: Date): Promise<Finding[]> {
  const findings: Finding[] = [];

  const pointer = await repos.runs.readPointer();
  if (!pointer) {
    findings.push({
      key: "no_active_run",
      kind: "watchdog_no_active_run",
      text: "No model run is published, so the bot cannot answer. Run fit and publish.",
    });
  } else {
    const activated = Date.parse(pointer.activatedAt);
    const limit = staleHoursOf(pointer.configJson);
    const ageHours = Number.isNaN(activated)
      ? Number.POSITIVE_INFINITY
      : (now.getTime() - activated) / HOUR_MS;
    if (ageHours > limit) {
      const age = Number.isFinite(ageHours) ? `${Math.floor(ageHours)} h old` : "of unreadable age";
      findings.push({
        key: "stale_run",
        kind: "watchdog_stale_run",
        text: `The active model run ${pointer.runId} is ${age} (limit ${limit} h). The nightly job did not publish. Check the nightly workflow.`,
      });
    }

    const dates = Array.from({ length: WATCHDOG_FORECAST_DAYS }, (_, i) =>
      isoDate(new Date(now.getTime() + i * 24 * HOUR_MS)),
    );
    const uncovered = (await repos.health.forecastCoverage(dates)).filter(
      (day) => day.scheduled > 0 && day.forecasts === 0,
    );
    if (uncovered.length > 0) {
      const days = uncovered.map((d) => `${d.date} (${d.scheduled} scheduled)`).join(", ");
      findings.push({
        key: "no_forecasts",
        kind: "watchdog_no_forecasts",
        text: `No forecasts are stored for ${days}, so every match would be answered NO_FORECAST. Run fit and publish.`,
      });
    }
  }

  const stuck = await repos.uploads.findStale(STUCK_UPLOAD_MINUTES);
  if (stuck.length > 0) {
    findings.push({
      key: "stuck_upload",
      kind: "watchdog_stuck_upload",
      text: `${stuck.length} upload(s) were acknowledged but never answered (oldest received ${stuck[0]?.receivedAt}). Send the file again.`,
      closeUploads: stuck.map((u) => u.uploadId),
    });
  }
  return findings;
}

/** Sends each new finding once a day. Never throws: a watchdog that crashes is a silent failure. */
export async function runWatchdog(deps: WatchdogDeps): Promise<WatchdogOutcome> {
  const { repos } = deps;
  const outcome: WatchdogOutcome = { findings: 0, sent: 0, skipped: 0, failed: 0 };
  let findings: Finding[];
  try {
    findings = await collectFindings(repos, deps.now());
  } catch {
    await repos.events
      .record({
        level: "error",
        source: "watchdog",
        kind: "watchdog_failed",
        dedupeKey: `watchdog_failed:${hourKey(deps.now())}`,
      })
      .catch(() => undefined);
    return { ...outcome, failed: 1 };
  }
  outcome.findings = findings.length;

  for (const finding of findings) {
    const dedupeKey = `alert:${finding.key}`;
    try {
      if (await repos.events.hasRecent(dedupeKey)) {
        outcome.skipped++;
        continue;
      }
      if (!deps.telegram || deps.chatId === null) {
        // Cannot tell anyone: leave the trace the nightly health check reports.
        await repos.events.record({
          level: "error",
          source: "watchdog",
          kind: deps.telegram ? "alert_chat_invalid" : "bot_token_missing",
          detail: { finding: finding.key },
          dedupeKey: `watchdog_unsendable:${hourKey(deps.now())}`,
        });
        outcome.failed++;
        continue;
      }
      const sent = await deps.telegram.send(deps.chatId, `ALERT: ${finding.text}`);
      if (!sent.ok) {
        await repos.events.record({
          level: "error",
          source: "watchdog",
          kind: "alert_send_failed",
          detail: { finding: finding.key, failure: sent.error.kind },
          dedupeKey: `alert_send_failed:${hourKey(deps.now())}`,
        });
        outcome.failed++;
        continue;
      }
      await repos.events.record({
        level: "error",
        source: "watchdog",
        kind: finding.kind,
        detail: { text: finding.text },
        dedupeKey,
      });
      outcome.sent++;
      for (const uploadId of finding.closeUploads ?? []) {
        // Guarded by status = 'received': an upload that finished meanwhile is left as it is.
        await repos.uploads
          .finalise(uploadId, { status: "failed", errorCode: ERROR_CODES.E_INTERNAL })
          .catch(() => false);
      }
    } catch {
      outcome.failed++;
    }
  }
  return outcome;
}

export function watchdogDeps(
  env: Env,
  repos: Repositories,
  services: { fetch: typeof fetch; now: () => Date; sleep?: Sleep },
): WatchdogDeps {
  return {
    repos,
    telegram: telegramFromEnv(env, services.fetch, services.sleep),
    chatId: alertChatId(env),
    now: services.now,
  };
}
