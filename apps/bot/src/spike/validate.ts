import type { SpikeUpload } from "./schema";

/**
 * F1 trim (architecture section 8.10): a hand-written validator for the bulk upload instead of Zod.
 * It enforces exactly the constraints of the Zod placeholder schema in `schema.ts` (unknown keys are
 * ignored, like Zod's default), and `test/validate.test.ts` checks the two agree on hundreds of
 * mutated payloads. Returns the upload on success and null on any violation.
 */

const COMPETITIONS = new Set(["EPL", "LL", "BL", "SA", "L1", "UCL", "ERE", "PPL", "CHA", "SPL"]);
const LINEUP = new Set(["none", "expected", "confirmed"]);
const ABSENCE_STATUS = new Set(["out", "doubtful"]);
const RUN_DATE = /^\d{4}-\d{2}-\d{2}$/;
const KICKOFF = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:00Z$/;

type Obj = Record<string, unknown>;

const isObject = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);
const str = (v: unknown, min: number, max: number): v is string =>
  typeof v === "string" && v.length >= min && v.length <= max;
const httpsUrl = (v: unknown): boolean => str(v, 0, 300) && v.startsWith("https://");
const restDays = (v: unknown): boolean =>
  v === null || (typeof v === "number" && Number.isInteger(v) && v >= 0 && v <= 60);

function absences(v: unknown): boolean {
  if (v === null) return true;
  if (!Array.isArray(v) || v.length > 40) return false;
  for (const a of v) {
    if (!isObject(a)) return false;
    if (!str(a.player, 0, 80)) return false;
    if (typeof a.status !== "string" || !ABSENCE_STATUS.has(a.status)) return false;
    if (!httpsUrl(a.source_url)) return false;
  }
  return true;
}

function validMatch(m: unknown): boolean {
  if (!isObject(m)) return false;
  if (!str(m.match_id, 1, 160)) return false;
  if (typeof m.competition !== "string" || !COMPETITIONS.has(m.competition)) return false;
  if (!str(m.home, 1, 64) || !str(m.away, 1, 64)) return false;
  if (typeof m.kickoff_utc !== "string" || !KICKOFF.test(m.kickoff_utc)) return false;
  if (typeof m.lineup_status !== "string" || !LINEUP.has(m.lineup_status)) return false;
  if (!absences(m.absences_home) || !absences(m.absences_away)) return false;
  if (!restDays(m.rest_days_home) || !restDays(m.rest_days_away)) return false;
  if (!Array.isArray(m.source_urls) || m.source_urls.length > 20) return false;
  for (const u of m.source_urls) if (!httpsUrl(u)) return false;
  return true;
}

export function validateUpload(value: unknown): SpikeUpload | null {
  if (!isObject(value)) return null;
  if (value.schema_version !== 1) return null;
  if (typeof value.run_date_utc !== "string" || !RUN_DATE.test(value.run_date_utc)) return null;
  if (value.notes !== null && !str(value.notes, 0, 2000)) return null;

  const matches = value.matches;
  if (!Array.isArray(matches) || matches.length > 100) return null;
  for (const m of matches) if (!validMatch(m)) return null;

  const excluded = value.excluded;
  if (!Array.isArray(excluded) || excluded.length > 200) return null;
  for (const e of excluded) {
    if (!isObject(e) || !str(e.match, 0, 200) || !str(e.reason, 0, 40)) return null;
  }
  return value as SpikeUpload;
}
