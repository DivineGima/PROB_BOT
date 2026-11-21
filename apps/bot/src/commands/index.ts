import {
  COMMAND_ALERT_HOURS,
  COMMAND_ALERT_PATH_HOURS,
  FORECAST_HORIZON_DAYS,
  STUCK_UPLOAD_MINUTES,
  WATCHDOG_FORECAST_DAYS,
} from "../config/constants";
import { ERROR_CODES, type ErrorCode } from "../config/errors";
import {
  renderAlerts,
  renderFixtures,
  renderFixturesWindow,
  renderHelp,
  renderLast,
  renderLogged,
  renderPending,
  renderReport,
  renderResults,
  renderStatus,
  renderTeam,
  renderTeamChoices,
  TEAM_NOT_FOUND,
  UNKNOWN_COMMAND,
} from "../format/commands";
import type { Repositories, TeamRef } from "../repo";
import type { TelegramClient } from "../telegram/client";
import { collectFindings, staleHoursOf } from "../watchdog";
import { normaliseName } from "./normalise";
import { daysBetween, type ParsedCommand, parseCountArg, parseDateArg } from "./parse";
import { type CommandName, usageOf } from "./registry";

/**
 * The read-only bot commands (architecture 3, sections 6.10 and 8.12, ADR-049 to ADR-051).
 *
 * READ-ONLY: handlers read through `repos.queries` (SELECT only), the watchdog's pure
 * `collectFindings` and nothing else. The one write is a `command_failed` event when something
 * unexpected happens (or `bot_token_missing`, as the usage hint does). No handler imports the upload
 * pipeline, logs a prediction, starts a job or changes a run (invariant 9).
 */

export interface CommandDeps {
  repos: Repositories;
  /** Null when the bot token is missing or malformed: nothing can be sent. */
  telegram: TelegramClient | null;
  now: () => Date;
  newErrorId: () => string;
}

export interface CommandOutcome {
  outcome: string;
  /** A known command name, for the request log (never the arguments). */
  command?: CommandName;
  errorCode?: ErrorCode;
  counts?: Record<string, number>;
}

const HOUR_MS = 3_600_000;
const DAY_MS = 24 * HOUR_MS;
const isoDate = (d: Date): string => d.toISOString().slice(0, 10);
const isoTime = (d: Date): string => `${d.toISOString().slice(0, 19)}Z`;
const hourKey = (d: Date): string => d.toISOString().slice(0, 13);

/** A handler's answer: the reply messages, or "send this command's usage line". */
type Reply = string[] | "usage";
type Handler = (deps: CommandDeps, args: string, now: Date) => Promise<Reply>;

const RESULTS_DEFAULT = 10;
const RESULTS_MAX = 20;
const PENDING_LIMIT = 30;
const ALERT_ROWS = 20;
const TEAM_CHOICES = 5;
const TEAM_MIN_CHARS = 2;
const TEAM_SUBSTRING_MIN = 3;

/**
 * Picks the team a typed name means: exact normalised canonical name, then a stored alias, then a
 * unique substring of a canonical name. Active clubs win over history-only clubs.
 */
export function matchTeam(
  query: string,
  teams: TeamRef[],
  aliasTeamIds: number[],
): { team: TeamRef } | { choices: TeamRef[] } | null {
  if (query === "") return null;
  const normalised = teams.map((t) => ({ team: t, norm: normaliseName(t.name) }));
  const aliasIds = new Set(aliasTeamIds);
  const tiers: TeamRef[][] = [
    normalised.filter((t) => t.norm === query).map((t) => t.team),
    teams.filter((t) => aliasIds.has(t.id)),
    query.length >= TEAM_SUBSTRING_MIN
      ? normalised.filter((t) => t.norm.includes(query)).map((t) => t.team)
      : [],
  ];
  const found = tiers.find((tier) => tier.length > 0);
  if (!found) return null;
  if (found.length === 1 && found[0]) return { team: found[0] };
  const active = found.filter((t) => t.active);
  if (active.length === 1 && active[0]) return { team: active[0] };
  return { choices: (active.length > 0 ? active : found).slice(0, TEAM_CHOICES) };
}

