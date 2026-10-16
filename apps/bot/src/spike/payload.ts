/**
 * Deterministic synthetic payloads for the CPU spike. Pure, erasable-syntax TypeScript so Node
 * can import it directly from `scripts/cpu-spike.mjs` and Vitest can import it in tests.
 */
export interface SpikeBlobs {
  dc: string;
  pi: string;
  bp: string;
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

/**
 * One model blob per model, as a JSON string exactly like `model_params.payload_json` (about
 * 30-60 KB each, section 5.4). Per-team arrays pad the size toward the documented range.
 */
function buildBlob(rng: () => number, kind: "dc" | "pi" | "bp"): string {
  const teams: Record<string, unknown> = {};
  for (let t = 0; t < TEAM_COUNT; t++) {
    const entry: Record<string, unknown> = {
      attack: round(rng() * 0.8 - 0.4, 6),
      defence: round(rng() * 0.8 - 0.4, 6),
      n: 20 + Math.floor(rng() * 100),
      history: Array.from({ length: 12 }, () => round(rng() * 2 - 1, 6)),
    };
    if (kind === "pi") entry.away_rating = round(rng() * 1.2 - 0.6, 6);
    teams[teamName(t)] = entry;
  }
  return JSON.stringify({
    version: 1,
    model: kind,
    home_advantage: 0.25,
    rho: -0.05,
    lambda3: 0.1,
    league_total_goals: 2.7,
    teams,
  });
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

/** The three model blobs as JSON strings, like rows read from `model_params.payload_json`. */
export function buildSyntheticBlobs(seed = 4242): SpikeBlobs {
  const rng = makeRng(seed);
  return { dc: buildBlob(rng, "dc"), pi: buildBlob(rng, "pi"), bp: buildBlob(rng, "bp") };
}
