// @ts-check
// Post-deploy smoke (architecture section 9.3): the deployed Worker must reject what it should and the
// webhook must be registered where we expect. Needs no write access and never prints a secret.
import { fileURLToPath } from "node:url";

/**
 * @typedef {{ name: string, ok: boolean, detail: string }} Check
 */

/**
 * @param {{ workerUrl: string, pathSecret: string, botToken?: string, fetchImpl?: typeof fetch, now?: () => number }} input
 * @returns {Promise<Check[]>}
 */
export async function runSmoke({
  workerUrl,
  pathSecret,
  botToken,
  fetchImpl = fetch,
  now = Date.now,
}) {
  const origin = new URL(workerUrl).origin;
  /** @type {Check[]} */
  const checks = [];
  /**
   * @param {string} name
   * @param {number | number[]} expected one accepted status, or several
   * @param {string} path
   * @param {RequestInit} init
   */
  const expectStatus = async (name, expected, path, init) => {
    const accepted = Array.isArray(expected) ? expected : [expected];
    try {
      const response = await fetchImpl(`${origin}${path}`, init);
      checks.push({
        name,
        ok: accepted.includes(response.status),
        detail: `HTTP ${response.status}, expected ${accepted.join(" or ")}`,
      });
    } catch (error) {
      checks.push({
        name,
        ok: false,
        detail: `request failed: ${error instanceof Error ? error.name : "error"}`,
      });
    }
  };

  await expectStatus("wrong header on the real path is 401", 401, `/tg/${pathSecret}`, {
    method: "POST",
    headers: {
      "x-telegram-bot-api-secret-token": "definitely-not-the-secret",
      "content-type": "application/json",
    },
    body: "{}",
  });
  await expectStatus("wrong path is 404", 404, "/tg/not-a-real-secret-0000000000", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: "{}",
  });
  await expectStatus("GET on the root is 404 (worker is up)", 404, "/", { method: "GET" });
  await expectStatus(
    // 404 while SPIKE_ENABLED=0 (route closed); 401 while it is deliberately on (route open but the
    // header check still rejects the caller). Either way an unauthenticated caller gets nothing.
    "spike path rejects unauthenticated callers (404 off, 401 on)",
    [404, 401],
    `/spike/${pathSecret}`,
    {
      method: "POST",
      headers: { "x-telegram-bot-api-secret-token": "definitely-not-the-secret" },
      body: "{}",
    },
  );

  if (botToken) {
    try {
      const response = await fetchImpl(`https://api.telegram.org/bot${botToken}/getWebhookInfo`);
      /** @type {{ ok?: boolean, result?: { url?: string, last_error_message?: string, last_error_date?: number, allowed_updates?: string[] } }} */
      const info = await response.json();
      const registered = info.result?.url === `${origin}/tg/${pathSecret}`;
      checks.push({
        name: "Telegram webhook points at this Worker",
        ok: registered,
        detail: registered ? "registered" : "URL differs or is empty",
      });
      // Telegram keeps reporting the last delivery error until a later delivery succeeds, so an old
      // error (for example from an earlier outage) must not fail a healthy deploy. Only an error from
      // the last 15 minutes, or one without a date, counts.
      const errorDate = info.result?.last_error_date;
      const recent = typeof errorDate !== "number" || now() - errorDate * 1000 < 15 * 60 * 1000;
      const clean = !info.result?.last_error_message || !recent;
      checks.push({
        name: "Telegram reports no delivery error",
        ok: clean,
        detail: clean
          ? info.result?.last_error_message
            ? "only an old delivery error is on record"
            : "no error"
          : "Telegram reports a delivery error",
      });
    } catch {
      checks.push({ name: "Telegram webhook info readable", ok: false, detail: "request failed" });
    }
  }
  return checks;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const env = process.env;
  const checks = await runSmoke({
    workerUrl: env.WORKER_URL ?? "",
    pathSecret: env.WEBHOOK_PATH_SECRET ?? "",
    ...(env.TELEGRAM_BOT_TOKEN ? { botToken: env.TELEGRAM_BOT_TOKEN } : {}),
  });
  for (const c of checks) console.log(`${c.ok ? "PASS" : "FAIL"}  ${c.name} (${c.detail})`);
  process.exitCode = checks.every((c) => c.ok) ? 0 : 1;
}
