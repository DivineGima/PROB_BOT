// @ts-check
// Post-deploy smoke (architecture section 9.3): the deployed Worker must reject what it should and the
// webhook must be registered where we expect. Needs no write access and never prints a secret.
import { fileURLToPath } from "node:url";

/**
 * @typedef {{ name: string, ok: boolean, detail: string }} Check
 */

/**
 * @param {{ workerUrl: string, pathSecret: string, botToken?: string, fetchImpl?: typeof fetch }} input
 * @returns {Promise<Check[]>}
 */
export async function runSmoke({ workerUrl, pathSecret, botToken, fetchImpl = fetch }) {
  const origin = new URL(workerUrl).origin;
  /** @type {Check[]} */
  const checks = [];
  /**
   * @param {string} name
   * @param {number} expected
   * @param {string} path
   * @param {RequestInit} init
   */
  const expectStatus = async (name, expected, path, init) => {
    try {
      const response = await fetchImpl(`${origin}${path}`, init);
      checks.push({
        name,
        ok: response.status === expected,
        detail: `HTTP ${response.status}, expected ${expected}`,
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
    "spike path is closed (404) unless deliberately enabled",
    404,
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
      /** @type {{ ok?: boolean, result?: { url?: string, last_error_message?: string, allowed_updates?: string[] } }} */
      const info = await response.json();
      const registered = info.result?.url === `${origin}/tg/${pathSecret}`;
      checks.push({
        name: "Telegram webhook points at this Worker",
        ok: registered,
        detail: registered ? "registered" : "URL differs or is empty",
      });
      const clean = !info.result?.last_error_message;
      checks.push({
        name: "Telegram reports no delivery error",
        ok: clean,
        detail: clean ? "no error" : "Telegram reports a delivery error",
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
