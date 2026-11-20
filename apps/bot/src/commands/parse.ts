import { COMMAND_ALIASES, type CommandName, isCommandName } from "./registry";

/**
 * Command grammar (architecture 3, section 6.10). Pure functions, no I/O.
 *
 * - A command is a message text whose first character is `/`.
 * - The token is the text up to the first whitespace; a `@<bot>` suffix is removed; it is lower-cased
 *   and must be `/` plus 1 to 32 of `a-z` and `_`. Anything else is an unknown command.
 * - The arguments are the rest: control and direction characters removed, whitespace collapsed,
 *   trimmed, at most MAX_ARGS_CHARS characters (longer gives the command's usage line).
 *
 * Arguments are untrusted (S15): they are never echoed, logged or stored.
 */

export const MAX_ARGS_CHARS = 64;

export type ParsedCommand =
  | { kind: "command"; name: CommandName; args: string }
  /** A known command whose arguments are over the length cap: reply with its usage line. */
  | { kind: "usage"; name: CommandName }
  | { kind: "unknown" };

const TOKEN = /^\/([a-z_]{1,32})$/;

/** True for a text the command router owns (section 6.2). */
export function isCommandText(text: string): boolean {
  return text.startsWith("/");
}

/** Control, zero-width, bidi and separator characters become spaces; whitespace collapses. */
export function cleanArgs(text: string): string {
  let out = "";
  for (const ch of text) {
    const code = ch.codePointAt(0) ?? 0;
    const control =
      code < 32 ||
      (code >= 127 && code <= 159) ||
      (code >= 0x200b && code <= 0x200f) ||
      (code >= 0x2028 && code <= 0x202e) ||
      (code >= 0x2066 && code <= 0x2069) ||
      code === 0xfeff;
    out += control ? " " : ch;
  }
  return out.replace(/\s+/g, " ").trim();
}

export function parseCommand(text: string): ParsedCommand {
  if (!isCommandText(text)) return { kind: "unknown" };
  const match = text.match(/^\S+/);
  const rawToken = match?.[0] ?? "";
  const token = (rawToken.split("@")[0] ?? "").toLowerCase();
  const found = token.match(TOKEN);
  if (!found?.[1]) return { kind: "unknown" };
  const word = found[1];
  const name = COMMAND_ALIASES[word] ?? (isCommandName(word) ? word : null);
  if (name === null) return { kind: "unknown" };
  const args = cleanArgs(text.slice(rawToken.length));
  if (args.length > MAX_ARGS_CHARS) return { kind: "usage", name };
  return { kind: "command", name, args };
}

const DAY_MS = 24 * 60 * 60 * 1000;
const isoDate = (d: Date): string => d.toISOString().slice(0, 10);

/** True for a real calendar date written as `YYYY-MM-DD`. */
export function isCalendarDate(text: string): boolean {
  const m = text.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!m) return false;
  const [y, mo, d] = [Number(m[1]), Number(m[2]), Number(m[3])];
  const date = new Date(Date.UTC(y, mo - 1, d));
  return date.getUTCFullYear() === y && date.getUTCMonth() === mo - 1 && date.getUTCDate() === d;
}

/**
 * `today`, `tomorrow`, `yesterday` or `YYYY-MM-DD`, read as UTC calendar dates (the dates of
 * `run_date_utc`, `match_date` and `fixture_key`). No argument means today. Null when unreadable.
 */
export function parseDateArg(args: string, now: Date): string | null {
  const word = args.trim().toLowerCase();
  if (word === "" || word === "today") return isoDate(now);
  if (word === "tomorrow") return isoDate(new Date(now.getTime() + DAY_MS));
  if (word === "yesterday") return isoDate(new Date(now.getTime() - DAY_MS));
  return isCalendarDate(word) ? word : null;
}

/** A whole number in [min, max]; no argument gives `fallback`. Null when unreadable or out of range. */
export function parseCountArg(
  args: string,
  fallback: number,
  min: number,
  max: number,
): number | null {
  const text = args.trim();
  if (text === "") return fallback;
  if (!/^\d{1,4}$/.test(text)) return null;
  const n = Number(text);
  return n >= min && n <= max ? n : null;
}

/** Whole days from `from` to `to` (both `YYYY-MM-DD`). */
export function daysBetween(from: string, to: string): number {
  return Math.round((Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / DAY_MS);
}
