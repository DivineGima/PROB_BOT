import { env } from "cloudflare:workers";
import { beforeEach, describe, expect, it } from "vitest";
import { handleScheduled } from "../src";
import { createRepositories, type Repositories } from "../src/repo";
import { createTelegramClient } from "../src/telegram/client";
import { collectFindings, runWatchdog, type WatchdogDeps } from "../src/watchdog";
import {
  CHAT_ID,
  count,
  fakeTelegram,
  resetWorld,
  seedForecast,
  seedReference,
  seedRun,
  TOKEN,
} from "./helpers";

/** The watchdog (architecture sections 9.2 and 10, ADR-015, ADR-029): each question, once a day. */

const NOW = new Date("2026-10-18T02:00:00Z");
const TODAY = "2026-10-18";
const TOMORROW = "2026-10-19";
const FRESH = "2026-10-18T01:30:00Z";

const repos = (): Repositories => createRepositories(env.DB, () => NOW);

async function scheduledMatch(date: string, home: number, away: number): Promise<void> {
  await env.DB.prepare(
    `INSERT INTO matches (comp_code, season, match_date, kickoff_utc, home_team_id, away_team_id,
       status, updated_at) VALUES ('EPL', '2026-27', ?1, ?2, ?3, ?4, 'TIMED', '2026-10-17T00:00:00Z')`,
  )
    .bind(date, `${date}T15:00:00Z`, home, away)
    .run();
}

async function receivedUpload(updateId: number, receivedAt: string): Promise<void> {
  await env.DB.prepare(
    "INSERT INTO uploads (update_id, received_at, status) VALUES (?1, ?2, 'received')",
  )
    .bind(updateId, receivedAt)
    .run();
}

function deps(
  overrides: Partial<WatchdogDeps> = {},
  fake = fakeTelegram(),
): [WatchdogDeps, ReturnType<typeof fakeTelegram>] {
  return [
    {
      repos: repos(),
      telegram: createTelegramClient(TOKEN, fake.fetch),
      chatId: CHAT_ID,
      now: () => NOW,
      ...overrides,
    },
    fake,
  ];
}

const events = async (kind: string): Promise<number> => count("events", `kind = '${kind}'`);

beforeEach(async () => {
  await resetWorld();
  await seedReference();
});

describe("collectFindings", () => {
  it("finds nothing when the run is fresh, forecasts exist and no upload is stuck", async () => {
    await seedRun({ activatedAt: FRESH });
    await scheduledMatch(TODAY, 1, 2);
    await seedForecast({ home: 1, away: 2, date: TODAY });
    expect(await collectFindings(repos(), NOW)).toEqual([]);
  });

  it("reports that no run is published, and does not ask about forecasts then", async () => {
    await scheduledMatch(TODAY, 1, 2);
    const findings = await collectFindings(repos(), NOW);
    expect(findings.map((f) => f.key)).toEqual(["no_active_run"]);
  });

  it("reports a run older than its stale limit, with its age", async () => {
    await seedRun({ activatedAt: "2026-10-16T13:00:00Z" }); // 37 h
    const [finding] = await collectFindings(repos(), NOW);
    expect(finding?.key).toBe("stale_run");
    expect(finding?.text).toContain("37 h old");
    expect(finding?.text).toContain("R20261017T011700Z");
  });

  it("uses the stale limit stored in the run's config, and the default when it is unreadable", async () => {
    await seedRun({ activatedAt: "2026-10-17T20:00:00Z", config: { stale_hours: 4 } }); // 6 h old
    expect((await collectFindings(repos(), NOW)).map((f) => f.key)).toEqual(["stale_run"]);
    await resetWorld();
    await seedReference();
    await seedRun({ activatedAt: "2026-10-17T20:00:00Z", config: { stale_hours: "soon" } });
    expect(await collectFindings(repos(), NOW)).toEqual([]);
  });

  it("treats an unreadable activation time as stale instead of crashing", async () => {
    await seedRun({ activatedAt: "not a time" });
    const [finding] = await collectFindings(repos(), NOW);
    expect(finding?.key).toBe("stale_run");
    expect(finding?.text).toContain("unreadable age");
  });

  it("reports scheduled fixtures that have no forecast, naming the days", async () => {
    await seedRun({ activatedAt: FRESH });
    await scheduledMatch(TODAY, 1, 2);
    await scheduledMatch(TOMORROW, 3, 4);
    await seedForecast({ home: 1, away: 2, date: TODAY });
    const findings = await collectFindings(repos(), NOW);
    expect(findings).toHaveLength(1);
    expect(findings[0]?.key).toBe("no_forecasts");
    expect(findings[0]?.text).toContain(`${TOMORROW} (1 scheduled)`);
    expect(findings[0]?.text).not.toContain(TODAY);
  });

  it("asks for no forecast on a day without scheduled fixtures or beyond tomorrow", async () => {
    await seedRun({ activatedAt: FRESH });
    await scheduledMatch("2026-10-20", 1, 2);
    expect(await collectFindings(repos(), NOW)).toEqual([]);
  });

  it("ignores forecasts of a run that is not active", async () => {
    await seedRun({ activatedAt: FRESH });
    await seedRun({ runId: "Rold", status: "superseded" });
    await scheduledMatch(TODAY, 1, 2);
    await seedForecast({ home: 1, away: 2, date: TODAY }, "Rold");
    expect((await collectFindings(repos(), NOW)).map((f) => f.key)).toEqual(["no_forecasts"]);
  });

  it("reports an upload stuck for ten minutes but not a fresh or a finished one", async () => {
    await seedRun({ activatedAt: FRESH });
    await receivedUpload(1, "2026-10-18T01:49:00Z"); // 11 min
    await receivedUpload(2, "2026-10-18T01:55:00Z"); // 5 min
    await env.DB.prepare(
      "INSERT INTO uploads (update_id, received_at, status) VALUES (3, '2026-10-18T00:00:00Z', 'processed')",
    ).run();
    const [finding] = await collectFindings(repos(), NOW);
    expect(finding?.key).toBe("stuck_upload");
    expect(finding?.text.startsWith("1 upload(s)")).toBe(true);
  });
});

