import { describe, expect, it } from "vitest";
import { checkSession, constantTimeEqual, routeOf, verifyWebhook } from "../src/auth";
import { classifyUpdate } from "../src/telegram/update";

const PATH_SECRET = "path-secret-0123456789";
const HEADER_SECRET = "header-secret-0123456789";
const secrets = { WEBHOOK_PATH_SECRET: PATH_SECRET, TELEGRAM_WEBHOOK_SECRET: HEADER_SECRET };

function request(path: string, init: { method?: string; header?: string | null } = {}): Request {
  const headers = new Headers();
  if (init.header !== null) {
    headers.set("X-Telegram-Bot-Api-Secret-Token", init.header ?? HEADER_SECRET);
  }
  return new Request(`https://bot.example${path}`, { method: init.method ?? "POST", headers });
}

describe("constantTimeEqual", () => {
  it("accepts equal strings, including empty and non-ASCII", () => {
    expect(constantTimeEqual("abc", "abc")).toBe(true);
    expect(constantTimeEqual("", "")).toBe(true);
    expect(constantTimeEqual("héllo", "héllo")).toBe(true);
  });

  it("rejects different content, different length, and prefix matches", () => {
    expect(constantTimeEqual("abc", "abd")).toBe(false);
    expect(constantTimeEqual("abc", "abcd")).toBe(false);
    expect(constantTimeEqual("abcd", "abc")).toBe(false);
    expect(constantTimeEqual("", "a")).toBe(false);
  });
});

describe("routeOf", () => {
  it("maps prefixes to routes and everything else to null", () => {
    expect(routeOf("/tg/x")).toBe("webhook");
    expect(routeOf("/spike/x")).toBe("spike");
    expect(routeOf("/")).toBeNull();
    expect(routeOf("/healthz")).toBeNull();
  });
});

describe("verifyWebhook (S1)", () => {
  it("accepts the right path, method and header", () => {
    const result = verifyWebhook(request(`/tg/${PATH_SECRET}`), secrets);
    expect(result).toEqual({ ok: true, value: { route: "webhook" } });
  });

  it("returns 404 for a wrong path", () => {
    const result = verifyWebhook(request("/tg/not-the-secret-0123456789"), secrets);
    expect(result).toMatchObject({ ok: false, error: { status: 404, reason: "no_match" } });
  });

  it("returns 404 for a path with a trailing slash or extra segment", () => {
    for (const path of [`/tg/${PATH_SECRET}/`, `/tg/${PATH_SECRET}/x`, `/tg/${PATH_SECRET}x`]) {
      expect(verifyWebhook(request(path), secrets)).toMatchObject({
        ok: false,
        error: { status: 404 },
      });
    }
  });

  it("returns 404 for a non-POST method even with the right path and header", () => {
    for (const method of ["GET", "PUT", "DELETE"]) {
      expect(verifyWebhook(request(`/tg/${PATH_SECRET}`, { method }), secrets)).toMatchObject({
        ok: false,
        error: { status: 404 },
      });
    }
  });

  it("returns 401 for a missing header", () => {
    const result = verifyWebhook(request(`/tg/${PATH_SECRET}`, { header: null }), secrets);
    expect(result).toMatchObject({ ok: false, error: { status: 401, code: "E_AUTH" } });
  });

  it("returns 401 for a wrong header, including one of the same length and an empty one", () => {
    for (const header of ["x".repeat(HEADER_SECRET.length), "", `${HEADER_SECRET}x`]) {
      expect(verifyWebhook(request(`/tg/${PATH_SECRET}`, { header }), secrets)).toMatchObject({
        ok: false,
        error: { status: 401 },
      });
    }
  });

  it("does not accept the header secret as the path secret or the reverse", () => {
    const swapped = {
      WEBHOOK_PATH_SECRET: HEADER_SECRET,
      TELEGRAM_WEBHOOK_SECRET: PATH_SECRET,
    };
    expect(verifyWebhook(request(`/tg/${PATH_SECRET}`), swapped).ok).toBe(false);
  });

  it("keeps the webhook and spike routes separate", () => {
    expect(verifyWebhook(request(`/spike/${PATH_SECRET}`), secrets).ok).toBe(false);
    expect(verifyWebhook(request(`/spike/${PATH_SECRET}`), secrets, "spike").ok).toBe(true);
    expect(verifyWebhook(request(`/tg/${PATH_SECRET}`), secrets, "spike").ok).toBe(false);
  });

  it("fails closed when a secret is missing, empty, short or has illegal characters", () => {
    const bad = [
      "",
      "short",
      "has space in it 0123456789",
      "path/with/slash/0123456789",
      undefined,
    ];
    for (const value of bad) {
      for (const env of [
        { ...secrets, WEBHOOK_PATH_SECRET: value as string },
        { ...secrets, TELEGRAM_WEBHOOK_SECRET: value as string },
      ]) {
        const result = verifyWebhook(request(`/tg/${PATH_SECRET}`), env);
        expect(result).toMatchObject({
          ok: false,
          error: { status: 404, reason: "misconfigured" },
        });
      }
    }
  });

  it("with an empty path secret, /tg/ with an empty header does NOT authenticate", () => {
    const env = { WEBHOOK_PATH_SECRET: "", TELEGRAM_WEBHOOK_SECRET: "" };
    expect(verifyWebhook(request("/tg/", { header: "" }), env).ok).toBe(false);
  });
});

