import { createExecutionContext, waitOnExecutionContext } from "cloudflare:test";
import { env } from "cloudflare:workers";
import { beforeEach, describe, expect, it } from "vitest";
import type { Env } from "../src/config/env";
import { handleFetch, type Services } from "../src/index";
import {
  CHAT_ID,
  count,
  documentUpdate,
  type FakeTelegram,
  fakeTelegram,
  RUN_ID,
  resetWorld,
  seedEvent,
  seedForecast,
  seedJob,
  seedModelParams,
  seedPrediction,
  seedReference,
  seedRun,
  seedScheduledMatch,
  seedUpload,
  teamName,
  textUpdate,
} from "./helpers";

/**
 * The commands through the real webhook entry (architecture 3, sections 6.2, 6.3, 6.10, 7.12 and
 * invariant 9; essentials 3 step 7): auth matrix, replay, read-only proof, subrequest budget.
 */

const NOW = new Date("2026-10-17T06:00:00Z");
const PATH = `/tg/${env.WEBHOOK_PATH_SECRET}`;

/** The tables a command must never change (invariant 9). */
const PROTECTED = [
  "predictions",
  "omissions",
  "uploads",
  "fixture_forecasts",
  "model_runs",
  "active_run",
  "team_form",
  "calibration_snapshots",
  "model_params",
  "matches",
  "teams",
  "team_aliases",
  "job_runs",
];

/** A D1 binding that counts the calls a request makes (each is a subrequest). */
function countingDb(real: D1Database): { db: D1Database; calls: () => number } {
  let calls = 0;
  const realOf = new WeakMap<object, D1PreparedStatement>();
  const wrap = (stmt: D1PreparedStatement): D1PreparedStatement => {
    const proxy = new Proxy(stmt, {
      get(target, prop) {
        if (prop === "bind") return (...args: unknown[]) => wrap(target.bind(...args));
        if (prop === "first" || prop === "all" || prop === "run" || prop === "raw") {
          return (...args: unknown[]) => {
            calls++;
            const fn = Reflect.get(target, prop) as (...a: unknown[]) => unknown;
            return fn.apply(target, args);
          };
        }
        const value = Reflect.get(target, prop);
        return typeof value === "function" ? value.bind(target) : value;
      },
    });
    realOf.set(proxy, stmt);
    return proxy;
  };
  const db = new Proxy(real, {
    get(target, prop) {
      if (prop === "prepare") return (sql: string) => wrap(target.prepare(sql));
      if (prop === "batch") {
        return (statements: D1PreparedStatement[]) => {
          calls++;
          return target.batch(statements.map((s) => realOf.get(s) ?? s));
        };
      }
      const value = Reflect.get(target, prop);
      return typeof value === "function" ? value.bind(target) : value;
    },
  });
  return { db, calls: () => calls };
}

async function deliver(
  update: unknown,
  tg: FakeTelegram,
  db: D1Database = env.DB,
): Promise<Response> {
  const services: Services = {
    fetch: tg.fetch,
    now: () => NOW,
    newErrorId: () => "ERR12345",
    sleep: async () => undefined,
  };
  const ctx = createExecutionContext();
  const request = new Request(`https://bot.example${PATH}`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "X-Telegram-Bot-Api-Secret-Token": env.TELEGRAM_WEBHOOK_SECRET,
    },
    body: JSON.stringify(update),
  });
  const response = await handleFetch(request, { ...env, DB: db } as Env, ctx, services);
  await waitOnExecutionContext(ctx);
  return response;
}

async function tableState(): Promise<string> {
  const parts: string[] = [];
  for (const table of PROTECTED) {
    const { results } = await env.DB.prepare(`SELECT * FROM ${table} ORDER BY 1`).all();
    parts.push(`${table}:${JSON.stringify(results)}`);
  }
  return parts.join("\n");
}

