import type { ScreenerV1 } from "./schema";

/**
 * F1 trim (architecture section 8.10): the runtime validator for the screener file, written by hand
 * so the Worker does not load or run Zod (the Stage 5b CPU measurement was 7 to 9 ms warmed against
 * a 6 ms target). `schema.ts` stays the single source of the contract: the generated JSON Schema and
 * the contract drift test still come from it, and `test/intake-validate.test.ts` feeds both this
 * validator and the Zod schema thousands of mutated files and requires the same verdict, the same
 * issue paths and the same issue codes. Change the contract in `schema.ts` first, then here.
 *
 * Behaviour copied from Zod on purpose: every issue is reported (the caller caps the list), unknown
 * keys are dropped from the result, and a value is never echoed in an issue.
 */

export interface Issue {
  path: (string | number)[];
  code: string;
}

export type ValidationResult =
  | { success: true; data: ScreenerV1 }
  | { success: false; issues: Issue[] };

const COMPETITIONS: ReadonlySet<string> = new Set([
  "EPL",
  "LL",
  "BL",
  "SA",
  "L1",
  "UCL",
  "ERE",
  "PPL",
  "CHA",
  "SPL",
]);
const LINEUP: ReadonlySet<string> = new Set(["none", "expected", "confirmed"]);
const ABSENCE_STATUS: ReadonlySet<string> = new Set(["out", "doubtful"]);
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const KICKOFF_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:00Z$/;
const HTTPS_URL_RE = /^https:\/\/[^\s]+$/;

type Path = (string | number)[];
type Obj = Record<string, unknown>;

const isObject = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);

/** A real calendar date (rejects 2026-02-30, which `Date` would silently roll over). */
function isRealDate(value: string): boolean {
  const date = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === value;
}

class Collector {
  readonly issues: Issue[] = [];
  add(path: Path, code: string): void {
    this.issues.push({ path, code });
  }
}

/**
 * Length limits as Zod applies them: to anything that has a length (a string or an array), also when
 * the value is the wrong type, so a 70-character string where an array is expected reports both.
 */
function bounds(c: Collector, v: unknown, path: Path, min: number, max: number): void {
  if (typeof v !== "string" && !Array.isArray(v)) return;
  if (v.length < min) c.add(path, "too_small");
  if (v.length > max) c.add(path, "too_big");
}

/** A string with length limits. Returns the value when it is a string, whatever the limits say. */
function text(c: Collector, v: unknown, path: Path, min: number, max: number): string | undefined {
  if (typeof v !== "string") c.add(path, "invalid_type");
  bounds(c, v, path, min, max);
  return typeof v === "string" ? v : undefined;
}

function httpsUrl(c: Collector, v: unknown, path: Path): void {
  const s = text(c, v, path, 0, 300);
  if (s !== undefined && !HTTPS_URL_RE.test(s)) c.add(path, "invalid_format");
}

function oneOf(
  c: Collector,
  v: unknown,
  path: Path,
  allowed: ReadonlySet<string>,
): string | undefined {
  if (typeof v !== "string" || !allowed.has(v)) {
    c.add(path, "invalid_value");
    return undefined;
  }
  return v;
}

function restDays(c: Collector, v: unknown, path: Path): number | null | undefined {
  if (v === null) return null;
  if (typeof v !== "number" || !Number.isFinite(v)) {
    c.add(path, "invalid_type");
    return undefined;
  }
  if (!Number.isInteger(v)) {
    c.add(path, "invalid_type");
    return undefined;
  }
  if (v < 0) c.add(path, "too_small");
  if (v > 60) c.add(path, "too_big");
  return v;
}

function absences(c: Collector, v: unknown, path: Path): unknown[] | null | undefined {
  if (v === null) return null;
  if (!Array.isArray(v)) {
    c.add(path, "invalid_type");
    bounds(c, v, path, 0, 40);
    return undefined;
  }
  if (v.length > 40) {
    c.add(path, "too_big");
    return undefined;
  }
  const out: unknown[] = [];
  for (const [i, a] of v.entries()) {
    const at = [...path, i];
    if (!isObject(a)) {
      c.add(at, "invalid_type");
      continue;
    }
    const player = text(c, a.player, [...at, "player"], 0, 80);
    const status = oneOf(c, a.status, [...at, "status"], ABSENCE_STATUS);
    const url = a.source_url;
    httpsUrl(c, url, [...at, "source_url"]);
    out.push({ player, status, source_url: url });
  }
  return out;
}

