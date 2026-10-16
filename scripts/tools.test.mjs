// @ts-check
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { benchWorker } from "./cpu-local-bench.mjs";
import { driveSpike } from "./cpu-spike.mjs";
import { extractCpuMs, GATE, parseRecords, percentile, summarise } from "./cpu-stats.mjs";
import { buildRegistration, setWebhook } from "./set-webhook.mjs";
import { runSmoke } from "./smoke.mjs";
import { isMergedPrCommit, verifyMergedPr } from "./verify-merged-pr.mjs";

const SHA = "a".repeat(40);
const PATH_SECRET = "path-secret-0123456789";
const HEADER_SECRET = "header-secret-0123456789";
const BOT_TOKEN = "123456:BOT-TOKEN-VALUE";

/** @param {unknown} body @param {number} [status] */
const json = (body, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

describe("cpu-stats", () => {
  const one20 = Array.from({ length: 20 }, (_, i) => i + 1);

  it("computes nearest-rank percentiles by hand-checkable cases", () => {
    assert.equal(percentile(one20, 50), 10);
    assert.equal(percentile(one20, 95), 19);
    assert.equal(percentile(one20, 100), 20);
    assert.equal(percentile([7], 95), 7);
    assert.equal(percentile([1, 2], 50), 1);
    assert.ok(Number.isNaN(percentile([], 95)));
  });

  it("extracts cpu time from tail events, Workers Logs and flattened records", () => {
    assert.equal(extractCpuMs({ cpuTime: 3, wallTime: 9 }), 3);
    assert.equal(extractCpuMs({ $workers: { cpuTimeMs: 4 } }), 4);
    assert.equal(extractCpuMs({ "$workers.cpuTimeMs": 5 }), 5);
    assert.equal(extractCpuMs({ cpuTimeMs: 0 }), 0);
    assert.equal(extractCpuMs({ event: { cpuTime: 2 } }), 2);
    for (const bad of [
      null,
      "x",
      5,
      {},
      { cpuTime: "3" },
      { cpuTime: -1 },
      { cpuTime: Number.NaN },
    ]) {
      assert.equal(extractCpuMs(bad), null);
    }
  });

  it("parses JSON Lines tolerating blank and broken lines, and JSON arrays", () => {
    const parsed = parseRecords('{"cpuTime":1}\n\n{broken\n{"cpuTime":2}\r\n');
    assert.equal(parsed.records.length, 2);
    assert.equal(parsed.invalid, 1);
    assert.equal(parseRecords('[{"cpuTime":1},{"cpuTime":2}]').records.length, 2);
  });

  it("passes when p95 <= 6 ms and max < 10 ms with enough invocations", () => {
    const values = [...Array.from({ length: 19 }, () => 4), 5];
    const s = summarise(values);
    assert.equal(s.passed, true);
    assert.match(s.verdict, /^PASS/);
  });

  it("treats exactly 6 ms as passing and anything above as failing", () => {
    assert.equal(summarise(Array.from({ length: 20 }, () => 6)).passed, true);
    assert.equal(summarise(Array.from({ length: 20 }, () => 6.01)).passed, false);
  });

  it("fails when any invocation reaches the 10 ms limit even if p95 is low", () => {
    const values = [...Array.from({ length: 24 }, () => 2), 10];
    const s = summarise(values);
    assert.equal(s.p95 <= 6, true);
    assert.equal(s.passed, false);
    assert.match(s.verdict, /^FAIL/);
  });

  it("reports insufficient data below the minimum instead of passing", () => {
    const s = summarise([1, 1, 1]);
    assert.equal(s.enough, false);
    assert.equal(s.passed, false);
    assert.match(s.verdict, /^INSUFFICIENT/);
    assert.equal(GATE.minInvocations, 20);
  });
});

describe("verify-merged-pr", () => {
  const merged = {
    merged_at: "2026-10-16T00:00:00Z",
    merge_commit_sha: SHA,
    base: { ref: "main" },
  };

  it("accepts the commit produced by a merged PR into main", () => {
    assert.equal(isMergedPrCommit(SHA, [merged]).ok, true);
  });

  it("refuses a direct push, an unmerged PR, another commit, another base and bad input", () => {
    assert.equal(isMergedPrCommit(SHA, []).ok, false);
    assert.equal(isMergedPrCommit(SHA, [{ ...merged, merged_at: null }]).ok, false);
    assert.equal(
      isMergedPrCommit(SHA, [{ ...merged, merge_commit_sha: "b".repeat(40) }]).ok,
      false,
    );
    assert.equal(isMergedPrCommit(SHA, [{ ...merged, base: { ref: "dev" } }]).ok, false);
    assert.equal(isMergedPrCommit(SHA, { message: "Not Found" }).ok, false);
    assert.equal(isMergedPrCommit("abc", [merged]).ok, false);
    assert.equal(isMergedPrCommit(SHA, [null]).ok, false);
  });

  it("asks the GitHub API for the commit's pull requests and honours its answer", async () => {
    /** @type {string[]} */
    const urls = [];
    const fetchImpl = /** @type {typeof fetch} */ (
      async (url) => {
        urls.push(String(url));
        return json([merged]);
      }
    );
    const result = await verifyMergedPr({
      repo: "DivineGima/PROB_BOT",
      sha: SHA,
      token: "t",
      fetchImpl,
    });
    assert.equal(result.ok, true);
    assert.equal(urls[0], `https://api.github.com/repos/DivineGima/PROB_BOT/commits/${SHA}/pulls`);

    const failing = /** @type {typeof fetch} */ (async () => json({}, 403));
    assert.equal(
      (await verifyMergedPr({ repo: "a/b", sha: SHA, token: "t", fetchImpl: failing })).ok,
      false,
    );
    assert.equal(
      (await verifyMergedPr({ repo: "bad repo", sha: SHA, token: "t", fetchImpl })).ok,
      false,
    );
  });
});

describe("set-webhook", () => {
  const good = {
    workerUrl: "https://prob-bot.example.workers.dev",
    pathSecret: PATH_SECRET,
    headerSecret: HEADER_SECRET,
    botToken: BOT_TOKEN,
  };

  it("builds the registration the architecture requires", () => {
    const { webhookUrl, body } = buildRegistration(good);
    assert.equal(webhookUrl, `https://prob-bot.example.workers.dev/tg/${PATH_SECRET}`);
    assert.deepEqual(body, {
      url: webhookUrl,
      secret_token: HEADER_SECRET,
      allowed_updates: ["message"],
      drop_pending_updates: false,
    });
  });

  it("normalises a trailing path on WORKER_URL and rejects weak secrets, http and junk", () => {
    assert.equal(
      buildRegistration({ ...good, workerUrl: "https://x.example/anything/" }).webhookUrl,
      `https://x.example/tg/${PATH_SECRET}`,
    );
    assert.throws(() => buildRegistration({ ...good, workerUrl: "http://x.example" }), /https/);
    assert.throws(() => buildRegistration({ ...good, workerUrl: "nonsense" }), /valid URL/);
    assert.throws(() => buildRegistration({ ...good, pathSecret: "short" }), /WEBHOOK_PATH_SECRET/);
    assert.throws(
      () => buildRegistration({ ...good, headerSecret: "has spaces in it 0123456789" }),
      /TELEGRAM_WEBHOOK_SECRET/,
    );
    assert.throws(() => buildRegistration({ ...good, botToken: "" }), /TELEGRAM_BOT_TOKEN/);
  });

  it("posts to Telegram and never leaks the token in a failure message", async () => {
    /** @type {{ url: string, body: any }[]} */
    const seen = [];
    const okFetch = /** @type {typeof fetch} */ (
      async (url, init) => {
        seen.push({ url: String(url), body: JSON.parse(String(init?.body)) });
        return json({ ok: true, result: true });
      }
    );
    await setWebhook({ ...good, fetchImpl: okFetch });
    assert.equal(seen[0]?.url, `https://api.telegram.org/bot${BOT_TOKEN}/setWebhook`);
    assert.equal(seen[0]?.body.drop_pending_updates, false);

    const badFetch = /** @type {typeof fetch} */ (
      async () => json({ ok: false, description: "Unauthorized" }, 401)
    );
    await assert.rejects(setWebhook({ ...good, fetchImpl: badFetch }), (error) => {
      assert.ok(error instanceof Error);
      assert.match(error.message, /HTTP 401\): Unauthorized/);
      assert.ok(!error.message.includes(BOT_TOKEN));
      return true;
    });

    const htmlFetch = /** @type {typeof fetch} */ (
      async () => new Response("<html>", { status: 502 })
    );
    await assert.rejects(setWebhook({ ...good, fetchImpl: htmlFetch }), /HTTP 502/);
  });
});