describe("checkSession (S2)", () => {
  const env = { ALLOWED_CHAT_ID: "1001", ALLOWED_USER_ID: "2002" };
  const update = (overrides: Record<string, unknown> = {}) => ({
    update_id: 55,
    message: {
      message_id: 1,
      chat: { id: 1001, type: "private" },
      from: { id: 2002, is_bot: false },
      text: "hi",
      ...overrides,
    },
  });

  it("returns a session for the allowed private chat and user", () => {
    expect(checkSession(update(), env)).toEqual({ updateId: 55, chatId: 1001, userId: 2002 });
  });

  it("returns null for another chat id or another user id", () => {
    expect(checkSession(update({ chat: { id: 9, type: "private" } }), env)).toBeNull();
    expect(checkSession(update({ from: { id: 9 } }), env)).toBeNull();
  });

  it("returns null for a group chat even when the ids match", () => {
    expect(checkSession(update({ chat: { id: 1001, type: "group" } }), env)).toBeNull();
    expect(checkSession(update({ chat: { id: 1001, type: "supergroup" } }), env)).toBeNull();
    expect(checkSession(update({ chat: { id: 1001, type: "channel" } }), env)).toBeNull();
  });

  it("does not coerce string ids from the update", () => {
    expect(checkSession(update({ chat: { id: "1001", type: "private" } }), env)).toBeNull();
    expect(checkSession(update({ from: { id: "2002" } }), env)).toBeNull();
  });

  it("returns null for malformed updates", () => {
    const malformed: unknown[] = [
      null,
      undefined,
      "x",
      42,
      [],
      {},
      { update_id: 1 },
      { update_id: 1, message: null },
      { update_id: 1, message: { chat: { id: 1001, type: "private" } } },
      { update_id: 1, message: { from: { id: 2002 } } },
      { message: update().message },
      { update_id: "55", message: update().message },
      { update_id: -1, message: update().message },
      { update_id: 1.5, message: update().message },
      { update_id: Number.MAX_SAFE_INTEGER + 2, message: update().message },
      { update_id: 1, edited_message: update().message },
    ];
    for (const value of malformed) expect(checkSession(value, env)).toBeNull();
  });

  it("returns null for everything when the allowlist is missing or malformed", () => {
    const configs = [
      { ALLOWED_CHAT_ID: "", ALLOWED_USER_ID: "2002" },
      { ALLOWED_CHAT_ID: "1001", ALLOWED_USER_ID: "" },
      { ALLOWED_CHAT_ID: "abc", ALLOWED_USER_ID: "2002" },
      { ALLOWED_CHAT_ID: "1001", ALLOWED_USER_ID: "NaN" },
      { ALLOWED_CHAT_ID: "10.5", ALLOWED_USER_ID: "2002" },
      { ALLOWED_CHAT_ID: undefined as unknown as string, ALLOWED_USER_ID: "2002" },
    ];
    for (const config of configs) expect(checkSession(update(), config)).toBeNull();
  });

  it("tolerates surrounding whitespace in the configured ids", () => {
    expect(
      checkSession(update(), { ALLOWED_CHAT_ID: " 1001 ", ALLOWED_USER_ID: "2002\n" }),
    ).not.toBeNull();
  });
});

describe("classifyUpdate", () => {
  it("classifies document, text and other messages", () => {
    expect(classifyUpdate({ message: { document: { file_id: "a" } } })).toBe("document");
    expect(classifyUpdate({ message: { text: "hello" } })).toBe("text");
    expect(classifyUpdate({ message: { text: "/status" } })).toBe("command");
    expect(classifyUpdate({ message: { text: "hi /status" } })).toBe("text");
    expect(classifyUpdate({ message: { photo: [] } })).toBe("other");
    expect(classifyUpdate({})).toBe("other");
    expect(classifyUpdate(null)).toBe("other");
  });
});
