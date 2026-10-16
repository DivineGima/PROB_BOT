import { checkSession, routeOf, verifyWebhook } from "./auth";
import { MAX_UPDATE_BODY_BYTES } from "./config/constants";
import type { Env } from "./config/env";
import { ERROR_CODES } from "./config/errors";
import { logRequest } from "./config/log";
import { createRepositories } from "./repo";
import { handleSpike } from "./spike";
import { classifyUpdate } from "./telegram/update";

/**
 * Entry point: routing only. Flow (sections 6.2, 7.8):
 *   path/method/header (auth.verifyWebhook) -> body guard -> allowlist (auth.checkSession)
 *   -> update_id dedupe (repo) -> 200.
 * Stage 1 acknowledges; intake, engine and reply arrive in Stage 5 behind the same 200.
 */

const empty = (status: number): Response => new Response(null, { status });

/** Reads at most `limit` bytes; returns null if the body is larger (never buffers an oversize body). */
async function readCapped(request: Request, limit: number): Promise<string | null> {
  const declared = Number(request.headers.get("content-length") ?? "0");
  if (declared > limit) return null;
  if (!request.body) return "";
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let received = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    received += value.byteLength;
    if (received > limit) {
      await reader.cancel();
      return null;
    }
    chunks.push(value);
  }
  const bytes = new Uint8Array(received);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return new TextDecoder("utf-8", { fatal: true, ignoreBOM: false }).decode(bytes);
}

async function handleTelegramUpdate(
  request: Request,
  env: Env,
  ctx: ExecutionContext,
  requestId: string,
): Promise<Response> {
  let update: unknown;
  try {
    const text = await readCapped(request, MAX_UPDATE_BODY_BYTES);
    if (text === null) {
      logRequest({ request_id: requestId, route: "webhook", outcome: "body_too_large" });
      return empty(200);
    }
    update = JSON.parse(text);
  } catch {
    logRequest({ request_id: requestId, route: "webhook", outcome: "bad_body" });
    return empty(200);
  }

  const repos = createRepositories(env.DB);

  const session = checkSession(update, env);
  if (!session) {
    // S2: no reply, no oracle. One counter event only; nothing about the sender is stored.
    ctx.waitUntil(
      repos.events
        .record({ level: "info", source: "bot", kind: "ignored_update" })
        .catch(() => undefined),
    );
    logRequest({ request_id: requestId, route: "webhook", outcome: "ignored" });
    return empty(200);
  }

  try {
    const firstTime = await repos.updates.markProcessed(session.updateId, classifyUpdate(update));
    logRequest({
      request_id: requestId,
      route: "webhook",
      outcome: firstTime ? "acknowledged" : "replay",
      update_id: session.updateId,
    });
    return empty(200);
  } catch {
    // Not yet acknowledged: a non-200 makes Telegram retry later, which is safe because nothing ran.
    logRequest({
      request_id: requestId,
      route: "webhook",
      outcome: "dedupe_failed",
      update_id: session.updateId,
      error_code: ERROR_CODES.E_INTERNAL,
    });
    return empty(500);
  }
}

export async function handleFetch(
  request: Request,
  env: Env,
  ctx: ExecutionContext,
): Promise<Response> {
  const requestId = crypto.randomUUID();
  const route = routeOf(new URL(request.url).pathname);
  if (route === null || (route === "spike" && env.SPIKE_ENABLED !== "1")) return empty(404);

  const verdict = verifyWebhook(request, env, route);
  if (!verdict.ok) {
    const { status, reason } = verdict.error;
    if (reason === "misconfigured") {
      logRequest({
        request_id: requestId,
        route,
        outcome: "auth_misconfigured",
        error_code: ERROR_CODES.E_AUTH,
      });
    }
    return empty(status);
  }

  if (route === "spike") return handleSpike(request);
  return handleTelegramUpdate(request, env, ctx, requestId);
}

export default {
  fetch: handleFetch,
} satisfies ExportedHandler<Env>;
