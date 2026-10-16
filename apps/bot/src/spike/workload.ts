import { bpGrid, dcGrid, type Grid, markets, mixGrids, piGrid } from "./grids";
import { buildSyntheticBlobs, type SpikeBlobs } from "./payload";
import { type SpikeMatch, spikeUploadSchema } from "./schema";

/**
 * Stage 1 CPU spike workload (ADR-013, section 8.10): the real-shaped steps of one upload.
 *   JSON parse -> schema validation (placeholder) -> parse 3 model blobs -> per match: 3 grids of
 *   169 cells (bivariate-Poisson sums included) -> linear pool -> markets -> render + split.
 * The request body is the upload (as the Telegram download would be). The three model blobs are JSON
 * strings built once at module load, standing in for `model_params.payload_json` rows read from D1,
 * so each request pays only for parsing them. The workload excludes grammY glue and D1 round trips,
 * so Stage 5 and Stage 7 re-measure the real path.
 */
const DEFAULT_BLOBS: SpikeBlobs = buildSyntheticBlobs();
export const SPIKE_WEIGHTS = [0.4, 0.3, 0.3];
const MAX_MESSAGE_CHARS = 3900;

interface TeamParams {
  attack: number;
  defence: number;
}

interface ModelBlob {
  home_advantage: number;
  rho: number;
  lambda3: number;
  league_total_goals: number;
  teams: Record<string, TeamParams>;
}

export interface WorkloadResult {
  matches: number;
  messages: number;
  characters: number;
  /** Sum of every rendered home-win probability; makes the result observable so it is not dead code. */
  checksum: number;
}

export class SpikeInputError extends Error {}

function parseBlob(text: string): ModelBlob {
  const blob = JSON.parse(text) as ModelBlob;
  if (typeof blob.teams !== "object" || blob.teams === null) {
    throw new SpikeInputError("model blob has no teams");
  }
  return blob;
}

function lookup(blob: ModelBlob, team: string): TeamParams {
  const params = blob.teams[team];
  if (!params) throw new SpikeInputError(`unknown team in spike payload: ${team}`);
  return params;
}

function pct(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

/** IST = UTC + 05:30, formatted by hand because Intl is comparatively expensive in a Worker. */
function istTime(kickoffUtc: string): string {
  const shifted = new Date(Date.parse(kickoffUtc) + 330 * 60_000);
  const hh = String(shifted.getUTCHours()).padStart(2, "0");
  const mm = String(shifted.getUTCMinutes()).padStart(2, "0");
  const nextDay = shifted.getUTCDate() !== Number(kickoffUtc.slice(8, 10)) ? " +1d" : "";
  return `${hh}:${mm} IST${nextDay}`;
}

function renderBlock(match: SpikeMatch, grid: Grid): { text: string; homeWin: number } {
  const m = markets(grid);
  const overs = ["0.5", "1.5", "2.5", "3.5", "4.5", "5.5"]
    .map((line, idx) => `O${line} ${pct(m.overs[idx] ?? 0)}`)
    .join(" | ");
  const text =
    `${match.competition}  ${match.home} v ${match.away}  ${istTime(match.kickoff_utc)}\n` +
    `1X2  ${pct(m.home)} / ${pct(m.draw)} / ${pct(m.away)}\n` +
    `${overs}\n` +
    `lineup: ${match.lineup_status}\n\n`;
  return { text, homeWin: m.home };
}

function split(blocks: string[]): string[] {
  const messages: string[] = [];
  let current = "";
  for (const block of blocks) {
    if (current.length + block.length > MAX_MESSAGE_CHARS && current.length > 0) {
      messages.push(current);
      current = "";
    }
    current += block;
  }
  if (current.length > 0) messages.push(current);
  return messages;
}

export function runWorkload(uploadText: string, blobs: SpikeBlobs = DEFAULT_BLOBS): WorkloadResult {
  let body: unknown;
  try {
    body = JSON.parse(uploadText);
  } catch {
    throw new SpikeInputError("body is not JSON");
  }
  const upload = spikeUploadSchema.safeParse(body);
  if (!upload.success) throw new SpikeInputError("upload schema invalid");

  const dc = parseBlob(blobs.dc);
  const pi = parseBlob(blobs.pi);
  const bp = parseBlob(blobs.bp);

  const blocks: string[] = [];
  let checksum = 0;
  for (const match of upload.data.matches) {
    const dcHome = lookup(dc, match.home);
    const dcAway = lookup(dc, match.away);
    const lambdaHome = Math.exp(dc.home_advantage + dcHome.attack - dcAway.defence) * 1.3;
    const lambdaAway = Math.exp(dcAway.attack - dcHome.defence) * 1.1;

    const piHome = lookup(pi, match.home);
    const piAway = lookup(pi, match.away);
    const diff = piHome.attack - piAway.attack + pi.home_advantage;
    const total = pi.league_total_goals;
    const piLambdaHome = Math.max(0.05, (total + diff) / 2);
    const piLambdaAway = Math.max(0.05, (total - diff) / 2);

    const bpHome = lookup(bp, match.home);
    const bpAway = lookup(bp, match.away);
    const bpLambda1 = Math.exp(bpHome.attack - bpAway.defence + bp.home_advantage) * 1.2;
    const bpLambda2 = Math.exp(bpAway.attack - bpHome.defence) * 1.0;

    const pooled = mixGrids(
      [
        dcGrid(lambdaHome, lambdaAway, dc.rho),
        piGrid(piLambdaHome, piLambdaAway),
        bpGrid(bpLambda1, bpLambda2, bp.lambda3),
      ],
      SPIKE_WEIGHTS,
    );
    const rendered = renderBlock(match, pooled);
    blocks.push(rendered.text);
    checksum += rendered.homeWin;
  }

  const messages = split(blocks);
  return {
    matches: upload.data.matches.length,
    messages: messages.length,
    characters: messages.reduce((sum, m) => sum + m.length, 0),
    checksum,
  };
}