const HANDLERS: Record<CommandName, Handler> = {
  async help() {
    return renderHelp();
  },

  async status(deps, _args, now) {
    const [findings, snapshot] = await Promise.all([
      collectFindings(deps.repos, now),
      deps.repos.queries.statusSnapshot(
        Array.from({ length: WATCHDOG_FORECAST_DAYS }, (_, i) =>
          isoDate(new Date(now.getTime() + i * DAY_MS)),
        ),
        isoTime(new Date(now.getTime() - COMMAND_ALERT_HOURS * HOUR_MS)),
        isoTime(new Date(now.getTime() - COMMAND_ALERT_PATH_HOURS * HOUR_MS)),
      ),
    ]);
    const stuck = findings.find((f) => f.key === "stuck_upload")?.closeUploads?.length ?? 0;
    return renderStatus({
      now,
      findings: findings.map((f) => f.text),
      stuckUploads: stuck,
      snapshot,
      staleHours: snapshot.run ? staleHoursOf(snapshot.run.configJson) : 0,
    });
  },

  async fixtures(deps, args, now) {
    const date = parseDateArg(args, now);
    if (date === null) return "usage";
    const today = isoDate(now);
    const last = isoDate(new Date(now.getTime() + FORECAST_HORIZON_DAYS * DAY_MS));
    const offset = daysBetween(today, date);
    if (offset < 0 || offset > FORECAST_HORIZON_DAYS) return renderFixturesWindow(today, last);
    return renderFixtures(date, await deps.repos.queries.forecastVerdicts(date));
  },

  async logged(deps, args, now) {
    const date = parseDateArg(args, now);
    if (date === null) return "usage";
    return renderLogged(date, await deps.repos.queries.loggedForDate(date));
  },

  async results(deps, args) {
    const n = parseCountArg(args, RESULTS_DEFAULT, 1, RESULTS_MAX);
    if (n === null) return "usage";
    return renderResults(await deps.repos.queries.settled(n));
  },

  async pending(deps) {
    return renderPending(await deps.repos.queries.pending(PENDING_LIMIT));
  },

  async report(deps) {
    return renderReport(await deps.repos.queries.latestSnapshot());
  },

  async last(deps, _args, now) {
    return renderLast(await deps.repos.queries.latestUpload(), now, STUCK_UPLOAD_MINUTES);
  },

  async team(deps, args, now) {
    if (args.length < TEAM_MIN_CHARS) return "usage";
    const query = normaliseName(args);
    if (query === "") return [TEAM_NOT_FOUND];
    const candidates = await deps.repos.queries.teamCandidates(query);
    const match = matchTeam(query, candidates.teams, candidates.aliasTeamIds);
    if (!match) return [TEAM_NOT_FOUND];
    if ("choices" in match) return renderTeamChoices(match.choices.map((t) => t.name));
    return renderTeam(match.team, await deps.repos.queries.teamForm(match.team.id, isoDate(now)));
  },

  async alerts(deps, _args, now) {
    const since = isoTime(new Date(now.getTime() - COMMAND_ALERT_HOURS * HOUR_MS));
    return renderAlerts(
      await deps.repos.queries.alertEvents(since, ALERT_ROWS),
      COMMAND_ALERT_HOURS,
    );
  },
};

async function safely(action: () => Promise<unknown>): Promise<void> {
  try {
    await action();
  } catch {
    // Best effort only: the original failure is what matters.
  }
}

/** Answers one parsed command in the allowed chat. Never throws. */
export async function handleCommand(
  deps: CommandDeps,
  chatId: number,
  parsed: ParsedCommand,
): Promise<CommandOutcome> {
  const command = parsed.kind === "unknown" ? undefined : parsed.name;
  const named = (o: CommandOutcome): CommandOutcome => (command ? { ...o, command } : o);
  const now = deps.now();

  const telegram = deps.telegram;
  if (!telegram) {
    // No token means no reply and no alert from here, so leave the trace the health check reads.
    await safely(() =>
      deps.repos.events.record({
        level: "error",
        source: "bot",
        kind: "bot_token_missing",
        dedupeKey: `bot_token_missing:${hourKey(now)}`,
      }),
    );
    return named({ outcome: "no_telegram_client" });
  }

  let messages: string[];
  let outcome: string;
  try {
    if (parsed.kind === "unknown") {
      messages = [UNKNOWN_COMMAND];
      outcome = "unknown_command";
    } else if (parsed.kind === "usage") {
      messages = [usageOf(parsed.name)];
      outcome = "command_usage";
    } else {
      const reply = await HANDLERS[parsed.name](deps, parsed.args, now);
      messages = reply === "usage" ? [usageOf(parsed.name)] : reply;
      outcome = reply === "usage" ? "command_usage" : "command";
    }
  } catch {
    const errorId = deps.newErrorId();
    await safely(() =>
      deps.repos.events.record({
        level: "error",
        source: "bot",
        kind: "command_failed",
        detail: { command: command ?? "unknown", error_id: errorId },
        dedupeKey: `command_failed:${hourKey(now)}`,
      }),
    );
    await safely(() => telegram.send(chatId, `Internal error, id=${errorId}`));
    return named({ outcome: "command_failed", errorCode: ERROR_CODES.E_INTERNAL });
  }

  for (const text of messages) {
    const sent = await telegram.send(chatId, text);
    if (!sent.ok) {
      return named({ outcome: "command_reply_failed", counts: { n_messages: messages.length } });
    }
  }
  return named({ outcome, counts: { n_messages: messages.length } });
}
