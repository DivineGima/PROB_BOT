import { MAX_REPLY_CHARS } from "../config/constants";
import type { OmissionCode } from "../config/errors";

/**
 * Reply rendering (architecture section 8.8). Pure functions: plain text, one block per match, UTC
 * and IST kickoff times, a footer once per upload, split at block boundaries so a match is never cut.
 *
 * Only validated numbers and strings from OUR tables are interpolated. Free text from the uploaded
 * file (notes, player names, URLs) is never echoed; the few file strings that appear (the names of
 * an omitted match whose teams did not resolve) are stripped of control characters and capped (S5).
 */

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const IST_OFFSET_MS = 330 * 60_000; // UTC+5:30, no daylight saving

export interface PublishedMatch {
  comp: string;
  home: string;
  away: string;
  kickoffUtc: string;
  p1x2: [number, number, number];
  /** P(over 0.5) .. P(over 5.5) */
  overs: number[];
  /** Models that contributed, with their weights, in a stable order. */
  weights: Array<[string, number]>;
  alreadyLogged: boolean;
}

export interface OmittedMatch {
  comp: string;
  home: string;
  away: string;
  reason: OmissionCode;
  /** A short, content-free note (for example the drifting team and the size of the move). */
  note?: string;
}

export interface ReplyInput {
  runDateUtc: string;
  runId: string;
  dataCutoff: string | null;
  published: PublishedMatch[];
  omitted: OmittedMatch[];
  /** Screener exclusions by gate code (`G1`..`G6`, `OTHER`). */
  excluded: Record<string, number>;
  banners: string[];
  hasUcl: boolean;
}

/** Control and direction-changing characters out, whitespace collapsed, length capped. */
export function clean(text: string, max = 48): string {
  let out = "";
  for (const ch of text) {
    const code = ch.codePointAt(0) ?? 0;
    const control =
      code < 32 ||
      (code >= 127 && code <= 159) ||
      (code >= 0x200b && code <= 0x200f) || // zero-width and direction marks
      (code >= 0x2028 && code <= 0x202e) || // line/paragraph separators, bidi overrides
      (code >= 0x2066 && code <= 0x2069) || // bidi isolates
      code === 0xfeff;
    out += control ? " " : ch;
  }
  const trimmed = out.replace(/\s+/g, " ").trim();
  return trimmed.length > max ? `${trimmed.slice(0, max - 1)}…` : trimmed;
}

const pad2 = (n: number): string => String(n).padStart(2, "0");

/** `17 Oct 15:00 UTC (20:30 IST)`; an IST time on the next calendar day carries `+1d`. */
export function formatKickoff(kickoffUtc: string): string {
  const utc = new Date(kickoffUtc);
  if (Number.isNaN(utc.getTime())) return "time unknown";
  const ist = new Date(utc.getTime() + IST_OFFSET_MS);
  const nextDay = ist.getUTCDate() !== utc.getUTCDate();
  const utcPart = `${utc.getUTCDate()} ${MONTHS[utc.getUTCMonth()]} ${pad2(utc.getUTCHours())}:${pad2(utc.getUTCMinutes())} UTC`;
  const istPart = `${pad2(ist.getUTCHours())}:${pad2(ist.getUTCMinutes())} IST${nextDay ? " +1d" : ""}`;
  return `${utcPart} (${istPart})`;
}

const pct = (p: number): string => (p * 100).toFixed(1);

export function renderMatch(m: PublishedMatch): string {
  const [home, draw, away] = m.p1x2;
  const lines = [
    `${clean(m.comp, 4)}  ${clean(m.home)} vs ${clean(m.away)}   ${formatKickoff(m.kickoffUtc)}${m.alreadyLogged ? "  [already logged]" : ""}`,
    `1X2   H ${pct(home)}%  D ${pct(draw)}%  A ${pct(away)}%`,
    `Over  ${m.overs.map((p, i) => `${i + 0.5} ${pct(p)}`).join(" | ")}   (Under = 100 - Over)`,
    `Models ${m.weights.map(([name]) => name).join("+")}   w ${m.weights.map(([, w]) => w.toFixed(2)).join("/")}   Drift: stable (goals only)`,
  ];
  return lines.join("\n");
}

const REASON_TEXT: Record<OmissionCode, string> = {
  UNMAPPED_TEAM: "a team is not in the canonical list",
  INSUFFICIENT_HISTORY: "a team has fewer than 10 matches of history",
  DRIFT: "recent form has drifted from the season average",
  STARTED: "kickoff is not in the future",
  TOO_FAR: "kickoff is more than 48 hours away",
  DATE_MISMATCH: "kickoff date is not the file's run date",
  NO_MODEL: "no model could forecast this fixture",
  DUPLICATE_PAIR: "listed more than once in the file",
  NO_FORECAST: "no stored forecast for this fixture",
};