describe("smoke", () => {
  const origin = "https://prob-bot.example.workers.dev";

  /** A pretend deployed Worker that behaves as specified in section 6.2. */
  const goodWorker = /** @type {typeof fetch} */ (
    async (url, init) => {
      const u = new URL(String(url));
      if (u.hostname === "api.telegram.org") {
        return json({ ok: true, result: { url: `${origin}/tg/${PATH_SECRET}` } });
      }
      const header = new Headers(init?.headers).get("x-telegram-bot-api-secret-token");
      if (u.pathname === `/tg/${PATH_SECRET}` && init?.method === "POST") {
        return new Response(null, { status: header === HEADER_SECRET ? 200 : 401 });
      }
      return new Response(null, { status: 404 });
    }
  );

  it("passes against a correctly behaving Worker and a matching webhook registration", async () => {
    const checks = await runSmoke({
      workerUrl: origin,
      pathSecret: PATH_SECRET,
      botToken: BOT_TOKEN,
      fetchImpl: goodWorker,
    });
    assert.equal(checks.length, 6);
    assert.deepEqual(
      checks.filter((c) => !c.ok),
      [],
    );
  });

  it("fails when the Worker answers 404 for everything (secrets missing) or 200 to bad requests", async () => {
    const allNotFound = /** @type {typeof fetch} */ (
      async () => new Response(null, { status: 404 })
    );
    const dead = await runSmoke({
      workerUrl: origin,
      pathSecret: PATH_SECRET,
      fetchImpl: allNotFound,
    });
    assert.equal(dead.find((c) => c.name.includes("401"))?.ok, false);

    const allOk = /** @type {typeof fetch} */ (async () => new Response(null, { status: 200 }));
    const open = await runSmoke({ workerUrl: origin, pathSecret: PATH_SECRET, fetchImpl: allOk });
    assert.equal(
      open.every((c) => c.ok),
      false,
    );
  });

  it("fails when Telegram points elsewhere or reports a delivery error, and survives network errors", async () => {
    const wrongHook = /** @type {typeof fetch} */ (
      async (url, init) =>
        new URL(String(url)).hostname === "api.telegram.org"
          ? json({
              ok: true,
              result: {
                url: "https://other.example/tg/x",
                last_error_message: "Wrong response from the webhook",
              },
            })
          : goodWorker(url, init)
    );
    const checks = await runSmoke({
      workerUrl: origin,
      pathSecret: PATH_SECRET,
      botToken: BOT_TOKEN,
      fetchImpl: wrongHook,
    });
    assert.equal(checks.filter((c) => !c.ok).length, 2);

    const down = /** @type {typeof fetch} */ (
      async () => {
        throw new TypeError("fetch failed");
      }
    );
    const failed = await runSmoke({
      workerUrl: origin,
      pathSecret: PATH_SECRET,
      botToken: BOT_TOKEN,
      fetchImpl: down,
    });
    assert.equal(
      failed.every((c) => !c.ok),
      true,
    );
  });

  it("never puts a secret in a check name or detail", async () => {
    const checks = await runSmoke({
      workerUrl: origin,
      pathSecret: PATH_SECRET,
      botToken: BOT_TOKEN,
      fetchImpl: goodWorker,
    });
    const text = JSON.stringify(checks);
    for (const secret of [PATH_SECRET, HEADER_SECRET, BOT_TOKEN]) assert.ok(!text.includes(secret));
  });
});