/** A small, complete world: every command has something to read. */
async function seedWorld(): Promise<void> {
  await seedRun();
  for (const m of ["dc", "pi", "bp"]) await seedModelParams(m, "ok");
  await seedJob("fit", "ok", "2026-10-17T01:20:00Z", "2026-10-17T01:25:00Z");
  await seedScheduledMatch("2026-10-17", 1, 2);
  await seedForecast({ home: 1, away: 2, pHome: 0.61 });
  await seedForecast({ home: 3, away: 4, verdict: "DRIFT" });
  const upload = await seedUpload(500, { run_date_utc: "2026-10-17", n_published: 1 });
  await seedPrediction({ home: 1, away: 2, uploadId: upload });
  await seedPrediction({
    home: 5,
    away: 6,
    uploadId: upload,
    date: "2026-10-16",
    status: "scored",
  });
  await env.DB.prepare(
    `INSERT INTO calibration_snapshots (created_at, window_from, window_to, n_scored, metrics_json)
     VALUES ('2026-10-12T01:40:00Z', '2026-10-01', '2026-10-11', 1, '{"n_scored": 1, "target": 300}')`,
  ).run();
  await env.DB.prepare(
    `INSERT INTO team_form (run_id, team_id, n_training, n_season, season_gf, season_ga, l10_n,
       l10_gf, l10_ga, latest_match_date) VALUES (?1, 1, 50, 9, 1.5, 1.1, 9, 1.4, 1.2, '2026-10-12')`,
  )
    .bind(RUN_ID)
    .run();
  await seedEvent("2026-10-17T01:00:00Z", "unmapped_team");
}

const COMMANDS = [
  "/help",
  "/start",
  "/status",
  "/fixtures",
  "/fixtures tomorrow",
  "/logged",
  "/logged yesterday",
  "/results",
  "/results 3",
  "/pending",
  "/report",
  "/last",
  `/team ${teamName(1)}`,
  "/alerts",
  "/unknown",
  "/fixtures never",
];

beforeEach(async () => {
  await resetWorld();
  await seedReference();
  await seedWorld();
});

describe("every command through the webhook", () => {
  it("answers, records the update as a command, and changes nothing else (invariant 9)", async () => {
    let updateId = 1000;
    for (const text of COMMANDS) {
      const before = await tableState();
      const eventsBefore = await count("events");
      const tg = fakeTelegram();
      const response = await deliver(textUpdate(++updateId, text), tg);
      expect(response.status, text).toBe(200);
      expect(tg.sent.length, text).toBeGreaterThan(0);
      expect(
        tg.sent.every((m) => m.chatId === CHAT_ID),
        text,
      ).toBe(true);
      expect(
        tg.calls.every((c) => c === "sendMessage"),
        text,
      ).toBe(true);
      expect(await tableState(), text).toBe(before);
      expect(await count("events"), text).toBe(eventsBefore);
      const row = await env.DB.prepare("SELECT kind FROM processed_updates WHERE update_id = ?1")
        .bind(updateId)
        .first<{ kind: string }>();
      expect(row?.kind, text).toBe("command");
    }
  });

  it("never shows a probability in /fixtures, also through the whole stack", async () => {
    const tg = fakeTelegram();
    await deliver(textUpdate(1, "/fixtures"), tg);
    const text = tg.sent.map((m) => m.text).join("\n");
    expect(text).toContain(`${teamName(1)} vs ${teamName(2)}`);
    expect(text).toContain("DRIFT");
    expect(text).not.toMatch(/%|\b0\.\d/);
  });

  it("stays within the subrequest budget (D1 calls plus Telegram calls)", async () => {
    let updateId = 2000;
    for (const text of COMMANDS) {
      const counter = countingDb(env.DB);
      const tg = fakeTelegram();
      await deliver(textUpdate(++updateId, text), tg, counter.db);
      // One D1 call is the update dedupe; /status adds the watchdog's three reads to its batch.
      const d1 = counter.calls() - 1;
      expect(counter.calls(), text).toBeGreaterThanOrEqual(1);
      expect(d1, text).toBeLessThanOrEqual(text === "/status" ? 4 : 2);
      expect(tg.calls.length, text).toBeLessThanOrEqual(5);
      expect(counter.calls() + tg.calls.length, text).toBeLessThanOrEqual(10);
    }
  });
});

