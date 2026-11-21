// @ts-check
// Registers the Telegram webhook (architecture section 6.2): secret_token, allowed_updates=["message"],
// drop_pending_updates=false. Run by deploy.yml and by hand after rotating a secret (S12 runbook).
// The bot token and both secrets are never printed.
// [v3, ADR-052] It also registers Telegram's "/" command menu with setMyCommands, scoped to the allowed
// chat (TELEGRAM_CHAT_ID), from packages/contracts/bot_commands.json. The webhook registration is
// fatal; a skipped or failed menu registration is only a warning, so it never blocks a deploy.
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const COMMANDS_FILE = path.join(
  import.meta.dirname,
  "..",
  "packages",
  "contracts",
  "bot_commands.json",
);
const CHAT_ID_PATTERN = /^-?\d{1,18}$/;

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

/**
 * The setMyCommands body: the shared command list, shown only in the allowed chat (S17).
 * @param {{ chatId: string, commands?: Array<{ command: string, description: string }> }} input
 */
export function buildCommandMenu({ chatId, commands }) {
  const trimmed = chatId.trim();
  if (!CHAT_ID_PATTERN.test(trimmed)) throw new Error("TELEGRAM_CHAT_ID is not a chat id");
  const list =
    commands ??
    /** @type {{ commands: Array<{ command: string, description: string }> }} */ (
      JSON.parse(readFileSync(COMMANDS_FILE, "utf8"))
    ).commands;
  return {
    commands: list.map((c) => ({ command: c.command, description: c.description })),
    scope: { type: "chat", chat_id: Number(trimmed) },
  };
}

/**
 * @param {{ botToken: string, chatId: string, fetchImpl?: typeof fetch,
 *           commands?: Array<{ command: string, description: string }> }} input
 */
export async function setCommandMenu(input) {
  const { fetchImpl = fetch, botToken, ...rest } = input;
  const body = buildCommandMenu(rest);
  const response = await fetchImpl(`https://api.telegram.org/bot${botToken}/setMyCommands`, {
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
    throw new Error(
      `setMyCommands failed (HTTP ${response.status}): ${result.description ?? "no description"}`,
    );
  }
}

/**
 * The script: the webhook (fatal), then the menu (a warning when skipped or failed).
 * @param {Record<string, string | undefined>} env
 * @param {typeof fetch} [fetchImpl]
 * @param {{ log: (m: string) => void, warn: (m: string) => void, error: (m: string) => void }} [out]
 * @returns {Promise<number>} the exit code
 */
export async function run(env, fetchImpl = fetch, out = console) {
  const botToken = env.TELEGRAM_BOT_TOKEN ?? "";
  try {
    await setWebhook({
      workerUrl: env.WORKER_URL ?? "",
      pathSecret: env.WEBHOOK_PATH_SECRET ?? "",
      headerSecret: env.TELEGRAM_WEBHOOK_SECRET ?? "",
      botToken,
      fetchImpl,
    });
    out.log("set-webhook: ok");
  } catch (error) {
    out.error(`set-webhook: ${error instanceof Error ? error.message : "failed"}`);
    return 1;
  }
  const chatId = env.TELEGRAM_CHAT_ID ?? "";
  if (chatId.trim() === "") {
    out.warn("set-webhook: command menu skipped (TELEGRAM_CHAT_ID is not set)");
    return 0;
  }
  try {
    await setCommandMenu({ botToken, chatId, fetchImpl });
    out.log("set-webhook: command menu ok");
  } catch (error) {
    out.warn(
      `set-webhook: command menu not registered: ${error instanceof Error ? error.message : "failed"}`,
    );
  }
  return 0;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  process.exitCode = await run(process.env);
}