describe("cpu-spike driver and local bench plumbing", () => {
  it("sends the synthetic upload n times to the secret spike path with the secret header", async () => {
    /** @type {{ url: string, header: string | null, bytes: number }[]} */
    const calls = [];
    const fetchImpl = /** @type {typeof fetch} */ (
      async (url, init) => {
        calls.push({
          url: String(url),
          header: new Headers(init?.headers).get("x-telegram-bot-api-secret-token"),
          bytes: String(init?.body).length,
        });
        return json({ matches: 60 });
      }
    );
    const result = await driveSpike({
      workerUrl: "https://w.example/ignored",
      pathSecret: PATH_SECRET,
      headerSecret: HEADER_SECRET,
      n: 3,
      matches: 60,
      fetchImpl,
      pauseMs: 0,
    });
    assert.equal(calls.length, 3);
    assert.equal(calls[0]?.url, `https://w.example/spike/${PATH_SECRET}`);
    assert.equal(calls[0]?.header, HEADER_SECRET);
    assert.deepEqual(result.statuses, { 200: 3 });
    assert.ok(result.bodyBytes > 40_000, "a 60-match upload is about 1 KB per match");
  });

  it("measures CPU per invocation and surfaces a non-200 as an error", async () => {
    const worker = { fetch: async () => new Response("{}", { status: 200 }) };
    const { cpuMs } = await benchWorker(worker, { n: 5, matches: 3 });
    assert.equal(cpuMs.length, 5);
    assert.ok(cpuMs.every((v) => v >= 0));

    const broken = { fetch: async () => new Response(null, { status: 401 }) };
    await assert.rejects(benchWorker(broken, { n: 1, matches: 3 }), /HTTP 401/);
  });
});
