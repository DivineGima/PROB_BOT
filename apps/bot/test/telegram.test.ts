import { describe, expect, it } from "vitest";
import { createTelegramClient, telegramFromEnv } from "../src/telegram/client";
import { classifyUpdate, extractDocument } from "../src/telegram/update";

const TOKEN = "123456:TEST-token-abcdefghijklmnopqrstuvwx";

type Handler = (url: string, init?: RequestInit) => Response | Promise<Response>;

function scripted(handlers: Handler[]) {
  const urls: string[] = [];
  let index = 0;
  const fetchFn = (async (input: RequestInfo | URL, init?: RequestInit) => {
    urls.push(String(input));
    const handler = handlers[Math.min(index++, handlers.length - 1)];
    if (!handler) throw new Error("no handler");
    return handler(String(input), init);
  }) as typeof fetch;
  return { fetchFn, urls };
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

const noSleep = async () => {};

describe("sendMessage", () => {
  it("posts plain text with no parse mode", async () => {
    let seen: Record<string, unknown> = {};
    const { fetchFn } = scripted([
      (_url, init) => {
        seen = JSON.parse(String(init?.body));
        return json({ ok: true, result: {} });
      },
    ]);
    const result = await createTelegramClient(TOKEN, fetchFn, noSleep).send(7, "hello <b>x</b>");
    expect(result.ok).toBe(true);
    expect(seen).toEqual({ chat_id: 7, text: "hello <b>x</b>" });
  });

  it("waits out a short 429 and retries once", async () => {
    const sleeps: number[] = [];
    const { fetchFn, urls } = scripted([
      () => json({ ok: false, parameters: { retry_after: 3 } }, 429),
      () => json({ ok: true, result: {} }),
    ]);
    const client = createTelegramClient(TOKEN, fetchFn, async (ms) => void sleeps.push(ms));
    expect((await client.send(1, "x")).ok).toBe(true);
    expect(sleeps).toEqual([3000]);
    expect(urls).toHaveLength(2);
  });

  it("does not wait out a long 429", async () => {
    const sleeps: number[] = [];
    const { fetchFn, urls } = scripted([
      () => json({ ok: false, parameters: { retry_after: 60 } }, 429),
    ]);
    const result = await createTelegramClient(
      TOKEN,
      fetchFn,
      async (ms) => void sleeps.push(ms),
    ).send(1, "x");
    expect(!result.ok && result.error).toEqual({ kind: "rate_limited", status: 429 });
    expect(sleeps).toEqual([]);
    expect(urls).toHaveLength(1);
  });

  it("gives up after one retry when 429 repeats", async () => {
    const { fetchFn, urls } = scripted([
      () => json({ ok: false, parameters: { retry_after: 1 } }, 429),
    ]);
    const result = await createTelegramClient(TOKEN, fetchFn, noSleep).send(1, "x");
    expect(!result.ok && result.error.kind).toBe("rate_limited");
    expect(urls).toHaveLength(2);
  });

  it("retries a network error and a 5xx once, then fails", async () => {
    const network = scripted([
      () => {
        throw new TypeError("boom");
      },
      () => json({ ok: true, result: {} }),
    ]);
    expect((await createTelegramClient(TOKEN, network.fetchFn, noSleep).send(1, "x")).ok).toBe(
      true,
    );
    const server = scripted([() => json({ ok: false }, 502)]);
    const failed = await createTelegramClient(TOKEN, server.fetchFn, noSleep).send(1, "x");
    expect(!failed.ok && failed.error).toEqual({ kind: "http", status: 502 });
    expect(server.urls).toHaveLength(2);
  });

  it("does not retry a permanent 4xx", async () => {
    const { fetchFn, urls } = scripted([
      () => json({ ok: false, description: "chat not found" }, 400),
    ]);
    const result = await createTelegramClient(TOKEN, fetchFn, noSleep).send(1, "x");
    expect(!result.ok && result.error).toEqual({ kind: "http", status: 400 });
    expect(urls).toHaveLength(1);
  });

  it("treats ok:false in a 200 body as a bad response", async () => {
    const { fetchFn } = scripted([() => json({ ok: false })]);
    const result = await createTelegramClient(TOKEN, fetchFn, noSleep).send(1, "x");
    expect(!result.ok && result.error.kind).toBe("bad_response");
  });

  it("never puts the token in a failure value", async () => {
    const { fetchFn } = scripted([
      () => {
        throw new Error(`failed to reach https://api.telegram.org/bot${TOKEN}/sendMessage`);
      },
    ]);
    const result = await createTelegramClient(TOKEN, fetchFn, noSleep).send(1, "x");
    expect(JSON.stringify(result)).not.toContain(TOKEN);
  });
});

describe("getFile and download", () => {
  it("returns the path and size", async () => {
    const { fetchFn } = scripted([
      () =>
        json({
          ok: true,
          result: { file_id: "f", file_path: "documents/file_1.json", file_size: 120 },
        }),
    ]);
    const result = await createTelegramClient(TOKEN, fetchFn, noSleep).getFile("f");
    expect(result.ok && result.value).toEqual({ filePath: "documents/file_1.json", size: 120 });
  });

  it("rejects a getFile answer without a path", async () => {
    const { fetchFn } = scripted([() => json({ ok: true, result: {} })]);
    const result = await createTelegramClient(TOKEN, fetchFn, noSleep).getFile("f");
    expect(!result.ok && result.error.kind).toBe("bad_response");
  });

  it("downloads bytes from the file endpoint", async () => {
    const { fetchFn, urls } = scripted([() => new Response(new Uint8Array([1, 2, 3]))]);
    const result = await createTelegramClient(TOKEN, fetchFn, noSleep).download(
      "documents/f.json",
      100,
    );
    expect(result.ok && [...result.value]).toEqual([1, 2, 3]);
    expect(urls[0]).toBe(`https://api.telegram.org/file/bot${TOKEN}/documents/f.json`);
  });

  it("refuses a declared size over the cap without reading the body", async () => {
    const { fetchFn } = scripted([
      () => new Response(new Uint8Array(10), { headers: { "content-length": "9999" } }),
    ]);
    const result = await createTelegramClient(TOKEN, fetchFn, noSleep).download("p", 100);
    expect(!result.ok && result.error.kind).toBe("too_large");
  });

  it("stops reading a body that grows past the cap even if it lied about its size", async () => {
    const { fetchFn } = scripted([() => new Response(new Uint8Array(500))]);
    const result = await createTelegramClient(TOKEN, fetchFn, noSleep).download("p", 100);
    expect(!result.ok && result.error.kind).toBe("too_large");
  });

  it("reports an HTTP error on download", async () => {
    const { fetchFn } = scripted([() => new Response("nope", { status: 404 })]);
    const result = await createTelegramClient(TOKEN, fetchFn, noSleep).download("p", 100);
    expect(!result.ok && result.error).toEqual({ kind: "http", status: 404 });
  });
});

describe("telegramFromEnv (the only reader of the token)", () => {
  const { fetchFn } = scripted([() => json({ ok: true, result: {} })]);

  it("builds a client for a well-formed token", () => {
    expect(telegramFromEnv({ TELEGRAM_BOT_TOKEN: TOKEN }, fetchFn)).not.toBeNull();
  });

  it("returns null for a missing, empty or malformed token", () => {
    expect(telegramFromEnv({}, fetchFn)).toBeNull();
    expect(telegramFromEnv({ TELEGRAM_BOT_TOKEN: "   " }, fetchFn)).toBeNull();
    expect(telegramFromEnv({ TELEGRAM_BOT_TOKEN: "not-a-token" }, fetchFn)).toBeNull();
    expect(telegramFromEnv({ TELEGRAM_BOT_TOKEN: "12:short" }, fetchFn)).toBeNull();
  });
});

describe("update helpers", () => {
  it("classifies documents, text and anything else", () => {
    expect(classifyUpdate({ message: { document: { file_id: "a" } } })).toBe("document");
    expect(classifyUpdate({ message: { text: "hi" } })).toBe("text");
    expect(classifyUpdate({ message: { text: "/status" } })).toBe("command");
    expect(classifyUpdate({ message: { text: "hi /status" } })).toBe("text");
    expect(classifyUpdate({ message: { photo: [] } })).toBe("other");
    expect(classifyUpdate(null)).toBe("other");
  });

  it("extracts document fields and caps their length", () => {
    const doc = extractDocument({
      message: {
        document: {
          file_id: "abc",
          file_unique_id: "u",
          file_name: "n".repeat(1000),
          mime_type: "application/json",
          file_size: 42,
        },
      },
    });
    expect(doc?.fileId).toBe("abc");
    expect(doc?.fileName).toHaveLength(256);
    expect(doc?.fileSize).toBe(42);
  });

  it("returns null without a usable document", () => {
    expect(extractDocument({ message: { text: "hi" } })).toBeNull();
    expect(extractDocument({ message: { document: { file_id: "" } } })).toBeNull();
    expect(extractDocument({ message: { document: "x" } })).toBeNull();
    expect(extractDocument(undefined)).toBeNull();
  });
});
