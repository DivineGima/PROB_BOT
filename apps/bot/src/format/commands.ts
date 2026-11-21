import { COMMAND_SPECS } from "../commands/registry";
import type {
  AlertRead,
  LoggedRow,
  PendingRow,
  SettledRow,
  SnapshotRow,
  StatusSnapshot,
  TeamFormRead,
  TeamRef,
  UploadRow,
  VerdictRead,
} from "../repo";
import {
  bar,
  callHit,
  callText,
  DISPLAY,
  favouriteOf,
  grade,
  OUTCOME_ICON,
  outcomeOf,
  pct0,
  strongestCall,
  verdictIcon,
} from "./display";
import { clean, ERROR_TEXT, formatKickoff, packLines, renderMatch, splitBlocks } from "./index";

/**
 * Replies of the read-only bot commands (architecture 4, sections 6.10 and 8.12). Pure functions:
 * plain text built from OUR stored rows (team names from our table, codes, numbers), every stored
 * string passed through `clean()`. The command's arguments are never interpolated (S15).
 *
 * [v4] The replies are visual (ADR-053): status icons, emoji bars and the strongest call (ADR-057),
 * drawn by `./display` from `packages/contracts/display.json`. Still plain text, no parse mode.
 *
 * `/fixtures` prints verdicts only: its input type carries no probability (ADR-050).
 */

/** At most this many reply messages per command (section 6.10). */
export const MAX_COMMAND_MESSAGES = 5;

