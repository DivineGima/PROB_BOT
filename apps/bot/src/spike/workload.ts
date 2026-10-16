import { bpGrid, dcGrid, type Grid, markets, mixGrids, piGrid } from "./grids";
import {
  buildSyntheticModelRows,
  MODEL_KINDS,
  type ModelKind,
  type SpikeModelRows,
} from "./payload";
import type { SpikeMatch } from "./schema";
import { validateUpload } from "./validate";

/**
 * Stage 1 CPU spike workload (ADR-013, section 8.10), with the F1 trims applied:
 *   JSON parse -> hand validation -> read ONLY the involved teams' rows for the 3 models -> per match:
 *   3 grids of 169 cells (bivariate-Poisson sums included) -> linear pool -> markets -> render + split.
 * The request body is the upload (as the Telegram download would be). The model rows are JSON strings
 * built once per isolate on the `x-spike-prime` request, standing in for `model_params` rows read from D1,
 * so each request pays only for parsing the rows it needs. The workload excludes grammY glue and D1 round
 * trips, so Stage 5 and Stage 7 re-measure the real path.
 */
let cachedModels: SpikeModelRows | undefined;

/**
 * Builds the synthetic model rows on first use. Doing it on demand (and not when the module loads) keeps
 * the harness's own generation cost out of the first measured request: the driver calls `primeModels`
 * first through the `x-spike-prime` header, as real model rows would already be in D1.
 */
export function primeModels(): void {
  cachedModels ??= buildSyntheticModelRows();
}

function defaultModels(): SpikeModelRows {
  primeModels();
  return cachedModels as SpikeModelRows;
}
export const SPIKE_WEIGHTS = [0.4, 0.3, 0.3];
const MAX_MESSAGE_CHARS = 3900;

interface TeamParams {
  attack: number;
  defence: number;
}

interface ModelMeta {
  home_advantage: number;
  rho: number;
  lambda3: number;
  league_total_goals: number;
}

interface LoadedModel {
  meta: ModelMeta;
  teams: Map<string, TeamParams>;
}

export interface WorkloadResult {
  matches: number;
  messages: number;
  characters: number;
  /** Sum of every rendered home-win probability; makes the result observable so it is not dead code. */
  checksum: number;
}

export class SpikeInputError extends Error {}

/** Reads the model's meta string and only the rows of the teams that appear in this upload. */
function loadModel(models: SpikeModelRows, kind: ModelKind, teams: Set<string>): LoadedModel {
  const metaText = models.meta[kind];
  if (typeof metaText !== "string") throw new SpikeInputError(`model ${kind} has no meta`);
  const meta = JSON.parse(metaText) as ModelMeta;
  const rows = models.rows[kind];
  const loaded = new Map<string, TeamParams>();
  for (const team of teams) {
    const text = rows?.[team];
    if (typeof text !== "string")
      throw new SpikeInputError(`unknown team in spike payload: ${team}`);
    loaded.set(team, JSON.parse(text) as TeamParams);
  }
  return { meta, teams: loaded };
}

function lookup(model: LoadedModel, team: string): TeamParams {
  return model.teams.get(team) as TeamParams;
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

export function runWorkload(
  uploadText: string,
  models: SpikeModelRows = defaultModels(),
): WorkloadResult {
  let body: unknown;
  try {
    body = JSON.parse(uploadText);
  } catch {
    throw new SpikeInputError("body is not JSON");
  }
  const upload = validateUpload(body);
  if (!upload) throw new SpikeInputError("upload schema invalid");

  const involved = new Set<string>();
  for (const match of upload.matches) {
    involved.add(match.home);
    involved.add(match.away);
  }
  const [dc, pi, bp] = MODEL_KINDS.map((kind) => loadModel(models, kind, involved)) as [
    LoadedModel,
    LoadedModel,
    LoadedModel,
  ];

  const blocks: string[] = [];
  let checksum = 0;
  for (const match of upload.matches) {
    const dcHome = lookup(dc, match.home);
    const dcAway = lookup(dc, match.away);
    const lambdaHome = Math.exp(dc.meta.home_advantage + dcHome.attack - dcAway.defence) * 1.3;
    const lambdaAway = Math.exp(dcAway.attack - dcHome.defence) * 1.1;

    const piHome = lookup(pi, match.home);
    const piAway = lookup(pi, match.away);
    const diff = piHome.attack - piAway.attack + pi.meta.home_advantage;
    const total = pi.meta.league_total_goals;
    const piLambdaHome = Math.max(0.05, (total + diff) / 2);
    const piLambdaAway = Math.max(0.05, (total - diff) / 2);

    const bpHome = lookup(bp, match.home);
    const bpAway = lookup(bp, match.away);
    const bpLambda1 = Math.exp(bpHome.attack - bpAway.defence + bp.meta.home_advantage) * 1.2;
    const bpLambda2 = Math.exp(bpAway.attack - bpHome.defence) * 1.0;

    const pooled = mixGrids(
      [
        dcGrid(lambdaHome, lambdaAway, dc.meta.rho),
        piGrid(piLambdaHome, piLambdaAway),
        bpGrid(bpLambda1, bpLambda2, bp.meta.lambda3),
      ],
      SPIKE_WEIGHTS,
    );
    const rendered = renderBlock(match, pooled);
    blocks.push(rendered.text);
    checksum += rendered.homeWin;
  }

  const messages = split(blocks);
  return {
    matches: upload.matches.length,
    messages: messages.length,
    characters: messages.reduce((sum, m) => sum + m.length, 0),
    checksum,
  };
}