describe("auth matrix and replays (S2, S3, S16)", () => {
  const variant = (mutate: (m: Record<string, Record<string, unknown>>) => void) => {
    const update = textUpdate(3000, "/status") as {
      message: Record<string, Record<string, unknown>>;
    };
    mutate(update.message);
    return update;
  };

  it("ignores a command from another chat, another user, or a group: no reply, no read", async () => {
    for (const update of [
      variant((m) => {
        if (m.chat) m.chat.id = 777;
      }),
      variant((m) => {
        if (m.from) m.from.id = 778;
      }),
      variant((m) => {
        if (m.chat) m.chat.type = "group";
      }),
    ]) {
      const tg = fakeTelegram();
      const counter = countingDb(env.DB);
      const response = await deliver(update, tg, counter.db);
      expect(response.status).toBe(200);
      expect(tg.calls).toEqual([]);
      expect(await count("processed_updates")).toBe(0);
      expect(counter.calls()).toBeLessThanOrEqual(1); // the hourly counter event only
    }
    expect(await count("events", "kind = 'ignored_update'")).toBe(1);
  });

  it("answers a replayed command update only once", async () => {
    const tg = fakeTelegram();
    await deliver(textUpdate(4000, "/help"), tg);
    await deliver(textUpdate(4000, "/help"), tg);
    expect(tg.sent).toHaveLength(1);
  });
});

describe("the other paths are unchanged", () => {
  it("still answers plain text with the usage hint, now pointing to /help", async () => {
    const tg = fakeTelegram();
    await deliver(textUpdate(5000, "run today"), tg);
    expect(tg.sent.map((m) => m.text)).toEqual([
      "Upload the screener .json file as a document.\nSend /help to see the commands.",
    ]);
    const row = await env.DB.prepare(
      "SELECT kind FROM processed_updates WHERE update_id = 5000",
    ).first();
    expect(row).toEqual({ kind: "text" });
  });

  it("treats a document whose caption starts with / as an upload, not a command", async () => {
    const update = documentUpdate(5001) as { message: Record<string, unknown> };
    update.message.caption = "/status";
    const tg = fakeTelegram(); // no file registered: the upload pipeline asks Telegram for it
    await deliver(update, tg);
    expect(tg.calls[0]).toBe("getFile");
    expect(tg.sent.map((m) => m.text)).toEqual(["Could not download the file. Please resend."]);
  });

  it("keeps the same numbers in /logged as the stored prediction", async () => {
    const tg = fakeTelegram();
    await deliver(textUpdate(5002, "/logged"), tg);
    const stored = await env.DB.prepare(
      "SELECT p_home FROM predictions WHERE match_date = '2026-10-17'",
    ).first<{ p_home: number }>();
    expect(tg.sent[0]?.text).toContain(`${Math.floor((stored?.p_home ?? 0) * 100 + 0.5)}% 🏠`);
  });
});

describe("failures", () => {
  it("answers E_INTERNAL with an id when D1 fails during a command, and writes nothing else", async () => {
    const broken = new Proxy(env.DB, {
      get(target, prop) {
        if (prop === "batch") return () => Promise.reject(new Error("D1 unavailable"));
        const value = Reflect.get(target, prop);
        return typeof value === "function" ? value.bind(target) : value;
      },
    });
    const before = await tableState();
    const tg = fakeTelegram();
    await deliver(textUpdate(6000, "/fixtures"), tg, broken);
    expect(tg.sent.map((m) => m.text)).toEqual(["Internal error, id=ERR12345"]);
    expect(await count("events", "kind = 'command_failed'")).toBe(1);
    expect(await tableState()).toBe(before);
  });

  it("waits out a 429 and still answers", async () => {
    const tg = fakeTelegram({ rateLimitOnce: 1 });
    await deliver(textUpdate(6001, "/help"), tg);
    expect(tg.sent).toHaveLength(1);
  });
});