describe("runWatchdog", () => {
  it("sends each finding to the allowed chat and records it", async () => {
    const [d, fake] = deps();
    const outcome = await runWatchdog(d);
    expect(outcome).toEqual({ findings: 1, sent: 1, skipped: 0, failed: 0 });
    expect(fake.sent).toHaveLength(1);
    expect(fake.sent[0]?.chatId).toBe(CHAT_ID);
    expect(fake.sent[0]?.text.startsWith("ALERT: No model run is published")).toBe(true);
    expect(await events("watchdog_no_active_run")).toBe(1);
  });

  it("does not repeat an alert inside 24 hours but does after", async () => {
    const [first] = deps();
    await runWatchdog(first);
    const [second, fake] = deps();
    expect(await runWatchdog(second)).toEqual({ findings: 1, sent: 0, skipped: 1, failed: 0 });
    expect(fake.sent).toHaveLength(0);

    const later = new Date(NOW.getTime() + 25 * 3_600_000);
    const [third, fake3] = deps({
      now: () => later,
      repos: createRepositories(env.DB, () => later),
    });
    expect((await runWatchdog(third)).sent).toBe(1);
    expect(fake3.sent).toHaveLength(1);
  });

  it("sends nothing when everything is fine", async () => {
    await seedRun({ activatedAt: FRESH });
    const [d, fake] = deps();
    expect(await runWatchdog(d)).toEqual({ findings: 0, sent: 0, skipped: 0, failed: 0 });
    expect(fake.calls).toEqual([]);
  });

  it("keeps the alert for the next run when Telegram refuses it", async () => {
    const [d] = deps({}, fakeTelegram({ failSendFrom: 1 }));
    const outcome = await runWatchdog(d);
    expect(outcome.failed).toBe(1);
    expect(await events("watchdog_no_active_run")).toBe(0);
    expect(await events("alert_send_failed")).toBe(1);

    const [retry, fake] = deps();
    expect((await runWatchdog(retry)).sent).toBe(1);
    expect(fake.sent).toHaveLength(1);
  });

  it("leaves a trace the health check reads when the bot token is missing", async () => {
    const [d] = deps({ telegram: null });
    expect((await runWatchdog(d)).failed).toBe(1);
    expect(await events("bot_token_missing")).toBe(1);
  });

  it("records an unusable allowlist instead of sending to nobody", async () => {
    const [d, fake] = deps({ chatId: null });
    expect((await runWatchdog(d)).failed).toBe(1);
    expect(await events("alert_chat_invalid")).toBe(1);
    expect(fake.calls).toEqual([]);
  });

  it("survives a failing database read: no throw, one event, no message", async () => {
    const broken = repos();
    broken.runs.readPointer = async () => {
      throw new Error("D1 unavailable");
    };
    const [d, fake] = deps({ repos: broken });
    expect(await runWatchdog(d)).toEqual({ findings: 0, sent: 0, skipped: 0, failed: 1 });
    expect(await events("watchdog_failed")).toBe(1);
    expect(fake.calls).toEqual([]);
  });

  it("sends several findings as separate messages", async () => {
    await seedRun({ activatedAt: "2026-10-16T13:00:00Z" });
    await scheduledMatch(TODAY, 1, 2);
    await receivedUpload(1, "2026-10-18T01:00:00Z");
    const [d, fake] = deps();
    expect((await runWatchdog(d)).sent).toBe(3);
    expect(fake.sent.map((m) => m.text.split(" ")[1])).toEqual(["The", "No", "1"]);
  });
});

describe("handleScheduled (the cron entry)", () => {
  it("runs the watchdog with the real bindings and the injected Telegram", async () => {
    const fake = fakeTelegram();
    const outcome = await handleScheduled(env, {
      fetch: fake.fetch,
      now: () => NOW,
      newErrorId: () => "E",
    });
    expect(outcome.sent).toBe(1);
    expect(fake.sent[0]?.chatId).toBe(CHAT_ID);
  });
});
