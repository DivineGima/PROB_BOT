import { z } from "zod";

/**
 * PLACEHOLDER for the schema-v1 screener contract (section 6.1), shaped like the real one so the
 * spike measures a realistic Zod cost. The real contract lands in Stage 5 under `intake/`.
 */
const httpsUrl = z.string().max(300).startsWith("https://");

const absence = z.object({
  player: z.string().max(80),
  status: z.enum(["out", "doubtful"]),
  source_url: httpsUrl,
});

const match = z.object({
  match_id: z.string().min(1).max(160),
  competition: z.enum(["EPL", "LL", "BL", "SA", "L1", "UCL", "ERE", "PPL", "CHA", "SPL"]),
  home: z.string().min(1).max(64),
  away: z.string().min(1).max(64),
  kickoff_utc: z.string().regex(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:00Z$/),
  lineup_status: z.enum(["none", "expected", "confirmed"]),
  absences_home: z.array(absence).max(40).nullable(),
  absences_away: z.array(absence).max(40).nullable(),
  rest_days_home: z.number().int().min(0).max(60).nullable(),
  rest_days_away: z.number().int().min(0).max(60).nullable(),
  source_urls: z.array(httpsUrl).max(20),
});

export const spikeUploadSchema = z.object({
  schema_version: z.literal(1),
  run_date_utc: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  notes: z.string().max(2000).nullable(),
  matches: z.array(match).max(100),
  excluded: z.array(z.object({ match: z.string().max(200), reason: z.string().max(40) })).max(200),
});

export type SpikeUpload = z.infer<typeof spikeUploadSchema>;
export type SpikeMatch = SpikeUpload["matches"][number];
