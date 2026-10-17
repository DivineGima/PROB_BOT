import { MAX_RETRY_AFTER_SECONDS, TELEGRAM_API_BASE } from "../config/constants";
import { err, ok, type Result } from "../config/errors";

/**
 * Telegram Bot API over plain `fetch` (ADR-043: no grammY). Four calls only: `getFile`, the file
 * download, `sendMessage` (plain text, no parse mode, so nothing can fail on escaping) and nothing else.
 *
 * The bot token is part of every URL, so failures carry only a kind and an HTTP status: never a URL,
 * a body or the token itself. 429 is honoured (`retry_after` up to MAX_RETRY_AFTER_SECONDS, then one
 * retry); network errors and 5xx are retried once; other 4xx are permanent.
 */

export type TelegramFailureKind =
  | "network"
  | "http"
  | "rate_limited"
  | "too_large"
  | "bad_response";

export interface TelegramFailure {
  kind: TelegramFailureKind;
  status?: number;
}

export interface TelegramClient {
  getFile(
    fileId: string,
  ): Promise<Result<{ filePath: string; size: number | null }, TelegramFailure>>;
  download(filePath: string, maxBytes: number): Promise<Result<Uint8Array, TelegramFailure>>;
  send(chatId: number, text: string): Promise<Result<true, TelegramFailure>>;
}

export type Sleep = (ms: number) => Promise<void>;
const defaultSleep: Sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const failure = (kind: TelegramFailureKind, status?: number): Result<never, TelegramFailure> =>
  err(status === undefined ? { kind } : { kind, status });

interface Reply {
  status: number;
  response: Response;
}

export function createTelegramClient(
  token: string,
  fetchFn: typeof fetch,
  sleep: Sleep = defaultSleep,
): TelegramClient {
  /** One request with the retry policy above. */
  async function request(url: string, init: RequestInit): Promise<Result<Reply, TelegramFailure>> {
    let last: Result<never, TelegramFailure> = failure("network");
    for (let attempt = 0; attempt < 2; attempt++) {
      let response: Response;
      try {
        response = await fetchFn(url, init);
      } catch {
        last = failure("network");
        continue;
      }
      if (response.status === 429) {
        const wait = await retryAfterSeconds(response);
        if (wait === null || wait > MAX_RETRY_AFTER_SECONDS) return failure("rate_limited", 429);
        last = failure("rate_limited", 429);
        await sleep(wait * 1000);
        continue;
      }
      if (response.status >= 500) {
        last = failure("http", response.status);
        continue;
      }
      return ok({ status: response.status, response });
    }
    return last;
  }

  async function call(method: string, body: Record<string, unknown>) {
    const reply = await request(`${TELEGRAM_API_BASE}/bot${token}/${method}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!reply.ok) return reply;
    if (reply.value.status >= 400) return failure("http", reply.value.status);
    try {
      const json = (await reply.value.response.json()) as { ok?: unknown; result?: unknown };
      if (json.ok !== true) return failure("bad_response", reply.value.status);
      return ok(json.result);
    } catch {
      return failure("bad_response", reply.value.status);
    }
  }

  return {
    async getFile(fileId) {
      const result = await call("getFile", { file_id: fileId });
      if (!result.ok) return result;
      const file = result.value as { file_path?: unknown; file_size?: unknown } | null;
      if (!file || typeof file.file_path !== "string" || file.file_path.length === 0) {
        return failure("bad_response");
      }
      return ok({
        filePath: file.file_path,
        size: typeof file.file_size === "number" ? file.file_size : null,
      });
    },

    async download(filePath, maxBytes) {
      const reply = await request(`${TELEGRAM_API_BASE}/file/bot${token}/${filePath}`, {
        method: "GET",
      });
      if (!reply.ok) return reply;
      const { response, status } = reply.value;
      if (status >= 400) return failure("http", status);
      const declared = Number(response.headers.get("content-length") ?? "0");
      if (declared > maxBytes) {
        await response.body?.cancel();
        return failure("too_large", status);
      }
      if (!response.body) return ok(new Uint8Array());
      // Never buffer more than the cap, whatever the server declared.
      const reader = response.body.getReader();
      const chunks: Uint8Array[] = [];
      let received = 0;
      try {
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          received += value.byteLength;
          if (received > maxBytes) {
            await reader.cancel();
            return failure("too_large", status);
          }
          chunks.push(value);
        }
      } catch {
        return failure("network");
      }
      const bytes = new Uint8Array(received);
      let offset = 0;
      for (const chunk of chunks) {
        bytes.set(chunk, offset);
        offset += chunk.byteLength;
      }
      return ok(bytes);
    },

    async send(chatId, text) {
      const result = await call("sendMessage", { chat_id: chatId, text });
      return result.ok ? ok(true as const) : result;
    },
  };
}

async function retryAfterSeconds(response: Response): Promise<number | null> {
  try {
    const json = (await response.json()) as { parameters?: { retry_after?: unknown } };
    const value = json.parameters?.retry_after;
    return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : null;
  } catch {
    return null;
  }
}

/** The ONLY place the bot token is read. No token means no client: the caller records an event. */
export function telegramFromEnv(
  env: { TELEGRAM_BOT_TOKEN?: string },
  fetchFn: typeof fetch,
  sleep?: Sleep,
): TelegramClient | null {
  const token = env.TELEGRAM_BOT_TOKEN?.trim();
  if (!token || !/^[0-9]+:[A-Za-z0-9_-]{20,}$/.test(token)) return null;
  return createTelegramClient(token, fetchFn, sleep);
}