export function renderOmission(o: OmittedMatch): string {
  const note = o.note ? ` (${clean(o.note, 80)})` : "";
  return `- ${clean(o.comp, 4)} ${clean(o.home)} vs ${clean(o.away)}: ${o.reason}, ${REASON_TEXT[o.reason]}${note}`;
}

function countsText(counts: Record<string, number>): string {
  return Object.entries(counts)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([key, n]) => `${key} ${n}`)
    .join(", ");
}

function footer(input: ReplyInput): string {
  const omittedCounts: Record<string, number> = {};
  for (const o of input.omitted) omittedCounts[o.reason] = (omittedCounts[o.reason] ?? 0) + 1;
  const nExcluded = Object.values(input.excluded).reduce((sum, n) => sum + n, 0);
  const lines = [
    `Run ${input.runId}${input.dataCutoff ? ` (results to ${input.dataCutoff.slice(0, 10)})` : ""}`,
    `Published ${input.published.length}; omitted ${input.omitted.length}${
      input.omitted.length ? ` (${countsText(omittedCounts)})` : ""
    }; excluded by the screener ${nExcluded}${nExcluded ? ` (${countsText(input.excluded)})` : ""}`,
  ];
  lines.push(...input.banners);
  if (input.hasUcl) {
    lines.push(
      "UCL: cross-league strength is the weakest-identified quantity; the final may be at a neutral ground.",
    );
  }
  lines.push(
    "Drift: goals only; thresholds are starting values, unvalidated. Probabilities, not advice.",
  );
  return lines.join("\n");
}

/** Splits blocks into messages of at most `limit` characters, never inside a block. */
export function splitBlocks(blocks: string[], limit = MAX_REPLY_CHARS): string[] {
  const messages: string[] = [];
  let current = "";
  for (const block of blocks) {
    const piece = block.length > limit ? `${block.slice(0, limit - 1)}…` : block;
    const joined = current ? `${current}\n\n${piece}` : piece;
    if (joined.length > limit && current) {
      messages.push(current);
      current = piece;
    } else {
      current = joined;
    }
  }
  if (current) messages.push(current);
  return messages;
}

/** Joins consecutive lines into blocks of at most `limit` characters, so a long omission list is
 * one compact block per message instead of one block (and blank line) per match. */
export function packLines(lines: string[], limit = MAX_REPLY_CHARS - 200): string[] {
  const blocks: string[] = [];
  let current = "";
  for (const line of lines) {
    const piece = line.length > limit ? `${line.slice(0, limit - 1)}…` : line;
    if (current && current.length + 1 + piece.length > limit) {
      blocks.push(current);
      current = piece;
    } else {
      current = current
        ? `${current}
${piece}`
        : piece;
    }
  }
  if (current) blocks.push(current);
  return blocks;
}

export function renderReply(input: ReplyInput): string[] {
  if (input.published.length === 0 && input.omitted.length === 0) {
    const nExcluded = Object.values(input.excluded).reduce((sum, n) => sum + n, 0);
    return splitBlocks([
      `File valid: 0 matches passed the screener (${nExcluded} excluded${
        nExcluded ? `: ${countsText(input.excluded)}` : ""
      }).`,
      footer(input),
    ]);
  }
  const blocks: string[] = [`Probabilities for ${input.runDateUtc}`];
  for (const match of input.published) blocks.push(renderMatch(match));
  if (input.omitted.length > 0) {
    blocks.push(...packLines(["Omitted:", ...input.omitted.map(renderOmission)]));
  }
  blocks.push(footer(input));
  return splitBlocks(blocks);
}

/** Error replies from the catalogue (section 6.6): short, no file content. */
export const ERROR_TEXT = {
  E_NOT_JSON_FILE: "Please upload the screener file as a .json document.",
  E_TOO_LARGE: "That file is too large (limit 256 KB). Nothing was computed.",
  E_DOWNLOAD_FAILED: "Could not download the file. Please resend.",
  E_PARSE: "The file is not valid UTF-8 JSON. Nothing was computed.",
  E_SCHEMA_VERSION: "Unsupported schema_version (this bot reads version 1). Nothing was computed.",
  E_SCHEMA_INVALID: "The file does not match schema version 1. Nothing was computed.",
  E_NO_RUN: "No usable model run — nothing computed.",
} as const;

export const USAGE_HINT = "Upload the screener .json file as a document.";

export function renderError(code: keyof typeof ERROR_TEXT, detail: string[] = []): string {
  const lines: string[] = [ERROR_TEXT[code]];
  if (detail.length) lines.push(...detail.map((d) => `- ${clean(d, 120)}`));
  return lines.join("\n");
}
