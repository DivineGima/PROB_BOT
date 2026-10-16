// @ts-check
// INDICATIVE local timing of the spike workload (Node/V8, not workerd). It exists to catch a workload
// that is wildly over budget before anything is deployed; it is NOT the ADR-013 gate, which uses production
// `cpuTime` from Workers Logs.
//
//   npx wrangler deploy --dry-run --outdir .measurements/bundle   (from apps/bot)
//   node scripts/cpu-local-bench.mjs .measurements/bundle/index.js [--n 40]
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { buildSyntheticUpload } from "../apps/bot/src/spike/payload.ts";
import { percentile } from "./cpu-stats.mjs";

/**
 * @param {{ fetch(request: Request, env: unknown, ctx: unknown): Promise<Response> }} worker
 * @param {{ n: number, matches: number }} options
 * @returns {Promise<{ cpuMs: number[], bodyBytes: number }>}
 */
export async function benchWorker(worker, { n, matches }) {
  const pathSecret = "bench-path-secret-0123456789";
  const headerSecret = "bench-header-secret-0123456789";
  const env = {
    WEBHOOK_PATH_SECRET: pathSecret,
    TELEGRAM_WEBHOOK_SECRET: headerSecret,
    SPIKE_ENABLED: "1",
  };
  const ctx = { waitUntil() {}, passThroughOnException() {} };
  const body = JSON.stringify(buildSyntheticUpload(matches));
  const make = () =>
    new Request(`https://bench.invalid/spike/${pathSecret}`, {
      method: "POST",
      headers: {
        "x-telegram-bot-api-secret-token": headerSecret,
        "content-type": "application/json",
      },
      body,
    });

  // Warm-up: first calls pay JIT and module costs the Worker also pays once per isolate.
  for (let i = 0; i < 5; i++) await (await worker.fetch(make(), env, ctx)).arrayBuffer();

  /** @type {number[]} */
  const cpuMs = [];
  for (let i = 0; i < n; i++) {
    const request = make();
    // High-resolution wall time of an almost entirely synchronous workload. process.cpuUsage() is not
    // used: on Windows it only advances in ~15.6 ms ticks, which would hide a 6 ms budget entirely.
    const before = performance.now();
    const response = await worker.fetch(request, env, ctx);
    const elapsed = performance.now() - before;
    if (response.status !== 200) throw new Error(`spike answered HTTP ${response.status}`);
    await response.arrayBuffer();
    cpuMs.push(elapsed);
  }
  return { cpuMs, bodyBytes: Buffer.byteLength(body) };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2);
  const bundle = args.find((a) => !a.startsWith("--"));
  if (!bundle) {
    console.error("usage: node scripts/cpu-local-bench.mjs <bundle/index.js> [--n 40]");
    process.exit(64);
  }
  const nIdx = args.indexOf("--n");
  const n = nIdx >= 0 ? Number(args[nIdx + 1]) : 40;
  const module = await import(pathToFileURL(path.resolve(bundle)).href);
  const result = await benchWorker(module.default, { n, matches: 60 });
  const sorted = [...result.cpuMs].sort((a, b) => a - b);
  const fixed = (/** @type {number} */ v) => Number(v.toFixed(2));
  console.log(
    JSON.stringify({
      runtime: `node ${process.version}`,
      indicative_only: true,
      invocations: n,
      body_bytes: result.bodyBytes,
      cpu_ms: {
        p50: fixed(percentile(sorted, 50)),
        p95: fixed(percentile(sorted, 95)),
        max: fixed(sorted[sorted.length - 1] ?? 0),
      },
    }),
  );
}
