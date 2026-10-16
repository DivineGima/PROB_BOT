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

/**
 * Reads records from any of the shapes Cloudflare tooling produces: a JSON array, JSON Lines, or the
 * stream of multi-line (pretty-printed) objects that `wrangler tail --format json` writes. Text outside
 * the objects (for example the "connected" banner) is ignored. `invalid` counts balanced `{...}` blocks
 * that were not valid JSON.
 * @param {string} text
 */
export function parseRecords(text) {
  const trimmed = text.trim();
  if (trimmed.startsWith("[")) {
    try {
      return { records: /** @type {unknown[]} */ (JSON.parse(trimmed)), invalid: 0 };
    } catch {
      // fall through to the stream scanner
    }
  }
  /** @type {unknown[]} */
  const records = [];
  let invalid = 0;
  let depth = 0;
  let start = -1;
  let inString = false;
  let escaped = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inString) {
      if (escaped) escaped = false;
      else if (c === "\\") escaped = true;
      else if (c === '"') inString = false;
      continue;
    }
    if (depth > 0 && c === '"') inString = true;
    else if (c === "{") {
      if (depth === 0) start = i;
      depth += 1;
    } else if (c === "}" && depth > 0) {
      depth -= 1;
      if (depth === 0) {
        try {
          records.push(JSON.parse(text.slice(start, i + 1)));
        } catch {
          invalid += 1;
        }
      }
    }
  }
  return { records, invalid };
}

/**
 * Keeps only invocations of the spike route that answered 200, so stray requests (a 401 from a wrong
 * header, the 204 prime request, a Telegram update) never enter the statistics. Records without request
 * details (Workers Logs exports, plain numbers) are kept.
 * @param {unknown} record
 */
export function isMeasured(record) {
  const r = /** @type {Record<string, any>} */ (record ?? {});
  const url = r.event?.request?.url;
  if (typeof url !== "string") return true;
  if (!url.includes("/spike/")) return false;
  const status = r.event?.response?.status;
  return status === undefined || status === 200;
}

/** Number of leading requests reported separately: they run on a cold or only partly warmed isolate. */
export const COLD_REQUESTS = 5;

/**
 * Turns raw records into the CPU series, in the order the requests happened.
 * @param {unknown[]} records
 */
export function cpuSeries(records) {
  const measured = records.filter(isMeasured);
  const withTime = measured.filter(
    (r) => typeof (/** @type {any} */ (r).eventTimestamp) === "number",
  );
  const ordered =
    withTime.length === measured.length
      ? [...measured].sort(
          (a, b) => /** @type {any} */ (a).eventTimestamp - /** @type {any} */ (b).eventTimestamp,
        )
      : measured;
  const values = /** @type {number[]} */ (ordered.map(extractCpuMs).filter((v) => v !== null));
  return { values, excluded: records.length - measured.length };
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
  const { values, excluded } = cpuSeries(records);
  const s = summarise(values, { minInvocations: min });
  const warm = values.length > COLD_REQUESTS + 4 ? summarise(values.slice(COLD_REQUESTS)) : null;
  console.log(
    JSON.stringify({
      n: s.n,
      p50_ms: s.p50,
      p95_ms: s.p95,
      max_ms: s.max,
      first_requests_ms: values.slice(0, COLD_REQUESTS),
      after_first_requests: warm
        ? { n: warm.n, p50_ms: warm.p50, p95_ms: warm.p95, max_ms: warm.max }
        : null,
      other_requests_ignored: excluded,
      unreadable_blocks: invalid,
    }),
  );
  console.log(s.verdict);
  console.log(
    "note: Workers reports cpuTime in whole milliseconds, so a 'p95 of 6' may hide 5.5-6.4 ms.",
  );
  process.exitCode = s.passed ? 0 : s.enough ? 1 : 2;
}
