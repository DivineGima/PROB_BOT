// @ts-check
// Registers the Telegram webhook (architecture section 6.2): secret_token, allowed_updates=["message"],
// drop_pending_updates=false. Run by deploy.yml and by hand after rotating a secret (S12 runbook).
// The bot token and both secrets are never printed.
import { fileURLToPath } from "node:url";

const SECRET_PATTERN = /^[A-Za-z0-9_-]{16,256}$/;

/**
 * @param {{ workerUrl: string, pathSecret: string, headerSecret: string, botToken: string }} input
 * @returns {{ webhookUrl: string, body: Record<string, unknown> }}
 */
export function buildRegistration({ workerUrl, pathSecret, headerSecret, botToken }) {
  if (!botToken) throw new Error("TELEGRAM_BOT_TOKEN is required");
  if (!SECRET_PATTERN.test(pathSecret))
    throw new Error("WEBHOOK_PATH_SECRET must be 16-256 chars of A-Za-z0-9_-");
  if (!SECRET_PATTERN.test(headerSecret))
    throw new Error("TELEGRAM_WEBHOOK_SECRET must be 16-256 chars of A-Za-z0-9_-");
  let base;
  try {
    base = new URL(workerUrl);
  } catch {
    throw new Error("WORKER_URL is not a valid URL");
  }
  if (base.protocol !== "https:") throw new Error("WORKER_URL must be https");
  const webhookUrl = `${base.origin}/tg/${pathSecret}`;
  return {
    webhookUrl,
    body: {
      url: webhookUrl,
      secret_token: headerSecret,
      allowed_updates: ["message"],
      drop_pending_updates: false,
    },
  };
}

/**
 * @param {Parameters<typeof buildRegistration>[0] & { fetchImpl?: typeof fetch }} input
 */
export async function setWebhook(input) {
  const { fetchImpl = fetch, ...rest } = input;
  const { body } = buildRegistration(rest);
  const response = await fetchImpl(`https://api.telegram.org/bot${rest.botToken}/setWebhook`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  /** @type {{ ok?: boolean, description?: string }} */
  let result = {};
  try {
    result = await response.json();
  } catch {
    // fall through with an empty result
  }
  if (!response.ok || result.ok !== true) {
    // The description comes from Telegram and never contains our token.
    throw new Error(
      `setWebhook failed (HTTP ${response.status}): ${result.description ?? "no description"}`,
    );
  }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const env = process.env;
  try {
    await setWebhook({
      workerUrl: env.WORKER_URL ?? "",
      pathSecret: env.WEBHOOK_PATH_SECRET ?? "",
      headerSecret: env.TELEGRAM_WEBHOOK_SECRET ?? "",
      botToken: env.TELEGRAM_BOT_TOKEN ?? "",
    });
    console.log("set-webhook: ok");
  } catch (error) {
    console.error(`set-webhook: ${error instanceof Error ? error.message : "failed"}`);
    process.exitCode = 1;
  }
}
