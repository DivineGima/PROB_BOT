import { createExecutionContext, waitOnExecutionContext } from "cloudflare:test";
import { env, exports } from "cloudflare:workers";
import { beforeEach, describe, expect, it } from "vitest";
import type { Env } from "../src/config/env";
import worker, { handleFetch } from "../src/index";

const PATH = `/tg/${env.WEBHOOK_PATH_SECRET}`;
const HEADER = env.TELEGRAM_WEBHOOK_SECRET;

const allowedUpdate = (updateId: number, message: Record<string, unknown> = { text: "hi" }) => ({
  update_id: updateId,
  message: {
    message_id: 1,
    chat: { id: Number(env.ALLOWED_CHAT_ID), type: "private" },
    from: { id: Number(env.ALLOWED_USER_ID), is_bot: false },
    ...message,
  },
});

function post(body: BodyInit | null, init: { path?: string; header?: string | null } = {}) {
  const headers = new Headers({ "content-type": "application/json" });
  if (init.header !== null) headers.set("X-Telegram-Bot-Api-Secret-Token", init.header ?? HEADER);
  return new Request(`https://bot.example${init.path ?? PATH}`, { method: "POST", headers, body });
}

async function call(request: Request, testEnv: Env = env) {
  const ctx = createExecutionContext();
  const response = await handleFetch(request, testEnv, ctx);
  await waitOnExecutionContext(ctx);
  return response;
}

async function count(table: string, where = "1=1"): Promise<number> {
  const row = await env.DB.prepare(`SELECT COUNT(*) AS n FROM ${table} WHERE ${where}`).first<{
    n: number;
  }>();
  return row?.n ?? -1;
}

beforeEach(async () => {
  await env.DB.batch([
    env.DB.prepare("DELETE FROM processed_updates"),
    env.DB.prepare("DELETE FROM events"),
  ]);
});

describe("webhook routing and auth (S1)", () => {
  it("answers 404 with no body for unknown paths and for a wrong path secret", async () => {
    for (const path of ["/", "/healthz", "/tg/", "/tg/wrong-secret-0123456789", "/other"]) {
      const response = await call(post(JSON.stringify(allowedUpdate(1)), { path }));
      expect(response.status).toBe(404);
      expect(await response.text()).toBe("");
    }
    expect(await count("processed_updates")).toBe(0);
  });

  it("answers 404 for GET on the right path", async () => {
    const response = await call(new Request(`https://bot.example${PATH}`, { method: "GET" }));
    expect(response.status).toBe(404);
  });

  it("answers 401 with no body for a missing or wrong header and does no work", async () => {
    for (const header of [null, "wrong-header-0123456789", ""]) {
      const response = await call(post(JSON.stringify(allowedUpdate(2)), { header }));
      expect(response.status).toBe(401);
      expect(await response.text()).toBe("");
    }
    expect(await count("processed_updates")).toBe(0);
    expect(await count("events")).toBe(0);
  });

  it("fails closed (404) when the Worker secrets are not configured", async () => {
    const broken = { ...env, WEBHOOK_PATH_SECRET: "", TELEGRAM_WEBHOOK_SECRET: "" } as Env;
    const response = await call(post(JSON.stringify(allowedUpdate(3)), { path: "/tg/" }), broken);
    expect(response.status).toBe(404);
  });
});

