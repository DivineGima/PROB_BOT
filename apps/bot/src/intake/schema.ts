import { z } from "zod";

/**
 * Screener file contract, schema version 1 (architecture section 6.1, ADR-026).
 *
 * - Unknown extra keys are STRIPPED (Zod's default for objects), never fatal, so a harmless prompt
 *   change does not brick the day. A missing or mistyped required key is fatal.
 * - A fact the screener could not find is `null`, so every key below is required; nullable ones say so.
 * - Any change that is not purely additive-optional becomes `schema_version: 2` with a new parser
 *   beside this one; this schema never changes meaning.
 * - `packages/contracts/screener_v1.schema.json` is generated from this file (`scripts/gen-screener-schema.mjs`)
 *   and a test fails if the two drift apart.
 */

/** Hard cap on matches per file (section 3.1). Lives here so this file has no relative imports and
 * can be loaded by the contract generator under plain Node. */
export const MAX_MATCHES = 100;

export const COMPETITIONS = [
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
] as const;
export type CompetitionCode = (typeof COMPETITIONS)[number];

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const KICKOFF_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:00Z$/;

/** A real calendar date (rejects 2026-02-30, which `Date` would silently roll over). */
function isRealDate(value: string): boolean {
  const date = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === value;
}

const httpsUrl = z
  .string()
  .max(300)
  .regex(/^https:\/\/[^\s]+$/);

const absence = z.object({
  player: z.string().max(80),
  status: z.enum(["out", "doubtful"]),
  source_url: httpsUrl,
});

const match = z
  .object({
    match_id: z.string().min(1).max(160),
    competition: z.enum(COMPETITIONS),
    home: z.string().min(1).max(64),
    away: z.string().min(1).max(64),
    kickoff_utc: z
      .string()
      .regex(KICKOFF_RE)
      .refine((v) => isRealDate(v.slice(0, 10)) && Number.isFinite(Date.parse(v)), {
        message: "not a real instant",
      }),
    lineup_status: z.enum(["none", "expected", "confirmed"]),
    absences_home: z.array(absence).max(40).nullable(),
    absences_away: z.array(absence).max(40).nullable(),
    rest_days_home: z.number().int().min(0).max(60).nullable(),
    rest_days_away: z.number().int().min(0).max(60).nullable(),
    source_urls: z.array(httpsUrl).max(20),
  })
  .refine((m) => m.home !== m.away, { path: ["away"], message: "home and away must differ" });

const excluded = z.object({
  match: z.string().max(200),
  reason: z.string().max(40),
});

export const screenerV1Schema = z.object({
  schema_version: z.literal(1),
  run_date_utc: z.string().regex(DATE_RE).refine(isRealDate, { message: "not a real date" }),
  notes: z.string().max(2000).nullable(),
  matches: z.array(match).max(MAX_MATCHES),
  excluded: z.array(excluded).max(200),
});

export type ScreenerV1 = z.infer<typeof screenerV1Schema>;
export type ScreenerMatch = ScreenerV1["matches"][number];
