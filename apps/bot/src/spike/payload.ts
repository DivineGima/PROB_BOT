/**
 * Deterministic synthetic payloads for the CPU spike. Pure, erasable-syntax TypeScript so Node
 * can import it directly from `scripts/cpu-spike.mjs` and Vitest can import it in tests.
 */
export type ModelKind = "dc" | "pi" | "bp";
export const MODEL_KINDS: readonly ModelKind[] = ["dc", "pi", "bp"];

/**
 * Model parameters as they would sit in D1 after the F1 trim: one small JSON "meta" string per model
 * (league-wide numbers) and one JSON string per team per model. The Worker reads and parses only the
 * rows of the teams in the upload, not the whole model.
 */
export interface SpikeModelRows {
  meta: Record<ModelKind, string>;
  rows: Record<ModelKind, Record<string, string>>;
}

/** mulberry32: small deterministic PRNG so every run measures the same bytes. */
export function makeRng(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const COMPETITIONS = ["EPL", "LL", "BL", "SA", "L1", "ERE", "PPL", "CHA", "SPL"] as const;
const LINEUP = ["none", "expected", "confirmed"] as const;
const TEAM_COUNT = 240;

export function teamName(index: number): string {
  return `Synthetic Club ${String(index).padStart(3, "0")}`;
}

const round = (value: number, digits: number): number => Number(value.toFixed(digits));

/** One team's parameters for one model. The history array pads the row to the documented size. */
function buildTeamRow(rng: () => number, kind: ModelKind): string {
  const entry: Record<string, unknown> = {
    attack: round(rng() * 0.8 - 0.4, 6),
    defence: round(rng() * 0.8 - 0.4, 6),
    n: 20 + Math.floor(rng() * 100),
    history: Array.from({ length: 12 }, () => round(rng() * 2 - 1, 6)),
  };
  if (kind === "pi") entry.away_rating = round(rng() * 1.2 - 0.6, 6);
  return JSON.stringify(entry);
}

/** A schema-v1-shaped upload of `matchCount` matches (about 1 KB per match, section 3.2). */
export function buildSyntheticUpload(matchCount = 60, seed = 20261016): unknown {
  const rng = makeRng(seed);
  const matches = Array.from({ length: matchCount }, (_, n) => {
    const home = Math.floor(rng() * TEAM_COUNT);
    const away = (home + 1 + Math.floor(rng() * (TEAM_COUNT - 1))) % TEAM_COUNT;
    const hour = 12 + Math.floor(rng() * 9);
    const absences = (count: number) =>
      count === 0
        ? null
        : Array.from({ length: count }, (_, k) => ({
            player: `Player ${n}-${k}`,
            status: rng() < 0.5 ? ("out" as const) : ("doubtful" as const),
            source_url: `https://example.invalid/injuries/${n}/${k}`,
          }));
    return {
      match_id: `2026-10-17_${COMPETITIONS[n % COMPETITIONS.length]}_${teamName(home)}_${teamName(away)}`,
      competition: COMPETITIONS[n % COMPETITIONS.length],
      home: teamName(home),
      away: teamName(away),
      kickoff_utc: `2026-10-17T${String(hour).padStart(2, "0")}:${rng() < 0.5 ? "00" : "30"}:00Z`,
      lineup_status: LINEUP[Math.floor(rng() * LINEUP.length)],
      absences_home: absences(Math.floor(rng() * 4)),
      absences_away: absences(Math.floor(rng() * 4)),
      rest_days_home: 2 + Math.floor(rng() * 8),
      rest_days_away: 2 + Math.floor(rng() * 8),
      source_urls: [
        `https://example.invalid/fixtures/${n}`,
        `https://example.invalid/lineups/${n}`,
        `https://example.invalid/form/${n}`,
      ],
    };
  });
  const excluded = Array.from({ length: 30 }, (_, n) => ({
    match: `${teamName(n)} vs ${teamName(n + 1)}`,
    reason: n % 2 === 0 ? "G1_FORM" : "G5_ABSENCES",
  }));
  return {
    schema_version: 1,
    run_date_utc: "2026-10-17",
    notes: "synthetic spike payload",
    matches,
    excluded,
  };
}

/** All three models as per-team rows plus a small meta string each (section 5.4 sizes, 240 teams). */
export function buildSyntheticModelRows(seed = 4242): SpikeModelRows {
  const rng = makeRng(seed);
  const meta = {} as Record<ModelKind, string>;
  const rows = {} as Record<ModelKind, Record<string, string>>;
  for (const kind of MODEL_KINDS) {
    meta[kind] = JSON.stringify({
      version: 1,
      model: kind,
      home_advantage: 0.25,
      rho: -0.05,
      lambda3: 0.1,
      league_total_goals: 2.7,
    });
    const perTeam: Record<string, string> = {};
    for (let t = 0; t < TEAM_COUNT; t++) perTeam[teamName(t)] = buildTeamRow(rng, kind);
    rows[kind] = perTeam;
  }
  return { meta, rows };
}
