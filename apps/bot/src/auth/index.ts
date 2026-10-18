import {
  MAX_SECRET_LENGTH,
  MIN_SECRET_LENGTH,
  SECRET_HEADER,
  SPIKE_PATH_PREFIX,
  WEBHOOK_PATH_PREFIX,
} from "../config/constants";
import type { Env } from "../config/env";
import { ERROR_CODES, err, ok, type Result } from "../config/errors";

/**
 * The ONLY module that reads the webhook path secret, the header secret, the chat id or the
 * user id (architecture section 6.5 and the locked Auth rule). Swapping the scheme touches
 * this file only. Three independent layers, in order (section 7.8):
 *   1. unguessable path  2. secret-token header (constant time)  3. chat-and-user allowlist
 */

export type AuthRoute = "webhook" | "spike";

export interface AuthOk {
  route: AuthRoute;
}

/**
 * `reason` is for server-side logs only and is never sent to the caller:
 *  - `no_match`: wrong path/method (404) or wrong/missing header (401);
 *  - `misconfigured`: a secret is missing or too weak, so the Worker fails closed.
 */
export interface AuthError {
  status: 404 | 401;
  code: typeof ERROR_CODES.E_AUTH | "E_NOT_FOUND";
  reason: "no_match" | "misconfigured";
}

export interface Session {
  updateId: number;
  chatId: number;
  userId: number;
}

const SECRET_PATTERN = /^[A-Za-z0-9_-]+$/;

const PREFIX: Record<AuthRoute, string> = {
  webhook: WEBHOOK_PATH_PREFIX,
  spike: SPIKE_PATH_PREFIX,
};

/** Which auth route a pathname belongs to, judged by prefix only (no secret involved). */
export function routeOf(pathname: string): AuthRoute | null {
  for (const route of Object.keys(PREFIX) as AuthRoute[]) {
    if (pathname.startsWith(PREFIX[route])) return route;
  }
  return null;
}

/**
 * Constant-time string equality: the loop always runs over the longer input, and a length
 * mismatch is folded into the accumulator instead of returning early.
 */
export function constantTimeEqual(a: string, b: string): boolean {
  const encoder = new TextEncoder();
  const left = encoder.encode(a);
  const right = encoder.encode(b);
  const length = Math.max(left.length, right.length);
  let diff = left.length ^ right.length;
  for (let i = 0; i < length; i++) {
    diff |= (left[i] ?? 0) ^ (right[i] ?? 0);
  }
  return diff === 0;
}

function isStrongSecret(value: unknown): value is string {
  return (
    typeof value === "string" &&
    value.length >= MIN_SECRET_LENGTH &&
    value.length <= MAX_SECRET_LENGTH &&
    SECRET_PATTERN.test(value)
  );
}

/**
 * Layers 1 and 2. Wrong method or path -> 404 with no body; missing or wrong header -> 401 with
 * no body. A missing or weak secret fails closed. Both secrets are always compared (no early
 * return between them) so timing does not reveal which layer failed first.
 */
export function verifyWebhook(
  request: Request,
  env: Pick<Env, "WEBHOOK_PATH_SECRET" | "TELEGRAM_WEBHOOK_SECRET">,
  route: AuthRoute = "webhook",
): Result<AuthOk, AuthError> {
  if (!isStrongSecret(env.WEBHOOK_PATH_SECRET) || !isStrongSecret(env.TELEGRAM_WEBHOOK_SECRET)) {
    return err({ status: 404, code: "E_NOT_FOUND", reason: "misconfigured" });
  }

  const pathname = new URL(request.url).pathname;
  const pathMatches = constantTimeEqual(pathname, `${PREFIX[route]}${env.WEBHOOK_PATH_SECRET}`);
  const headerMatches = constantTimeEqual(
    request.headers.get(SECRET_HEADER) ?? "",
    env.TELEGRAM_WEBHOOK_SECRET,
  );

  if (request.method !== "POST" || !pathMatches) {
    return err({ status: 404, code: "E_NOT_FOUND", reason: "no_match" });
  }
  if (!headerMatches) {
    return err({ status: 401, code: ERROR_CODES.E_AUTH, reason: "no_match" });
  }
  return ok({ route });
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function parseAllowedId(raw: unknown): number | null {
  if (typeof raw !== "string" || !/^-?\d{1,18}$/.test(raw.trim())) return null;
  const parsed = Number(raw.trim());
  return Number.isSafeInteger(parsed) ? parsed : null;
}

/**
 * Layer 3. Returns a Session only for a private chat whose chat id AND sender id both equal the
 * configured allowlist; anything else (including a malformed update or a missing allowlist)
 * returns null, so the caller answers 200 with no reply and leaks nothing (S2).
 */
export function checkSession(
  update: unknown,
  env: Pick<Env, "ALLOWED_CHAT_ID" | "ALLOWED_USER_ID">,
): Session | null {
  const allowedChat = parseAllowedId(env.ALLOWED_CHAT_ID);
  const allowedUser = parseAllowedId(env.ALLOWED_USER_ID);
  if (allowedChat === null || allowedUser === null) return null;

  const root = asRecord(update);
  const updateId = root?.update_id;
  if (typeof updateId !== "number" || !Number.isSafeInteger(updateId) || updateId < 0) return null;

  const message = asRecord(root?.message);
  const chat = asRecord(message?.chat);
  const from = asRecord(message?.from);
  if (!chat || !from) return null;

  if (chat.type !== "private") return null;
  if (chat.id !== allowedChat || from.id !== allowedUser) return null;

  return { updateId, chatId: allowedChat, userId: allowedUser };
}

/**
 * The chat the watchdog writes to: the allowlisted chat, read here because only `auth` may read the
 * allowlist. Null when it is missing or malformed (the watchdog then records an event instead).
 */
export function alertChatId(env: Pick<Env, "ALLOWED_CHAT_ID">): number | null {
  return parseAllowedId(env.ALLOWED_CHAT_ID);
}
