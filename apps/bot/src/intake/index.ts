import { MAX_ERROR_PATHS, MAX_FILE_BYTES, MAX_KICKOFF_AHEAD_MS } from "../config/constants";
import {
  ERROR_CODES,
  type ErrorCode,
  err,
  type OmissionCode,
  ok,
  type Result,
} from "../config/errors";
import type { ScreenerMatch, ScreenerV1 } from "./schema";
import { validateScreener } from "./validate";

/**
 * Intake: everything between "Telegram says a document arrived" and "a validated ScreenerV1"
 * (architecture sections 6.1, 6.5, S4). The file is hostile input produced by an LLM-driven
 * screener: nothing in it is fetched or evaluated, and an error message never echoes file content.
 */

export interface IntakeError {
  code: ErrorCode;
  /** Short, content-free explanation lines (validation paths and rule names only). */
  detail: string[];
}

export interface DocumentInfo {
  fileName?: string;
  mimeType?: string;
  fileSize?: number;
}

const fail = (code: ErrorCode, detail: string[] = []): Result<never, IntakeError> =>
  err({ code, detail });

/** Document guard run BEFORE any download: a `.json` name (or a JSON MIME type) and a sane size. */
export function guardDocument(doc: DocumentInfo): Result<true, IntakeError> {
  const name = (doc.fileName ?? "").toLowerCase();
  const mime = (doc.mimeType ?? "").toLowerCase();
  if (!name.endsWith(".json") && mime !== "application/json")
    return fail(ERROR_CODES.E_NOT_JSON_FILE);
  if (typeof doc.fileSize === "number" && doc.fileSize > MAX_FILE_BYTES) {
    return fail(ERROR_CODES.E_TOO_LARGE);
  }
  return ok(true);
}

/** Strict UTF-8 (a leading byte-order mark is tolerated and removed). */
export function decodeUtf8(bytes: Uint8Array): Result<string, IntakeError> {
  if (bytes.byteLength > MAX_FILE_BYTES) return fail(ERROR_CODES.E_TOO_LARGE);
  try {
    const text = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(bytes);
    return ok(text.charCodeAt(0) === 0xfeff ? text.slice(1) : text);
  } catch {
    return fail(ERROR_CODES.E_PARSE, ["not valid UTF-8"]);
  }
}

/** Validation issues reduced to `path (code)`: never the offending value. */
function issuePaths(issues: ReadonlyArray<{ path: PropertyKey[]; code: string }>): string[] {
  const seen = new Set<string>();
  for (const issue of issues) {
    const where = issue.path.length ? issue.path.map(String).join(".") : "(file)";
    seen.add(`${where} (${issue.code})`);
    if (seen.size >= MAX_ERROR_PATHS) break;
  }
  return [...seen];
}

/**
 * Size cap, UTF-8, JSON, then `schema_version` (before the schema, so a v2 file says so), then the
 * hand validator (F1 trim; `schema.ts` keeps the Zod contract that a test compares it with).
 */
export function parseScreenerFile(bytes: Uint8Array): Result<ScreenerV1, IntakeError> {
  const text = decodeUtf8(bytes);
  if (!text.ok) return text;

  let json: unknown;
  try {
    json = JSON.parse(text.value);
  } catch {
    return fail(ERROR_CODES.E_PARSE, ["not valid JSON"]);
  }
  if (typeof json !== "object" || json === null || Array.isArray(json)) {
    return fail(ERROR_CODES.E_SCHEMA_INVALID, ["(file) (invalid_type)"]);
  }
  const version = (json as { schema_version?: unknown }).schema_version;
  if (version !== 1) return fail(ERROR_CODES.E_SCHEMA_VERSION);

  const parsed = validateScreener(json);
  if (!parsed.success) return fail(ERROR_CODES.E_SCHEMA_INVALID, issuePaths(parsed.issues));
  return ok(parsed.data);
}

/**
 * Business checks that produce an omission, not a file rejection (section 6.1). Order matters and
 * is part of the contract: a wrong date wins over "started", which wins over "too far".
 */
export function timeCheck(
  match: Pick<ScreenerMatch, "kickoff_utc">,
  runDateUtc: string,
  now: Date,
): OmissionCode | null {
  if (match.kickoff_utc.slice(0, 10) !== runDateUtc) return "DATE_MISMATCH";
  const kickoff = Date.parse(match.kickoff_utc);
  if (kickoff <= now.getTime()) return "STARTED";
  if (kickoff > now.getTime() + MAX_KICKOFF_AHEAD_MS) return "TOO_FAR";
  return null;
}

/** Screener exclusions counted by their gate code (`G1`..`G6`); anything else is `OTHER` (S5). */
export function countExclusions(excluded: ScreenerV1["excluded"]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const item of excluded) {
    const gate =
      item.reason
        .trim()
        .toUpperCase()
        .match(/^G[1-6](?![0-9])/)?.[0] ?? "OTHER";
    counts[gate] = (counts[gate] ?? 0) + 1;
  }
  return counts;
}