function match(c: Collector, m: unknown, at: Path): Obj | undefined {
  if (!isObject(m)) {
    c.add(at, "invalid_type");
    return undefined;
  }
  const before = c.issues.length;
  const matchId = text(c, m.match_id, [...at, "match_id"], 1, 160);
  const competition = oneOf(c, m.competition, [...at, "competition"], COMPETITIONS);
  const home = text(c, m.home, [...at, "home"], 1, 64);
  const away = text(c, m.away, [...at, "away"], 1, 64);

  const kickoffPath = [...at, "kickoff_utc"];
  const kickoff = m.kickoff_utc;
  if (typeof kickoff !== "string") {
    c.add(kickoffPath, "invalid_type");
  } else {
    if (!KICKOFF_RE.test(kickoff)) c.add(kickoffPath, "invalid_format");
    if (!(isRealDate(kickoff.slice(0, 10)) && Number.isFinite(Date.parse(kickoff)))) {
      c.add(kickoffPath, "custom");
    }
  }

  const lineup = oneOf(c, m.lineup_status, [...at, "lineup_status"], LINEUP);
  const absencesHome = absences(c, m.absences_home, [...at, "absences_home"]);
  const absencesAway = absences(c, m.absences_away, [...at, "absences_away"]);
  const restHome = restDays(c, m.rest_days_home, [...at, "rest_days_home"]);
  const restAway = restDays(c, m.rest_days_away, [...at, "rest_days_away"]);

  const urlsPath = [...at, "source_urls"];
  const urls = m.source_urls;
  const sourceUrls: unknown[] = [];
  if (!Array.isArray(urls)) {
    c.add(urlsPath, "invalid_type");
    bounds(c, urls, urlsPath, 0, 20);
  } else if (urls.length > 20) {
    c.add(urlsPath, "too_big");
  } else {
    for (const [i, u] of urls.entries()) {
      httpsUrl(c, u, [...urlsPath, i]);
      sourceUrls.push(u);
    }
  }

  if (c.issues.length === before && home === away) c.add([...at, "away"], "custom");
  return {
    match_id: matchId,
    competition,
    home,
    away,
    kickoff_utc: kickoff,
    lineup_status: lineup,
    absences_home: absencesHome,
    absences_away: absencesAway,
    rest_days_home: restHome,
    rest_days_away: restAway,
    source_urls: sourceUrls,
  };
}

/** Validates an already JSON-parsed screener file (schema version 1). */
export function validateScreener(value: unknown): ValidationResult {
  const c = new Collector();
  if (!isObject(value)) return { success: false, issues: [{ path: [], code: "invalid_type" }] };

  if (value.schema_version !== 1) c.add(["schema_version"], "invalid_value");

  const runDate = value.run_date_utc;
  if (typeof runDate !== "string") {
    c.add(["run_date_utc"], "invalid_type");
  } else {
    if (!DATE_RE.test(runDate)) c.add(["run_date_utc"], "invalid_format");
    if (!isRealDate(runDate)) c.add(["run_date_utc"], "custom");
  }

  const notes = value.notes;
  if (notes !== null) text(c, notes, ["notes"], 0, 2000);

  const matches: Obj[] = [];
  const rawMatches = value.matches;
  if (!Array.isArray(rawMatches)) {
    c.add(["matches"], "invalid_type");
    bounds(c, rawMatches, ["matches"], 0, 100);
  } else if (rawMatches.length > 100) {
    c.add(["matches"], "too_big");
  } else {
    for (const [i, m] of rawMatches.entries()) {
      const parsed = match(c, m, ["matches", i]);
      if (parsed) matches.push(parsed);
    }
  }

  const excluded: { match: unknown; reason: unknown }[] = [];
  const rawExcluded = value.excluded;
  if (!Array.isArray(rawExcluded)) {
    c.add(["excluded"], "invalid_type");
    bounds(c, rawExcluded, ["excluded"], 0, 200);
  } else if (rawExcluded.length > 200) {
    c.add(["excluded"], "too_big");
  } else {
    for (const [i, e] of rawExcluded.entries()) {
      if (!isObject(e)) {
        c.add(["excluded", i], "invalid_type");
        continue;
      }
      text(c, e.match, ["excluded", i, "match"], 0, 200);
      text(c, e.reason, ["excluded", i, "reason"], 0, 40);
      excluded.push({ match: e.match, reason: e.reason });
    }
  }

  if (c.issues.length > 0) return { success: false, issues: c.issues };
  return {
    success: true,
    data: {
      schema_version: 1,
      run_date_utc: runDate as string,
      notes: notes as string | null,
      matches,
      excluded,
    } as unknown as ScreenerV1,
  };
}
