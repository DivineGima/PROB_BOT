import contract from "../../../../packages/contracts/display.json";

/**
 * [v4] Display helpers (architecture 4, ADR-053, ADR-056, ADR-057). Pure functions over stored
 * probabilities: emoji bars, the favourite label, the strongest call and the grade. The rules live in
 * `packages/contracts/display.json`, which the Python job reads too (`footy/report/display.py`), so a
 * Telegram reply and a chart never disagree. Display only: nothing here changes a stored number.
 */

export const DISPLAY = contract;

export type Outcome = "home" | "draw" | "away";
export type CallKey =
  | "home"
  | "draw"
  | "away"
  | "over_1.5"
  | "under_1.5"
  | "over_2.5"
  | "under_2.5"
  | "over_3.5"
  | "under_3.5";

export interface StrongestCall {
  key: CallKey;
  p: number;
}

const OUTCOMES: readonly Outcome[] = ["home", "draw", "away"];
/** Index of each over line in the stored `overs` array (0.5 .. 5.5). */
const OVER_INDEX: Readonly<Record<string, number>> = { "1.5": 1, "2.5": 2, "3.5": 3 };

/** Number of filled cells: floor(p * cells + 0.5), clamped (the same rule in Python). */
export function filledCells(p: number, cells = DISPLAY.bar.cells): number {
  const clamped = Number.isFinite(p) ? Math.min(1, Math.max(0, p)) : 0;
  return Math.min(cells, Math.floor(clamped * cells + 0.5));
}

/** `🟩🟩🟩🟩⬜⬜⬜⬜⬜⬜` for 0.44 with the home cell. */
export function bar(p: number, cell: string): string {
  const n = filledCells(p);
  return cell.repeat(n) + DISPLAY.bar.empty.repeat(DISPLAY.bar.cells - n);
}

/** A whole percent, `44%` (half up). */
export function pct0(p: number): string {
  return Number.isFinite(p) ? `${Math.floor(p * 100 + 0.5)}%` : "n/a";
}

/** The most likely of home, draw and away; on a tie (within the tolerance) the earlier one. */
export function favouriteOf(p1x2: readonly [number, number, number]): {
  outcome: Outcome;
  p: number;
} {
  let best = 0;
  for (let i = 1; i < 3; i++) {
    if ((p1x2[i] ?? 0) > (p1x2[best] ?? 0) + DISPLAY.strongest_call.tie_tolerance) best = i;
  }
  return { outcome: OUTCOMES[best] as Outcome, p: p1x2[best] ?? 0 };
}

export function favouriteLabel(p: number): string {
  for (const label of DISPLAY.favourite_labels) if (p >= label.min) return label.text;
  return DISPLAY.favourite_labels.at(-1)?.text ?? "";
}

/** The probability of one strongest-call candidate. `overs` holds P(over 0.5) .. P(over 5.5). */
export function callProbability(
  key: CallKey,
  p1x2: readonly [number, number, number],
  overs: readonly number[],
): number {
  if (key === "home") return p1x2[0];
  if (key === "draw") return p1x2[1];
  if (key === "away") return p1x2[2];
  const [side, line] = key.split("_") as ["over" | "under", string];
  const over = overs[OVER_INDEX[line] ?? -1] ?? Number.NaN;
  return side === "over" ? over : 1 - over;
}

/** The single outcome the bot is most sure of among the contract's candidates (ADR-057). */
export function strongestCall(
  p1x2: readonly [number, number, number],
  overs: readonly number[],
): StrongestCall {
  let best: StrongestCall | null = null;
  for (const key of DISPLAY.strongest_call.candidates as CallKey[]) {
    const p = callProbability(key, p1x2, overs);
    if (!Number.isFinite(p)) continue;
    if (best === null || p > best.p + DISPLAY.strongest_call.tie_tolerance) best = { key, p };
  }
  return best ?? { key: "home", p: p1x2[0] };
}

/** `Bayern Munich win`, `Draw`, `Over 1.5 goals (2+)`, `Under 3.5 goals (3 or fewer)`. */
export function callText(key: CallKey, home: string, away: string): string {
  if (key === "home") return `${home} win`;
  if (key === "away") return `${away} win`;
  if (key === "draw") return "Draw";
  const [side, line] = key.split("_") as ["over" | "under", string];
  const goals = Math.floor(Number(line) + 0.5);
  return side === "over"
    ? `Over ${line} goals (${goals}+)`
    : `Under ${line} goals (${goals - 1} or fewer)`;
}

export function outcomeOf(goals: readonly [number, number]): Outcome {
  return goals[0] > goals[1] ? "home" : goals[0] === goals[1] ? "draw" : "away";
}

/** Did a call come true for this 90-minute score? */
export function callHit(key: CallKey, goals: readonly [number, number]): boolean {
  if (key === "home" || key === "draw" || key === "away") return outcomeOf(goals) === key;
  const [side, line] = key.split("_") as ["over" | "under", string];
  const total = goals[0] + goals[1];
  return side === "over" ? total > Number(line) : total < Number(line);
}

/** `🟢 good` / `🟡 fair` / `🔴 poor` for a 1X2 RPS (lower is better). */
export function grade(rps: number | null): string {
  if (rps === null || !Number.isFinite(rps)) return "n/a";
  for (const g of DISPLAY.grades) if (g.max === null || rps < g.max) return g.text;
  return DISPLAY.grades.at(-1)?.text ?? "";
}

export function verdictIcon(verdict: string): string {
  return (DISPLAY.verdict_icons as Record<string, string>)[verdict] ?? "❔";
}

export function omissionIcon(reason: string): string {
  return (DISPLAY.omission_icons as Record<string, string>)[reason] ?? "❔";
}

export const OUTCOME_ICON: Readonly<Record<Outcome, string>> = {
  home: "🏠",
  draw: "🤝",
  away: "✈️",
};
