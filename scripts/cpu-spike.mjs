// @ts-check
// Driver for the Stage 1 CPU spike (ADR-013). Sends the deterministic 60-match synthetic upload to the
// deployed Worker N times. It does NOT measure CPU: read `cpuTime` from Workers Logs or `wrangler tail`
// afterwards and feed it to scripts/cpu-stats.mjs. Enable the path first with SPIKE_ENABLED=1 and
// switch it off again when the gate is recorded.
//
//   WORKER_URL=https://... WEBHOOK_PATH_SECRET=... TELEGRAM_WEBHOOK_SECRET=... \
//     node scripts/cpu-spike.mjs [--n 25] [--matches 60]
import { fileURLToPath } from "node:url";
import { buildSyntheticUpload } from "../apps/bot/src/spike/payload.ts";

/**
 * @param {{ workerUrl: string, pathSecret: string, headerSecret: string, n: number, matches: number, fetchImpl?: typeof fetch, pauseMs?: number }} input
 */
export async function driveSpike({
  workerUrl,
  pathSecret,
  headerSecret,
  n,
  matches,
  fetchImpl = fetch,
  pauseMs = 300,
}) {
  const url = `${new URL(workerUrl).origin}/spike/${pathSecret}`;
  const body = JSON.stringify(buildSyntheticUpload(matches));
  /** @type {Record<string, number>} */
  const statuses = {};
  /** @type {number[]} */
  const wallMs = [];
  for (let i = 0; i < n; i++) {
    const started = performance.now();
    const response = await fetchImpl(url, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-telegram-bot-api-secret-token": headerSecret,
      },
      body,
    });
    await response.arrayBuffer();
    wallMs.push(performance.now() - started);
    statuses[response.status] = (statuses[response.status] ?? 0) + 1;
    if (pauseMs > 0) await new Promise((resolve) => setTimeout(resolve, pauseMs));
  }
  return { n, bodyBytes: Buffer.byteLength(body), statuses, wallMs };
}

/** @param {string[]} args @param {string} flag @param {number} fallback */
function numberFlag(args, flag, fallback) {
  const i = args.indexOf(flag);
  const value = i >= 0 ? Number(args[i + 1]) : fallback;
  if (!Number.isInteger(value) || value < 1 || value > 1000)
    throw new Error(`${flag} must be an integer from 1 to 1000`);
  return value;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2);
  const env = process.env;
  const result = await driveSpike({
    workerUrl: env.WORKER_URL ?? "",
    pathSecret: env.WEBHOOK_PATH_SECRET ?? "",
    headerSecret: env.TELEGRAM_WEBHOOK_SECRET ?? "",
    n: numberFlag(args, "--n", 25),
    matches: numberFlag(args, "--matches", 60),
  });
  const sorted = [...result.wallMs].sort((a, b) => a - b);
  console.log(
    JSON.stringify({
      sent: result.n,
      body_bytes: result.bodyBytes,
      http_statuses: result.statuses,
      wall_ms_median: Math.round(sorted[Math.floor(sorted.length / 2)] ?? 0),
    }),
  );
  console.log(
    "Now read cpuTime for these invocations (Workers Logs or `wrangler tail --format json`) and run scripts/cpu-stats.mjs.",
  );
  process.exitCode = Object.keys(result.statuses).every((s) => s === "200") ? 0 : 1;
}
