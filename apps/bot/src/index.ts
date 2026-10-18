import { checkSession, routeOf, verifyWebhook } from "./auth";
import { MAX_UPDATE_BODY_BYTES } from "./config/constants";
import type { Env } from "./config/env";
import { ERROR_CODES } from "./config/errors";
import { logRequest } from "./config/log";
import { createRepositories } from "./repo";
import { handleSpike } from "./spike";
import { type Sleep, telegramFromEnv } from "./telegram/client";
import { classifyUpdate, extractDocument } from "./telegram/update";
import { handleDocument, sendUsageHint, type UploadOutcome } from "./upload";
import { runWatchdog, type WatchdogOutcome, watchdogDeps } from "./watchdog";

/**
 * Entry point: routing only. Flow (sections 6.2, 7.8):
 *   path/method/header (auth.verifyWebhook) -> body guard -> allowlist (auth.checkSession)
 *   -> update_id dedupe (repo) -> 200, then the upload pipeline (or the usage hint) runs after
 *   the acknowledgement in `ctx.waitUntil` (Stage 5b, ADR-042).
 */

/** What the Worker needs from the outside world; tests inject fakes, production uses the defaults. */
export interface Services {
  fetch: typeof fetch;
  now: () => Date;
  newErrorId: () => string;
  sleep?: Sleep;
}

const defaultServices: Services = {
  fetch: (input, init) => fetch(input, init),
  now: () => new Date(),
  newErrorId: () => crypto.randomUUID().slice(0, 8),
};

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
  services: Services,
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

  const repos = createRepositories(env.DB, services.now);

  const session = checkSession(update, env);
  if (!session) {
    // S2: no reply, no oracle. A counter event at most once per hour, so a stranger messaging the
    // public bot cannot use up D1's daily write quota; nothing about the sender is stored.
    ctx.waitUntil(
      repos.events
        .record({
          level: "info",
          source: "bot",
          kind: "ignored_update",
          dedupeKey: `ignored_update:${new Date().toISOString().slice(0, 13)}`,
        })
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
    if (firstTime) {
      ctx.waitUntil(runPipeline(update, session, repos, env, requestId, services));
    }
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

/** The work behind the acknowledgement: a document runs the upload pipeline, anything else gets the hint. */
async function runPipeline(
  update: unknown,
  session: { updateId: number; chatId: number },
  repos: ReturnType<typeof createRepositories>,
  env: Env,
  requestId: string,
  services: Services,
): Promise<void> {
  const started = Date.now();
  let outcome: UploadOutcome;
  try {
    const deps = {
      repos,
      telegram: telegramFromEnv(env, services.fetch, services.sleep),
      now: services.now,
      newErrorId: services.newErrorId,
    };
    const document = classifyUpdate(update) === "document" ? extractDocument(update) : null;
    outcome = document
      ? await handleDocument(deps, { updateId: session.updateId, chatId: session.chatId, document })
      : await sendUsageHint(deps, session.chatId);
  } catch {
    outcome = { outcome: "pipeline_crashed", errorCode: ERROR_CODES.E_INTERNAL };
  }
  logRequest({
    request_id: requestId,
    route: "webhook",
    outcome: outcome.outcome,
    update_id: session.updateId,
    ...(outcome.errorCode ? { error_code: outcome.errorCode } : {}),
    duration_ms: Date.now() - started,
    ...outcome.counts,
  });
}

export async function handleFetch(
  request: Request,
  env: Env,
  ctx: ExecutionContext,
  services: Services = defaultServices,
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
  return handleTelegramUpdate(request, env, ctx, requestId, services);
}

/** The cron trigger (every six hours): the watchdog. Awaited, so the run is complete and logged. */
export async function handleScheduled(
  env: Env,
  services: Services = defaultServices,
): Promise<WatchdogOutcome> {
  const repos = createRepositories(env.DB, services.now);
  const outcome = await runWatchdog(watchdogDeps(env, repos, services));
  logRequest({
    request_id: crypto.randomUUID(),
    route: "other",
    outcome: "watchdog",
    n_findings: outcome.findings,
    n_sent: outcome.sent,
    n_skipped: outcome.skipped,
    n_failed: outcome.failed,
  });
  return outcome;
}

export default {
  fetch: handleFetch,
  async scheduled(_controller, env, ctx) {
    ctx.waitUntil(handleScheduled(env));
  },
} satisfies ExportedHandler<Env>;
