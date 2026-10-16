// @ts-check
// CPU gate statistics (ADR-013, architecture section 8.10, Essentials 1 Stage 1 steps 7-8).
// Reads the `cpuTime` of invocation records exported from Workers Logs, or captured with
// `wrangler tail --format json`, and prints p50 / p95 / max against the gate.
//
//   node scripts/cpu-stats.mjs invocations.jsonl [--min 20]
//
// Exit codes: 0 gate passed, 1 gate failed, 2 not enough invocations to judge.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

export const GATE = Object.freeze({ p95Ms: 6, hardLimitMs: 10, minInvocations: 20 });

/**
 * Nearest-rank percentile of an ascending-sorted list: the smallest value with at least p% of
 * the sample at or below it. p95 of 20 samples is therefore the 19th value.
 * @param {number[]} sorted
 * @param {number} p 0 < p <= 100
 */
export function percentile(sorted, p) {
  if (sorted.length === 0) return Number.NaN;
  const rank = Math.ceil((p / 100) * sorted.length);
  return /** @type {number} */ (sorted[Math.min(sorted.length, Math.max(1, rank)) - 1]);
}

/**
 * Finds the CPU time in ms in one record. Accepts the shapes Cloudflare produces:
 * tail events (`cpuTime`), Workers Logs (`$workers.cpuTimeMs`, nested or flattened) and `cpuTimeMs`.
 * @param {unknown} record
 * @returns {number | null}
 */
export function extractCpuMs(record) {
  if (typeof record !== "object" || record === null) return null;
  const r = /** @type {Record<string, any>} */ (record);
  const candidates = [
    r.cpuTime,
    r.cpuTimeMs,
    r.$workers?.cpuTimeMs,
    r["$workers.cpuTimeMs"],
    r.event?.cpuTime,
  ];
  for (const c of candidates) {
    if (typeof c === "number" && Number.isFinite(c) && c >= 0) return c;
  }
  return null;
}

/** @param {string} text JSON Lines or a single JSON array */
export function parseRecords(text) {
  const trimmed = text.trim();
  if (trimmed.startsWith("[")) {
    return { records: /** @type {unknown[]} */ (JSON.parse(trimmed)), invalid: 0 };
  }
  /** @type {unknown[]} */
  const records = [];
  let invalid = 0;
  for (const line of trimmed.split(/\r?\n/)) {
    if (!line.trim()) continue;
    try {
      records.push(JSON.parse(line));
    } catch {
      invalid += 1;
    }
  }
  return { records, invalid };
}

/**
 * @param {number[]} values CPU ms per invocation
 * @param {{ minInvocations?: number }} [options]
 */
export function summarise(values, { minInvocations = GATE.minInvocations } = {}) {
  const sorted = [...values].sort((a, b) => a - b);
  const p50 = percentile(sorted, 50);
  const p95 = percentile(sorted, 95);
  const max = sorted.length ? /** @type {number} */ (sorted[sorted.length - 1]) : Number.NaN;
  const enough = sorted.length >= minInvocations;
  const passed = enough && p95 <= GATE.p95Ms && max < GATE.hardLimitMs;
  let verdict;
  if (!enough)
    verdict = `INSUFFICIENT: ${sorted.length} invocations, need at least ${minInvocations}`;
  else if (passed)
    verdict = "PASS: p95 within 6 ms and no invocation near the 10 ms limit; proceed";
  else
    verdict =
      "FAIL: apply F1 and re-measure; escalate F2/F3 and the pre-computed-grids idea to Divine";
  return { n: sorted.length, p50, p95, max, enough, passed, verdict };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const [file, ...rest] = process.argv.slice(2);
  if (!file) {
    console.error("usage: node scripts/cpu-stats.mjs <invocations.jsonl> [--min N]");
    process.exit(64);
  }
  const minIdx = rest.indexOf("--min");
  const min = minIdx >= 0 ? Number(rest[minIdx + 1]) : GATE.minInvocations;
  const { records, invalid } = parseRecords(readFileSync(file, "utf8"));
  const values = records.map(extractCpuMs).filter((v) => v !== null);
  const skipped = records.length - values.length;
  const s = summarise(/** @type {number[]} */ (values), { minInvocations: min });
  console.log(
    JSON.stringify({
      n: s.n,
      p50_ms: s.p50,
      p95_ms: s.p95,
      max_ms: s.max,
      skipped_without_cpu: skipped,
      unparseable_lines: invalid,
    }),
  );
  console.log(s.verdict);
  console.log(
    "note: Workers reports cpuTime in whole milliseconds, so a 'p95 of 6' may hide 5.5-6.4 ms.",
  );
  process.exitCode = s.passed ? 0 : s.enough ? 1 : 2;
}