describe("allowlist and dedupe (S2, S3)", () => {
  it("acknowledges an allowed text message and records it once", async () => {
    const response = await call(post(JSON.stringify(allowedUpdate(10))));
    expect(response.status).toBe(200);
    const row = await env.DB.prepare(
      "SELECT kind, outcome FROM processed_updates WHERE update_id = 10",
    ).first();
    expect(row).toEqual({ kind: "text", outcome: "received" });
  });

  it("records the kind for a document upload", async () => {
    await call(
      post(JSON.stringify(allowedUpdate(11, { document: { file_id: "f", file_name: "a.json" } }))),
    );
    const row = await env.DB.prepare(
      "SELECT kind FROM processed_updates WHERE update_id = 11",
    ).first();
    expect(row).toEqual({ kind: "document" });
  });

  it("answers a replay with 200 and does not create a second row (S3)", async () => {
    const first = await call(post(JSON.stringify(allowedUpdate(12))));
    const second = await call(post(JSON.stringify(allowedUpdate(12))));
    expect([first.status, second.status]).toEqual([200, 200]);
    expect(await count("processed_updates", "update_id = 12")).toBe(1);
  });

  it("handles two concurrent identical updates as one first-time and one replay", async () => {
    const responses = await Promise.all([
      call(post(JSON.stringify(allowedUpdate(13)))),
      call(post(JSON.stringify(allowedUpdate(13)))),
    ]);
    expect(responses.map((r) => r.status)).toEqual([200, 200]);
    expect(await count("processed_updates", "update_id = 13")).toBe(1);
  });

  it("ignores other chats, other users and groups: 200, no reply body, at most one counter event per hour, no dedupe row", async () => {
    const others = [
      {
        ...allowedUpdate(20),
        message: { ...allowedUpdate(20).message, chat: { id: 5, type: "private" } },
      },
      { ...allowedUpdate(21), message: { ...allowedUpdate(21).message, from: { id: 5 } } },
      {
        ...allowedUpdate(22),
        message: {
          ...allowedUpdate(22).message,
          chat: { id: Number(env.ALLOWED_CHAT_ID), type: "group" },
        },
      },
    ];
    for (const update of others) {
      const response = await call(post(JSON.stringify(update)));
      expect(response.status).toBe(200);
      expect(await response.text()).toBe("");
    }
    expect(await count("processed_updates")).toBe(0);
    // Three ignored messages in one hour share a dedupe key (two only if the hour rolls over mid-test).
    const ignored = await count("events", "kind = 'ignored_update'");
    expect(ignored).toBeGreaterThanOrEqual(1);
    expect(ignored).toBeLessThanOrEqual(2);
    const detail = await env.DB.prepare("SELECT detail_json FROM events LIMIT 1").first();
    expect(detail).toEqual({ detail_json: null });
  });
});

describe("hostile or broken bodies from an authenticated caller", () => {
  it("returns 200 and records nothing for non-JSON, empty, invalid UTF-8 and oversize bodies", async () => {
    const bodies: BodyInit[] = [
      "not json",
      "",
      new Uint8Array([0xff, 0xfe, 0xfd]),
      `{"update_id": 30, "pad": "${"x".repeat(70 * 1024)}"}`,
    ];
    for (const body of bodies) {
      const response = await call(post(body));
      expect(response.status).toBe(200);
    }
    expect(await count("processed_updates")).toBe(0);
  });

  it("ignores JSON that is not an update object", async () => {
    for (const body of ["[]", "null", "42", '"s"', "{}"]) {
      expect((await call(post(body))).status).toBe(200);
    }
    expect(await count("processed_updates")).toBe(0);
  });
});

describe("D1 failure before acknowledgement", () => {
  it("answers 500 so Telegram retries, and does not claim success", async () => {
    const failing = {
      ...env,
      DB: {
        prepare: () => {
          throw new Error("D1 unavailable");
        },
      },
    } as unknown as Env;
    const response = await call(post(JSON.stringify(allowedUpdate(40))), failing);
    expect(response.status).toBe(500);
    expect(await count("processed_updates", "update_id = 40")).toBe(0);
  });
});

describe("spike route gating", () => {
  it("is 404 when SPIKE_ENABLED is not 1, even with the right secrets", async () => {
    const off = { ...env, SPIKE_ENABLED: "0" } as Env;
    const response = await call(post("{}", { path: `/spike/${env.WEBHOOK_PATH_SECRET}` }), off);
    expect(response.status).toBe(404);
  });
});

describe("default export", () => {
  it("serves requests through the Worker entry point", async () => {
    expect(typeof worker.fetch).toBe("function");
    const entry = exports as unknown as { default: { fetch(url: string): Promise<Response> } };
    const response = await entry.default.fetch("https://bot.example/nothing");
    expect(response.status).toBe(404);
  });
});