const MODEL_ORDER = ["dc", "pi", "bp"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const pad2 = (n: number): string => String(n).padStart(2, "0");
const pct = (p: number): string => `${(p * 100).toFixed(1)}%`;
const fixed = (v: unknown, digits = 4): string =>
  typeof v === "number" && Number.isFinite(v) ? v.toFixed(digits) : "n/a";
const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const tick = (ok: boolean): string => (ok ? "✅" : "❌");

export const UNKNOWN_COMMAND = "Unknown command. Send /help to see the commands.";
export const PROBABILITIES_NOTE = "Probabilities come only from an uploaded screener file.";

/** `17 Oct 06:00 UTC` for a stored UTC timestamp; `time unknown` when unreadable. */
export function shortUtc(iso: string | null | undefined): string {
  const d = new Date(iso ?? "");
  if (Number.isNaN(d.getTime())) return "time unknown";
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${pad2(d.getUTCHours())}:${pad2(d.getUTCMinutes())} UTC`;
}

/** `17 Oct` for a `YYYY-MM-DD` date. */
export function shortDate(date: string): string {
  const d = new Date(`${date}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return clean(date, 10);
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}`;
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

/** A nested object of a parsed JSON object, or `{}`. */
function objectAt(parent: Record<string, unknown>, key: string): Record<string, unknown> {
  const value = parent[key];
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

/** Model weights in a stable order (dc, pi, bp, then any other). */
export function weightsOf(weights: unknown): Array<[string, number]> {
  const object = typeof weights === "string" ? parseObject(weights) : (weights ?? {});
  return Object.entries(object as Record<string, unknown>)
    .filter((entry): entry is [string, number] => typeof entry[1] === "number")
    .sort(([a], [b]) => rank(a) - rank(b) || a.localeCompare(b));
}

const rank = (model: string): number => {
  const i = MODEL_ORDER.indexOf(model);
  return i < 0 ? MODEL_ORDER.length : i;
};

/** Splits blocks into at most MAX_COMMAND_MESSAGES messages; a cut reply says so. */
export function capMessages(blocks: string[]): string[] {
  const messages = splitBlocks(blocks);
  if (messages.length <= MAX_COMMAND_MESSAGES) return messages;
  const kept = messages.slice(0, MAX_COMMAND_MESSAGES);
  kept[MAX_COMMAND_MESSAGES - 1] =
    `${kept[MAX_COMMAND_MESSAGES - 1]}\n\n(Reply cut at ${MAX_COMMAND_MESSAGES} messages.)`;
  return kept;
}

const teams = (home: string, away: string): string => `${clean(home)} vs ${clean(away)}`;

// -- /help ------------------------------------------------------------------------------------------

const HELP_ICONS: Readonly<Record<string, string>> = {
  status: "🟢",
  fixtures: "📅",
  logged: "📒",
  results: "📋",
  pending: "⏳",
  report: "📊",
  last: "📨",
  team: "🔎",
  alerts: "🔔",
  help: "❓",
};

export function renderHelp(): string[] {
  const lines = ["🤖 Commands (they only read what is stored):"];
  for (const c of COMMAND_SPECS) {
    lines.push(
      `${HELP_ICONS[c.command] ?? "•"} /${c.command}${c.args ? ` ${c.args}` : ""} - ${c.description}`,
    );
  }
  lines.push(
    "",
    "Dates are UTC calendar dates. Upload the screener .json file as a document to get probabilities.",
    PROBABILITIES_NOTE,
  );
  return [lines.join("\n")];
}

// -- /status ----------------------------------------------------------------------------------------

export interface StatusInput {
  now: Date;
  /** The watchdog's findings (its own text), in its order. */
  findings: string[];
  /** Uploads acknowledged but never answered (the watchdog's stuck-upload finding). */
  stuckUploads: number;
  snapshot: StatusSnapshot;
  /** The active run's stale limit in hours. */
  staleHours: number;
}

export function renderStatus(input: StatusInput): string[] {
  const { snapshot: s, now } = input;
  const failedModels = s.run?.models.filter((m) => m.status === "failed") ?? [];
  const failedJobs = s.jobs.filter((j) => j.status === "failed");
  const attention =
    input.findings.length > 0 ||
    failedModels.length > 0 ||
    failedJobs.length > 0 ||
    s.alertPath.length > 0;

  const lines = [attention ? "🔴 Status: ATTENTION" : "🟢 Status: OK"];
  for (const text of input.findings) lines.push(`⚠️ ${clean(text, 300)}`);
  lines.push("");

  if (!s.run) {
    lines.push("🧠 No model run is published.");
  } else {
    const age = (now.getTime() - Date.parse(s.run.activatedAt)) / 3_600_000;
    const ageText = Number.isFinite(age) ? `${Math.floor(age)} h old` : "age unknown";
    lines.push(
      `🧠 Run ${clean(s.run.runId, 40)}, published ${shortUtc(s.run.activatedAt)} (${ageText}, limit ${input.staleHours} h)`,
    );
    if (s.run.dataCutoffUtc) lines.push(`   Results to ${clean(s.run.dataCutoffUtc, 10)}`);
    const weights = new Map(weightsOf(parseObject(s.run.ensembleJson).weights));
    const models = s.run.models.map((m) =>
      m.status === "ok"
        ? `${m.model}${weights.has(m.model) ? ` ${fixed(weights.get(m.model), 2)}` : ""} ✅`
        : `❌ ${m.model} FAILED`,
    );
    lines.push(`   Models: ${models.length ? models.join(" · ") : "none recorded"}`);
  }

  lines.push(
    s.jobs.length
      ? `🌙 Nightly: ${s.jobs
          .map(
            (j) =>
              `${j.status === "failed" ? "❌" : j.status === "ok" ? "✅" : "⏳"} ${clean(j.kind, 16)} ${j.status === "failed" ? "FAILED " : ""}${shortUtc(j.startedAt)}`,
          )
          .join(" · ")}`
      : "🌙 Nightly: no job recorded",
  );
  lines.push(
    `📅 Forecasts stored / fixtures scheduled: ${s.coverage
      .map((d) => `${d.date} ${d.forecasts}/${d.scheduled}`)
      .join(", ")}`,
  );
  lines.push(`📨 Unanswered uploads: ${input.stuckUploads === 0 ? "none" : input.stuckUploads}`);
  lines.push(`🔔 Alerts waiting for the nightly delivery: ${s.alertsWaiting}`);
  lines.push(
    s.alertPath.length
      ? `⚠️ Alert delivery problems (24 h): ${s.alertPath
          .map((p) => `${clean(p.kind, 32)} x${p.n} (last ${shortUtc(p.last)})`)
          .join(", ")}`
      : "✅ Alert delivery problems (24 h): none",
  );
  return capMessages([lines.join("\n")]);
}

// -- /fixtures (verdicts only, ADR-050) --------------------------------------------------------------

/** Which side made a fixture's verdict, from the stored detail; codes only, no numbers. */
export function verdictSides(detailJson: string): string {
  const drift = parseObject(detailJson).drift;
  if (typeof drift !== "object" || drift === null) return "";
  const sides: string[] = [];
  for (const side of ["home", "away"] as const) {
    const team = (drift as Record<string, unknown>)[side];
    if (typeof team !== "object" || team === null) continue;
    const status = (team as Record<string, unknown>).status;
    if (typeof status === "string" && status !== "ok") sides.push(`${side} ${clean(status, 24)}`);
  }
  return sides.length ? ` (${sides.join(", ")})` : "";
}

export function renderFixtures(date: string, read: VerdictRead | null): string[] {
  if (!read) return ["🧠 No model run is published, so no forecasts are stored."];
  const header = [`📅 Fixtures for ${date} (UTC date), run ${clean(read.runId, 40)}`];
  if (read.rows.length === 0) {
    header.push(`No forecasts are stored for ${date}.`);
  } else {
    const counts = new Map<string, number>();
    for (const r of read.rows) counts.set(r.verdict, (counts.get(r.verdict) ?? 0) + 1);
    header.push(
      [...counts.entries()]
        .sort(([a], [b]) => (a === "ok" ? -1 : b === "ok" ? 1 : a.localeCompare(b)))
        .map(([v, n]) => `${verdictIcon(v)} ${v} ${n}`)
        .join(" · "),
    );
  }
  const lines = read.rows.map(
    (r) =>
      `${verdictIcon(r.verdict)} ${clean(r.compCode, 4)}  ${teams(r.home, r.away)}  ${r.kickoffUtc ? formatKickoff(r.kickoffUtc) : "time unknown"}  ${clean(r.verdict, 24)}${r.verdict === "ok" ? "" : verdictSides(r.detailJson)}`,
  );
  const footer: string[] = [];
  if (read.unforecast > 0) {
    footer.push(
      `❓ ${read.unforecast} scheduled fixture(s) have no forecast (an upload would answer NO_FORECAST).`,
    );
  }
  footer.push(
    "Verdicts only. Probabilities come from an uploaded screener file; its gates still decide.",
  );
  return capMessages([header.join("\n"), ...packLines(lines), footer.join("\n")]);
}

export function renderFixturesWindow(first: string, last: string): string[] {
  return [
    `📅 Forecasts are stored for ${first} to ${last} (UTC dates). Usage: /fixtures [today|tomorrow|YYYY-MM-DD]`,
  ];
}

// -- /logged ----------------------------------------------------------------------------------------

function statusText(status: string, goals: [number, number] | null, voidReason: string | null) {
  if (status === "scored" && goals) return `scored ${goals[0]}-${goals[1]}`;
  if (status === "void") return `void (${clean(voidReason ?? "no reason", 24)})`;
  return clean(status, 12);
}

/** `✅ Status: scored 2-0 · favourite right ✅ · ⭐ call right ❌` for a settled row. */
function settledLine(
  status: string,
  goals: [number, number] | null,
  voidReason: string | null,
  p1x2: [number, number, number],
  overs: number[],
): string {
  const text = statusText(status, goals, voidReason);
  if (status !== "scored" || !goals) {
    return `${status === "void" ? "⚪" : "⏳"} Status: ${text}`;
  }
  const favRight = favouriteOf(p1x2).outcome === outcomeOf(goals);
  const callRight = callHit(strongestCall(p1x2, overs).key, goals);
  return `${tick(favRight)} Status: ${text} · favourite right ${tick(favRight)} · ⭐ call right ${tick(callRight)}`;
}

export function renderLogged(date: string, rows: LoggedRow[]): string[] {
  if (rows.length === 0) return [`📒 Nothing logged for ${date} (UTC date).`];
  const blocks = [`📒 Logged for ${date} (UTC date): ${rows.length}`];
  for (const r of rows) {
    const block = renderMatch({
      comp: r.compCode,
      home: r.home,
      away: r.away,
      kickoffUtc: r.kickoffUtc,
      p1x2: r.p1x2,
      overs: r.overs,
      weights: weightsOf(r.weightsJson),
      alreadyLogged: false,
    });
    blocks.push(
      `${block}\n${settledLine(r.status, r.goals, r.voidReason, r.p1x2, r.overs)}\n🕓 logged ${shortUtc(r.createdAt)}`,
    );
  }
  blocks.push(
    "These are the stored numbers, as the upload reply showed them. Probabilities, not advice.",
  );
  return capMessages(blocks);
}

// -- /results ---------------------------------------------------------------------------------------

const OUTCOME_WORDS = { home: "home win", draw: "draw", away: "away win" } as const;

export function renderResults(rows: SettledRow[]): string[] {
  if (rows.length === 0) return ["📋 No settled predictions yet."];
  const blocks = [`📋 Latest settled predictions: ${rows.length}`];
  let scored = 0;
  let favRight = 0;
  let callRight = 0;
  for (const r of rows) {
    const head = `${clean(r.compCode, 4)} ${shortDate(r.matchDate)} · ${clean(r.home)}`;
    if (r.status === "void" || !r.goals) {
      blocks.push(
        `⚪ ${head} vs ${clean(r.away)}  void (${clean(r.voidReason ?? "no result", 24)})`,
      );
      continue;
    }
    const [h, a] = r.goals;
    const actual = outcomeOf(r.goals);
    const fav = favouriteOf(r.p1x2).outcome === actual;
    const call = strongestCall(r.p1x2, r.overs);
    const hit = callHit(call.key, r.goals);
    scored += 1;
    favRight += fav ? 1 : 0;
    callRight += hit ? 1 : 0;
    blocks.push(
      [
        `${tick(fav)} ${head} ${h}-${a} ${clean(r.away)}`,
        `   ${OUTCOME_ICON.home} ${pct0(r.p1x2[0])}  ${OUTCOME_ICON.draw} ${pct0(r.p1x2[1])}  ${OUTCOME_ICON.away} ${pct0(r.p1x2[2])}  → ${OUTCOME_WORDS[actual]}`,
        `   ⭐ ${callText(call.key, clean(r.home), clean(r.away))} ${pct0(call.p)} ${tick(hit)} · grade ${grade(r.rps1x2)} (RPS ${fixed(r.rps1x2, 3)})`,
      ].join("\n"),
    );
  }
  const summary = [
    scored
      ? `Summary: favourite right ${favRight} of ${scored} · ⭐ strongest call right ${callRight} of ${scored}`
      : "Summary: nothing scored in this list.",
    "✅/❌ at the start = the most likely result; ⭐ = the strongest call. Grade: 🟢 good · 🟡 fair · 🔴 poor (RPS, lower is better). Averages and the baseline are in /report.",
  ];
  blocks.push(summary.join("\n"));
  return capMessages(blocks);
}

// -- /pending ---------------------------------------------------------------------------------------

export function renderPending(read: { rows: PendingRow[]; total: number }): string[] {
  if (read.total === 0) return ["⏳ No predictions are waiting for a result."];
  const lines = [`⏳ Waiting for a result: ${read.total}`];
  for (const r of read.rows) {
    lines.push(
      `• ${clean(r.compCode, 4)}  ${teams(r.home, r.away)}  ${formatKickoff(r.kickoffUtc)}`,
    );
  }
  if (read.total > read.rows.length) lines.push(`… and ${read.total - read.rows.length} more`);
  lines.push("A match with no result 3 days after kickoff is voided NO_RESULT.");
  return capMessages(packLines(lines));
}

// -- /report ----------------------------------------------------------------------------------------

/** `5 of 6 (83%)` from a `{n, hits}` object; `n/a` when absent. */
function hitsOf(entry: Record<string, unknown>): string {
  const n = num(entry.n);
  const hits = num(entry.hits);
  if (n === null || hits === null || n === 0) return "n/a";
  return `${hits} of ${n} (${pct0(hits / n)})`;
}

export function renderReport(snapshot: SnapshotRow | null): string[] {
  if (!snapshot)
    return ["📊 No weekly report stored yet. It is made on Mondays once predictions are scored."];
  const m = parseObject(snapshot.metricsJson);
  const paired = objectAt(m, "paired");
  const omissions = objectAt(m, "omissions");
  const byModel = objectAt(m, "by_model");
  const level = typeof paired.level === "number" ? `${Math.round(paired.level * 100)}%` : "n/a";
  const nScored = num(m.n_scored) ?? 0;
  const target = num(m.target) ?? 0;

  const lines = [
    `📊 Weekly report of ${shortUtc(snapshot.createdAt)} (matches ${clean(snapshot.windowFrom, 10)} to ${clean(snapshot.windowTo, 10)})`,
    `📈 Progress ${target ? bar(nScored / target, DISPLAY.bar.home) : ""} Scored ${fixed(m.n_scored, 0)} of the ${fixed(m.target, 0)}-match target; pending ${fixed(m.n_pending, 0)}`,
    "",
    `🏆 RPS 1X2 on ${fixed(paired.n, 0)} paired matches (lower is better): bot ${fixed(paired.ensemble_rps_1x2)}, simple benchmark ${fixed(paired.baseline_rps_1x2)}`,
  ];
  const diff = num(paired.mean_diff_rps_1x2);
  const base = num(paired.baseline_rps_1x2);
  const low = num(paired.ci_low);
  const high = num(paired.ci_high);
  if (diff !== null && base) {
    const better = -diff / base;
    lines.push(
      `   The bot is ${pct0(Math.abs(better))} ${better >= 0 ? "better" : "worse"} than the benchmark. Difference ${fixed(diff)}, ${level} interval ${fixed(low)} to ${fixed(high)}`,
    );
  }
  if (low !== null && high !== null) {
    lines.push(
      high < 0
        ? "   🟢 Ahead, and the interval excludes zero (information, not a significance claim)."
        : low > 0
          ? "   🔴 Behind, and the interval excludes zero."
          : "   🟡 Not proven yet: the interval includes zero, so it could still be luck.",
    );
  }

  const strongest = objectAt(m, "strongest");
  if (Object.keys(strongest).length) {
    const said = num(strongest.mean_forecast);
    lines.push(
      "",
      `⭐ Strongest calls right: ${hitsOf(strongest)}${said !== null ? ` · the bot said ${pct0(said)} on average` : ""}`,
    );
  }
  const favourite = objectAt(m, "favourite");
  if (Object.keys(favourite).length) {
    const bands = objectAt(favourite, "by_band");
    lines.push(
      `👉 Favourite (most likely result) right: ${hitsOf(favourite)}`,
      `   💪 60%+: ${hitsOf(objectAt(bands, "clear"))} · 👍 50-60%: ${hitsOf(objectAt(bands, "slight"))} · 🤷 under 50%: ${hitsOf(objectAt(bands, "open"))}`,
    );
  }
  const goals = objectAt(m, "goals");
  if (num(goals.expected) !== null) {
    lines.push(
      `⚽ Goals per match: expected ${fixed(goals.expected, 2)}, actual ${fixed(goals.actual, 2)}`,
    );
  }

  const models = weightsOf(
    Object.fromEntries(
      Object.entries(byModel).map(([name, v]) => [name, parseObject(JSON.stringify(v)).rps_1x2]),
    ),
  );
  if (models.length) {
    lines.push(
      `🧠 Per model RPS 1X2: ${models
        .map(([name, rps]) => {
          const n = parseObject(JSON.stringify(byModel[name])).n;
          return `${clean(name, 8)} ${fixed(rps)} (n ${fixed(n, 0)})`;
        })
        .join(", ")}`,
    );
  }
  const reasons = objectAt(omissions, "by_reason");
  const reasonText = Object.entries(reasons)
    .filter((e): e is [string, number] => typeof e[1] === "number")
    .map(([k, n]) => `${clean(k, 24)} ${n}`)
    .join(", ");
  lines.push(
    `🚫 Omitted: ${typeof omissions.rate === "number" ? pct(omissions.rate) : "n/a"} of the matches seen${reasonText ? ` (${reasonText})` : ""}`,
  );
  lines.push(
    "ℹ️ Small samples are noisy: read this as information. The chart comes with the Monday report.",
  );
  return capMessages([lines.join("\n")]);
}

// -- /last ------------------------------------------------------------------------------------------

const UPLOAD_ICON: Readonly<Record<string, string>> = {
  processed: "✅",
  received: "⏳",
  rejected: "⛔",
  failed: "❌",
};

export function renderLast(upload: UploadRow | null, now: Date, stuckMinutes: number): string[] {
  if (!upload) return ["📨 No upload has been received yet."];
  const n = (v: number | null): string => (v === null ? "-" : String(v));
  const lines = [
    `${UPLOAD_ICON[upload.status] ?? "📨"} Last upload: ${shortUtc(upload.receivedAt)}, status ${clean(upload.status, 12)}`,
    `📄 File date ${upload.runDateUtc ? clean(upload.runDateUtc, 10) : "-"}; matches ${n(upload.nMatchesIn)}; excluded by the screener ${n(upload.nExcludedIn)}; published ${n(upload.nPublished)}; omitted ${n(upload.nOmitted)}; already logged ${n(upload.nDuplicate)}`,
  ];
  if (upload.runId) lines.push(`🧠 Run ${clean(upload.runId, 40)}`);
  if (upload.errorCode) {
    const text = (ERROR_TEXT as Record<string, string>)[upload.errorCode];
    lines.push(`❌ Error ${clean(upload.errorCode, 24)}${text ? `: ${text}` : ""}`);
  }
  const age = (now.getTime() - Date.parse(upload.receivedAt)) / 60_000;
  if (upload.status === "received" && age > stuckMinutes) {
    lines.push("⚠️ Never answered: send the file again.");
  }
  return [lines.join("\n")];
}

// -- /team ------------------------------------------------------------------------------------------

export const TEAM_NOT_FOUND =
  "No team by that name in our table. Use the canonical name, for example /team Arsenal.";

export function renderTeamChoices(names: string[]): string[] {
  return [
    `🔎 Several teams match: ${names.map((n) => clean(n)).join(", ")}. Send /team with the full name.`,
  ];
}

/** Goals-per-match bars scale: a full bar is 3 goals a match. */
const GOALS_BAR_MAX = 3;

function goalsBar(value: number | null, cell: string): string {
  return value === null ? "n/a" : `${bar(value / GOALS_BAR_MAX, cell)} ${fixed(value, 2)}`;
}

export function renderTeam(team: TeamRef, read: TeamFormRead | null): string[] {
  const lines = [
    `🔎 ${clean(team.name)} (${team.homeComp ? clean(team.homeComp, 4) : "UCL only"}, ${team.active ? "active" : "history-only"})`,
  ];
  if (!read) {
    lines.push("🧠 No model run is published.");
    return [lines.join("\n")];
  }
  const f = read.form;
  if (!f) {
    lines.push(`No form row in run ${clean(read.runId, 40)}.`);
  } else {
    lines.push(`Matches in the training window ${f.nTraining}; this season ${f.nSeason}`);
    lines.push(
      "",
      "⚽ Goals scored per match",
      `   season   ${goalsBar(f.seasonGf, DISPLAY.bar.home)}`,
      `   last ${f.l10N}  ${goalsBar(f.l10Gf, DISPLAY.bar.home)}`,
      "🧤 Goals conceded per match",
      `   season   ${goalsBar(f.seasonGa, DISPLAY.bar.away)}`,
      `   last ${f.l10N}  ${goalsBar(f.l10Ga, DISPLAY.bar.away)}`,
      `Goals per match this season: for ${fixed(f.seasonGf, 2)}, against ${fixed(f.seasonGa, 2)}`,
    );
    if (f.latestMatchDate) lines.push(`Latest match ${clean(f.latestMatchDate, 10)}`);
  }
  const next = read.nextFixture;
  lines.push(
    "",
    next
      ? `${verdictIcon(next.verdict)} Next stored fixture: ${clean(next.compCode, 4)}  ${teams(next.home, next.away)}  ${next.kickoffUtc ? formatKickoff(next.kickoffUtc) : shortDate(next.matchDate)}  ${clean(next.verdict, 24)}`
      : "No stored fixture from today on.",
  );
  lines.push(
    "Drift is judged per fixture by the nightly job (goals only, thresholds unvalidated).",
  );
  return [lines.join("\n")];
}

// -- /alerts ----------------------------------------------------------------------------------------

const STATE_TEXT = {
  delivered: "✅ delivered",
  waiting: "⏳ waiting",
  watchdog: "🐕 sent by watchdog",
};

export function renderAlerts(read: AlertRead, hours: number): string[] {
  if (read.total === 0) return [`🔔 No alerts in the last ${hours} hours.`];
  const lines = [
    `🔔 Alerts in the last ${hours} hours: ${read.total} (${read.waiting} waiting for the nightly delivery)`,
  ];
  for (const r of read.rows) {
    lines.push(`${shortUtc(r.at)}  ${clean(r.kind, 40)}  ${STATE_TEXT[r.state]}`);
  }
  if (read.total > read.rows.length) {
    lines.push(`… and ${read.total - read.rows.length} older not shown`);
  }
  lines.push(`By kind: ${read.byKind.map((k) => `${clean(k.kind, 40)} ${k.n}`).join(", ")}`);
  return capMessages(packLines(lines));
}
