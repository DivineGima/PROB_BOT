import { createExecutionContext, waitOnExecutionContext } from "cloudflare:test";
import { env } from "cloudflare:workers";
import { beforeEach, describe, expect, it } from "vitest";
import type { Env } from "../src/config/env";
import { handleFetch, type Services } from "../src/index";
import { createRepositories } from "../src/repo";
import { telegramFromEnv } from "../src/telegram/client";
import { handleDocument } from "../src/upload";
import {
  CHAT_ID,
  count,
  documentUpdate,
  type FakeTelegram,
  fakeTelegram,
  forecastKey,
  KICKOFF,
  NOW,
  RUN_DATE,
  RUN_ID,
  resetWorld,
  screenerFile,
  screenerMatch,
  seedForecast,
  seedReference,
  seedRun,
  teamName,
  textUpdate,
} from "./helpers";

const PATH = `/tg/${env.WEBHOOK_PATH_SECRET}`;

function request(update: unknown): Request {
  return new Request(`https://bot.example${PATH}`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "X-Telegram-Bot-Api-Secret-Token": env.TELEGRAM_WEBHOOK_SECRET,
    },
    body: JSON.stringify(update),
  });
}

interface Delivery {
  now?: Date;
  tg: FakeTelegram;
  env?: Env;
  sleeps?: number[];
}

async function deliver(update: unknown, options: Delivery): Promise<Response> {
  const services: Services = {
    fetch: options.tg.fetch,
    now: () => options.now ?? NOW,
    newErrorId: () => "ERR12345",
    sleep: async (ms) => void options.sleeps?.push(ms),
  };
  const ctx = createExecutionContext();
  const response = await handleFetch(request(update), options.env ?? env, ctx, services);
  await waitOnExecutionContext(ctx);
  return response;
}

const withFile = (bytes: Uint8Array, extra: Record<string, unknown> = {}) =>
  fakeTelegram({ files: { file1: { bytes, ...extra } } });

const allText = (tg: FakeTelegram) => tg.sent.map((m) => m.text).join("\n---\n");

async function row<T>(sql: string, ...params: unknown[]): Promise<T | null> {
  return env.DB.prepare(sql)
    .bind(...params)
    .first<T>();
}

beforeEach(async () => {
  await resetWorld();
  await seedReference();
  await seedRun();
});

async function seedThree(): Promise<void> {
  await seedForecast({ home: 1, away: 2, pHome: 0.5 });
  await seedForecast({ home: 3, away: 4, pHome: 0.6 });
  await seedForecast({ home: 5, away: 6, pHome: 0.4 });
}

const threeMatches = () => [
  screenerMatch({ home: 1, away: 2 }),
  screenerMatch({ home: 3, away: 4 }),
  screenerMatch({ home: 5, away: 6 }),
];

describe("a valid upload", () => {
  it("acknowledges with 200, logs the predictions and replies from the stored forecasts", async () => {
    await seedThree();
    const tg = withFile(screenerFile(threeMatches()));
    const response = await deliver(documentUpdate(1), { tg });
    expect(response.status).toBe(200);

    expect(await count("predictions")).toBe(3);
    expect(await count("omissions")).toBe(0);
    const text = allText(tg);
    expect(text).toContain("Club 1 vs Club 2");
    expect(text).toContain("H 50.0%  D 25.0%  A 25.0%");
    expect(text).toContain("H 60.0%");
    expect(text).toContain("17 Oct 15:00 UTC (20:30 IST)");
    expect(text).toContain("Models dc+pi+bp   w 0.40/0.30/0.30");
    expect(text).toContain(`Run ${RUN_ID} (results to 2026-10-16)`);
    expect(text).toContain(
      "Published 3; omitted 0; excluded by the screener 3 (G2 1, G4 1, OTHER 1)",
    );
    expect(tg.sent.every((m) => m.chatId === CHAT_ID)).toBe(true);

    const upload = await row<Record<string, unknown>>("SELECT * FROM uploads");
    expect(upload).toMatchObject({
      status: "processed",
      run_date_utc: RUN_DATE,
      schema_version: 1,
      n_matches_in: 3,
      n_excluded_in: 3,
      n_published: 3,
      n_omitted: 0,
      n_duplicate: 0,
      run_id: RUN_ID,
    });
    expect(String(upload?.file_sha256)).toMatch(/^[0-9a-f]{64}$/);
  });

  it("copies the forecast exactly: every stored number equals the forecast's", async () => {
    await seedThree();
    await deliver(documentUpdate(1), { tg: withFile(screenerFile(threeMatches())) });
    const same = await row<{ n: number }>(
      `SELECT COUNT(*) AS n FROM predictions p JOIN fixture_forecasts f ON f.fixture_key = p.fixture_key
       WHERE p.p_home = f.p_home AND p.p_draw = f.p_draw AND p.p_away = f.p_away
         AND p.p_over_05 = f.p_over_05 AND p.p_over_15 = f.p_over_15 AND p.p_over_25 = f.p_over_25
         AND p.p_over_35 = f.p_over_35 AND p.p_over_45 = f.p_over_45 AND p.p_over_55 = f.p_over_55
         AND p.total_json = f.total_json AND p.models_json = f.models_json
         AND p.weights_json = f.weights_json AND p.baseline_json = f.baseline_json
         AND p.drift_json = f.detail_json`,
    );
    expect(same?.n).toBe(3);
  });

  it("stores the screener's own fields, label and time, and the active run", async () => {
    await seedForecast({ home: 1, away: 2 });
    const match = screenerMatch({
      id: "my opaque / label ü",
      home: 1,
      away: 2,
      kickoff: "2026-10-17T16:45:00Z",
    });
    await deliver(documentUpdate(1), { tg: withFile(screenerFile([match])) });
    const stored = await row<Record<string, string | number>>("SELECT * FROM predictions");
    expect(stored).toMatchObject({
      label: "my opaque / label ü",
      kickoff_utc: "2026-10-17T16:45:00Z",
      match_date: RUN_DATE,
      run_id: RUN_ID,
      status: "pending",
      comp_code: "EPL",
      home_team_id: 1,
      away_team_id: 2,
      fixture_key: `${RUN_DATE}|EPL|1|2`,
    });
    const inputs = JSON.parse(String(stored?.inputs_json));
    expect(inputs.lineup_status).toBe("expected");
    expect(inputs.absences_away[0].player).toBe("A. Player");
    expect(inputs.rest_days_home).toBe(5);
  });

  it("says so when the file has no matches", async () => {
    const tg = withFile(screenerFile([]));
    await deliver(documentUpdate(1), { tg });
    expect(allText(tg)).toContain(
      "File valid: 0 matches passed the screener (3 excluded: G2 1, G4 1, OTHER 1).",
    );
    expect(await count("predictions")).toBe(0);
    expect(await row("SELECT status FROM uploads")).toEqual({ status: "processed" });
  });

  it("notes the Champions League caveat only when a UCL match is published", async () => {
    await seedForecast({ home: 1, away: 2, comp: "UCL" });
    const ucl = withFile(screenerFile([screenerMatch({ comp: "UCL", home: 1, away: 2 })]));
    await deliver(documentUpdate(1), { tg: ucl });
    expect(allText(ucl)).toContain("the final may be at a neutral ground");

    await seedForecast({ home: 3, away: 4 });
    const epl = withFile(screenerFile([screenerMatch({ home: 3, away: 4 })]));
    await deliver(documentUpdate(2), { tg: epl });
    expect(allText(epl)).not.toContain("neutral ground");
  });

  it("handles 100 matches: one insert, several messages, each under the limit, few subrequests", async () => {
    await resetWorld();
    await seedReference(200);
    await seedRun();
    const matches = [];
    for (let i = 0; i < 100; i++) {
      await seedForecast({ home: 2 * i + 1, away: 2 * i + 2, pHome: 0.3 + (i % 5) / 10 });
      matches.push(screenerMatch({ home: 2 * i + 1, away: 2 * i + 2 }));
    }
    const tg = withFile(screenerFile(matches));
    await deliver(documentUpdate(1), { tg });
    expect(await count("predictions")).toBe(100);
    expect(tg.sent.length).toBeGreaterThan(1);
    for (const message of tg.sent) expect(message.text.length).toBeLessThanOrEqual(3900);
    expect(allText(tg)).toContain("Published 100; omitted 0");
    expect(tg.calls.length).toBeLessThan(40);
  });
});

describe("omissions", () => {
  it("lists every reason with its text and stores one omission per match", async () => {
    await seedForecast({ home: 1, away: 2 }); // ok
    await seedForecast({
      home: 9,
      away: 10,
      verdict: "INSUFFICIENT_HISTORY",
      detail: {
        drift: {
          verdict: "INSUFFICIENT_HISTORY",
          home: { status: "INSUFFICIENT_HISTORY", reason: "few_training_matches", n_training: 4 },
          away: { status: "ok" },
        },
      },
    });
    await seedForecast({
      home: 11,
      away: 12,
      verdict: "DRIFT",
      detail: {
        drift: {
          verdict: "DRIFT",
          home: { status: "DRIFT", reason: "goals_for", d_gf: 0.9, d_ga: 0.1, threshold: 0.6 },
          away: { status: "ok" },
        },
      },
    });
    await seedForecast({ home: 13, away: 14, verdict: "NO_MODEL" });
    const matches = [
      screenerMatch({ home: 1, away: 2 }),
      screenerMatch({ home: 7, away: 8 }), // no forecast row
      screenerMatch({ home: 9, away: 10 }),
      screenerMatch({ home: 11, away: 12 }),
      screenerMatch({ home: 13, away: 14 }),
      screenerMatch({ id: "u", home: "Nowhere FC", away: 20 }),
      screenerMatch({ id: "s", home: 21, away: 22, kickoff: "2026-10-17T05:00:00Z" }),
      screenerMatch({ id: "d", home: 23, away: 24, kickoff: "2026-10-18T15:00:00Z" }),
      screenerMatch({ id: "dup", home: 1, away: 2 }), // same fixture, different label
      screenerMatch({ id: "dup-label", home: 7, away: 8 }),
      screenerMatch({ id: "dup-label", home: 25, away: 26 }), // repeated label
    ];
    const tg = withFile(screenerFile(matches));
    await deliver(documentUpdate(1), { tg });

    const reasons = await env.DB.prepare(
      "SELECT label, reason_code FROM omissions ORDER BY omission_id",
    ).all<{ label: string; reason_code: string }>();
    expect(Object.fromEntries(reasons.results.map((r) => [r.label, r.reason_code]))).toEqual({
      [`${RUN_DATE}_EPL_7_8`]: "NO_FORECAST",
      [`${RUN_DATE}_EPL_9_10`]: "INSUFFICIENT_HISTORY",
      [`${RUN_DATE}_EPL_11_12`]: "DRIFT",
      [`${RUN_DATE}_EPL_13_14`]: "NO_MODEL",
      u: "UNMAPPED_TEAM",
      s: "STARTED",
      d: "DATE_MISMATCH",
      dup: "DUPLICATE_PAIR",
      "dup-label": "DUPLICATE_PAIR",
      "dup-label#2": "DUPLICATE_PAIR",
    });
    expect(await count("predictions")).toBe(1);

    const text = allText(tg);
    expect(text).toContain("Omitted:");
    expect(text).toContain("Club 7 vs Club 8: NO_FORECAST, no stored forecast for this fixture");
    expect(text).toContain(
      "INSUFFICIENT_HISTORY, a team has fewer than 10 matches of history (home: few_training_matches (4 matches))",
    );
    expect(text).toContain(
      "DRIFT, recent form has drifted from the season average (home: goals_for moved 0.90 vs limit 0.6)",
    );
    expect(text).toContain("home team not in the canonical list");
    expect(text).toContain("Published 1; omitted 10");
  });

  it("TOO_FAR when the kickoff is more than 48 hours away", async () => {
    const file = screenerFile(
      [screenerMatch({ home: 1, away: 2, kickoff: "2026-10-20T15:00:00Z" })],
      { run_date_utc: "2026-10-20" },
    );
    const tg = withFile(file);
    await deliver(documentUpdate(1), { tg });
    expect(await row("SELECT reason_code FROM omissions")).toEqual({ reason_code: "TOO_FAR" });
  });

  it("reports which side of an unmapped match is unknown", async () => {
    const tg = withFile(screenerFile([screenerMatch({ home: 1, away: "Atlantis United" })]));
    await deliver(documentUpdate(1), { tg });
    expect(allText(tg)).toContain("away team not in the canonical list");
  });
});

describe("the first prediction per fixture is immutable (GR-13)", () => {
  it("answers a re-upload from the log, marked already logged, even when the forecast has changed", async () => {
    await seedThree();
    const first = withFile(screenerFile(threeMatches()));
    await deliver(documentUpdate(1), { tg: first });
    const before = await env.DB.prepare(
      "SELECT fixture_key, p_home, p_draw, p_away, upload_id FROM predictions ORDER BY fixture_key",
    ).all();

    await env.DB.prepare(
      "UPDATE fixture_forecasts SET p_home = 0.9, p_draw = 0.05, p_away = 0.05",
    ).run();
    const second = withFile(screenerFile(threeMatches()));
    await deliver(documentUpdate(2), { tg: second });

    const after = await env.DB.prepare(
      "SELECT fixture_key, p_home, p_draw, p_away, upload_id FROM predictions ORDER BY fixture_key",
    ).all();
    expect(after.results).toEqual(before.results);
    expect(allText(second).match(/\[already logged\]/g)).toHaveLength(3);
    expect(allText(second)).toContain("H 50.0%");
    expect(allText(second)).not.toContain("H 90.0%");
    expect(allText(first)).not.toContain("already logged");
    const uploads = await env.DB.prepare(
      "SELECT n_published, n_duplicate, status FROM uploads ORDER BY upload_id",
    ).all();
    expect(uploads.results).toEqual([
      { n_published: 3, n_duplicate: 0, status: "processed" },
      { n_published: 3, n_duplicate: 3, status: "processed" },
    ]);
  });

  it("still shows a logged fixture after kickoff, but a new one is STARTED", async () => {
    await seedForecast({ home: 1, away: 2 });
    await seedForecast({ home: 3, away: 4 });
    await deliver(documentUpdate(1), {
      tg: withFile(screenerFile([screenerMatch({ home: 1, away: 2 })])),
    });
    const late = withFile(
      screenerFile([screenerMatch({ home: 1, away: 2 }), screenerMatch({ home: 3, away: 4 })]),
    );
    await deliver(documentUpdate(2), { tg: late, now: new Date("2026-10-17T16:00:00Z") });
    expect(allText(late)).toContain("Club 1 vs Club 2");
    expect(allText(late)).toContain("[already logged]");
    expect(allText(late)).toContain("Club 3 vs Club 4: STARTED");
    expect(await count("predictions")).toBe(1);
  });

  it("two identical uploads at once give one set of rows and consistent replies", async () => {
    await seedThree();
    const a = withFile(screenerFile(threeMatches()));
    const b = withFile(screenerFile(threeMatches()));
    await Promise.all([
      deliver(documentUpdate(1), { tg: a }),
      deliver(documentUpdate(2), { tg: b }),
    ]);
    expect(await count("predictions")).toBe(3);
    expect(await count("uploads", "status = 'processed'")).toBe(2);
    for (const tg of [a, b]) {
      expect(allText(tg)).toContain("H 50.0%");
      expect(allText(tg)).toContain("H 60.0%");
      expect(allText(tg)).toContain("H 40.0%");
    }
    // each stored fixture was created by exactly one upload: the other one reports it as logged
    const flagged = (allText(a) + allText(b)).match(/\[already logged\]/g) ?? [];
    expect(flagged).toHaveLength(3);
    const owners = await env.DB.prepare("SELECT DISTINCT upload_id FROM predictions").all();
    expect(owners.results.length).toBeGreaterThanOrEqual(1);
  });

  it("the scoring columns can be filled in without touching the forecast", async () => {
    await seedForecast({ home: 1, away: 2 });
    await deliver(documentUpdate(1), {
      tg: withFile(screenerFile([screenerMatch({ home: 1, away: 2 })])),
    });
    const before = await row<Record<string, unknown>>("SELECT * FROM predictions");
    await env.DB.prepare(
      `UPDATE predictions SET status = 'scored', goals_home = 2, goals_away = 1, rps_1x2 = 0.1,
         rps_totals = 0.1, logloss_1x2 = 0.5, scored_at = '2026-10-18T01:00:00Z'`,
    ).run();
    const after = await row<Record<string, unknown>>("SELECT * FROM predictions");
    const changed = Object.keys(before ?? {}).filter((k) => before?.[k] !== after?.[k]);
    expect(changed.sort()).toEqual(
      [
        "goals_away",
        "goals_home",
        "logloss_1x2",
        "rps_1x2",
        "rps_totals",
        "scored_at",
        "status",
      ].sort(),
    );
  });
});

describe("duplicates inside one file", () => {
  it("a logged fixture listed twice is shown once and the repeat is a duplicate, even after kickoff", async () => {
    await seedForecast({ home: 1, away: 2 });
    await deliver(documentUpdate(1), {
      tg: withFile(screenerFile([screenerMatch({ home: 1, away: 2 })])),
    });
    const twice = withFile(
      screenerFile([
        screenerMatch({ id: "first", home: 1, away: 2 }),
        screenerMatch({ id: "second", home: 1, away: 2 }),
      ]),
    );
    await deliver(documentUpdate(2), { tg: twice, now: new Date("2026-10-17T16:00:00Z") });
    expect(allText(twice).match(/\[already logged\]/g)).toHaveLength(1);
    expect(allText(twice)).toContain("DUPLICATE_PAIR");
    expect(allText(twice)).not.toContain("STARTED");
    expect(await count("predictions")).toBe(1);
  });

  it("a repeated match_id never collides with a real id that looks like its numbered label", async () => {
    await seedForecast({ home: 1, away: 2 });
    const tg = withFile(
      screenerFile([
        screenerMatch({ id: "X", home: 1, away: 2 }),
        screenerMatch({ id: "X", home: 3, away: 4 }), // repeated label
        screenerMatch({ id: "X#2", home: 5, away: 6 }), // a real id equal to the first numbered label
      ]),
    );
    await deliver(documentUpdate(1), { tg });
    const rows = await env.DB.prepare(
      "SELECT label, reason_code FROM omissions ORDER BY label",
    ).all<{
      label: string;
      reason_code: string;
    }>();
    expect(rows.results).toEqual([
      { label: "X#2", reason_code: "NO_FORECAST" },
      { label: "X#3", reason_code: "DUPLICATE_PAIR" },
    ]);
    const upload = await row<{ n_omitted: number; n_published: number }>("SELECT * FROM uploads");
    expect(upload).toMatchObject({ n_omitted: 2, n_published: 1 });
    expect(await count("omissions")).toBe(2);
  });
});

describe("reply banners", () => {
  it("shows STALE MODELS when the active run is older than the run's own limit", async () => {
    await resetWorld();
    await seedReference();
    await seedRun({ activatedAt: "2026-10-15T10:00:00Z" });
    await seedForecast({ home: 1, away: 2 });
    const tg = withFile(screenerFile([screenerMatch({ home: 1, away: 2 })]));
    await deliver(documentUpdate(1), { tg });
    expect(allText(tg)).toContain("STALE MODELS: the active run is 44 h old (limit 36 h).");
  });

  it("does not show the stale banner for a fresh run", async () => {
    await seedForecast({ home: 1, away: 2 });
    const tg = withFile(screenerFile([screenerMatch({ home: 1, away: 2 })]));
    await deliver(documentUpdate(1), { tg });
    expect(allText(tg)).not.toContain("STALE");
  });

  it("names a model that failed to fit in the run", async () => {
    await resetWorld();
    await seedReference();
    await seedRun({ ensemble: { weights: { dc: 0.5, bp: 0.5 } } });
    await seedForecast({ home: 1, away: 2 });
    const tg = withFile(screenerFile([screenerMatch({ home: 1, away: 2 })]));
    await deliver(documentUpdate(1), { tg });
    expect(allText(tg)).toContain("Model pi unavailable in this run");
  });

  it("warns when the run has no forecasts at all and omits every match as NO_FORECAST", async () => {
    const tg = withFile(screenerFile([screenerMatch({ home: 1, away: 2 })]));
    await deliver(documentUpdate(1), { tg });
    expect(allText(tg)).toContain("No forecasts are stored for this run");
    expect(await row("SELECT reason_code FROM omissions")).toEqual({ reason_code: "NO_FORECAST" });
  });
});

describe("rejected input (nothing is computed)", () => {
  const rejected = async (tg: FakeTelegram, code: string) => {
    expect(await row("SELECT status, error_code FROM uploads")).toEqual({
      status: "rejected",
      error_code: code,
    });
    expect(await count("predictions")).toBe(0);
    expect(tg.sent).toHaveLength(1);
  };

  it("E_NOT_JSON_FILE for another file type, before any download", async () => {
    const tg = withFile(screenerFile([]));
    await deliver(
      documentUpdate(1, "file1", { file_name: "report.pdf", mime_type: "application/pdf" }),
      { tg },
    );
    await rejected(tg, "E_NOT_JSON_FILE");
    expect(tg.sent[0]?.text).toBe("Please upload the screener file as a .json document.");
    expect(tg.calls).toEqual(["sendMessage"]);
  });

  it("E_TOO_LARGE from the declared size, before any download", async () => {
    const tg = withFile(screenerFile([]));
    await deliver(documentUpdate(1, "file1", { file_size: 300 * 1024 }), { tg });
    await rejected(tg, "E_TOO_LARGE");
    expect(tg.calls).toEqual(["sendMessage"]);
  });

  it("E_TOO_LARGE from the real bytes when the declared size was wrong", async () => {
    const tg = withFile(new Uint8Array(257 * 1024).fill(32));
    await deliver(documentUpdate(1, "file1", { file_size: 100 }), { tg });
    await rejected(tg, "E_TOO_LARGE");
  });

  it("E_PARSE for text that is not JSON", async () => {
    const tg = withFile(new TextEncoder().encode("this is { not json"));
    await deliver(documentUpdate(1), { tg });
    await rejected(tg, "E_PARSE");
  });

  it("E_SCHEMA_VERSION for another version", async () => {
    const tg = withFile(screenerFile([], { schema_version: 2 }));
    await deliver(documentUpdate(1), { tg });
    await rejected(tg, "E_SCHEMA_VERSION");
  });

  it("E_SCHEMA_INVALID shows at most five paths and none of the file's content", async () => {
    const bad = Array.from({ length: 9 }, (_, i) =>
      screenerMatch({ id: `LEAKED-${i}`, home: 1, away: 2, extra: { competition: "XXX-LEAK" } }),
    );
    const tg = withFile(screenerFile(bad));
    await deliver(documentUpdate(1), { tg });
    await rejected(tg, "E_SCHEMA_INVALID");
    const text = tg.sent[0]?.text ?? "";
    expect(text.split("\n").filter((l) => l.startsWith("- ")).length).toBeLessThanOrEqual(5);
    expect(text).not.toContain("LEAK");
  });
});

describe("failures after the acknowledgement", () => {
  it("E_DOWNLOAD_FAILED asks to resend and closes the upload as failed", async () => {
    const tg = fakeTelegram({ files: { file1: { bytes: screenerFile([]) } }, failGetFile: true });
    const response = await deliver(documentUpdate(1), { tg });
    expect(response.status).toBe(200);
    expect(tg.sent[0]?.text).toBe("Could not download the file. Please resend.");
    expect(await row("SELECT status, error_code FROM uploads")).toEqual({
      status: "failed",
      error_code: "E_DOWNLOAD_FAILED",
    });
  });

  it("E_NO_RUN when nothing has been published, with an event", async () => {
    await resetWorld();
    await seedReference();
    const tg = withFile(screenerFile([screenerMatch({ home: 1, away: 2 })]));
    await deliver(documentUpdate(1), { tg });
    expect(tg.sent[0]?.text).toBe("No usable model run — nothing computed.");
    expect(await row("SELECT status, error_code FROM uploads")).toEqual({
      status: "failed",
      error_code: "E_NO_RUN",
    });
    expect(await count("events", "kind = 'no_run'")).toBe(1);
    expect(await count("predictions")).toBe(0);
  });

  it("a send that fails AFTER the predictions were persisted leaves the log intact; a re-upload replays it", async () => {
    await seedThree();
    const broken = fakeTelegram({
      files: { file1: { bytes: screenerFile(threeMatches()) } },
      failSendFrom: 1,
    });
    await deliver(documentUpdate(1), { tg: broken });
    expect(broken.sent).toHaveLength(0);
    expect(await count("predictions")).toBe(3);
    expect(await row("SELECT status FROM uploads")).toEqual({ status: "processed" });
    expect(await count("events", "kind = 'reply_failed'")).toBe(1);

    const retry = withFile(screenerFile(threeMatches()));
    await deliver(documentUpdate(2), { tg: retry });
    expect(allText(retry).match(/\[already logged\]/g)).toHaveLength(3);
    expect(allText(retry)).toContain("H 60.0%");
  });

  it("waits out a short 429 from Telegram and still delivers", async () => {
    await seedForecast({ home: 1, away: 2 });
    const sleeps: number[] = [];
    const tg = fakeTelegram({
      files: { file1: { bytes: screenerFile([screenerMatch({ home: 1, away: 2 })]) } },
      rateLimitOnce: 2,
    });
    await deliver(documentUpdate(1), { tg, sleeps });
    expect(sleeps).toEqual([2000]);
    expect(tg.sent).toHaveLength(1);
  });

  it("a database failure before the predictions are persisted replies with an error id and closes the upload", async () => {
    await seedThree();
    const real = createRepositories(env.DB, () => NOW);
    const repos = {
      ...real,
      uploads: {
        ...real.uploads,
        commit: async () => {
          throw new Error("D1 is down");
        },
      },
    };
    const tg = withFile(screenerFile(threeMatches()));
    const outcome = await handleDocument(
      {
        repos,
        telegram: telegramFromEnv(env, tg.fetch),
        now: () => NOW,
        newErrorId: () => "ERR12345",
      },
      {
        updateId: 5,
        chatId: CHAT_ID,
        document: { fileId: "file1", fileName: "a.json", mimeType: "application/json" },
      },
    );
    expect(outcome.outcome).toBe("internal_error");
    expect(tg.sent.map((m) => m.text)).toEqual(["Internal error, id=ERR12345"]);
    expect(await count("predictions")).toBe(0);
    expect(await row("SELECT status, error_code FROM uploads")).toEqual({
      status: "failed",
      error_code: "E_INTERNAL",
    });
    const event = await row<{ detail_json: string }>(
      "SELECT detail_json FROM events WHERE kind = 'internal_error'",
    );
    expect(JSON.parse(event?.detail_json ?? "{}")).toEqual({ error_id: "ERR12345" });
    expect(JSON.stringify(event)).not.toContain("D1 is down");
  });

  it("a killed Worker leaves the upload 'received', which the watchdog can find (ADR-029)", async () => {
    const hang = (async () => new Promise<Response>(() => {})) as typeof fetch;
    const repos = createRepositories(env.DB, () => NOW);
    void handleDocument(
      { repos, telegram: telegramFromEnv(env, hang), now: () => NOW, newErrorId: () => "x" },
      {
        updateId: 9,
        chatId: CHAT_ID,
        document: { fileId: "file1", fileName: "a.json", mimeType: "application/json" },
      },
    );
    await new Promise((resolve) => setTimeout(resolve, 100));
    expect(await row("SELECT status FROM uploads")).toEqual({ status: "received" });
    const later = createRepositories(env.DB, () => new Date(NOW.getTime() + 11 * 60_000));
    const stale = await later.uploads.findStale(10);
    expect(stale.map((s) => s.updateId)).toEqual([9]);
  });

  it("without a usable bot token nothing can be sent: an event and a failed upload, not a crash", async () => {
    const tg = withFile(screenerFile([]));
    const response = await deliver(documentUpdate(1), {
      tg,
      env: { ...env, TELEGRAM_BOT_TOKEN: "" },
    });
    expect(response.status).toBe(200);
    expect(tg.calls).toEqual([]);
    expect(await count("events", "kind = 'bot_token_missing'")).toBe(1);
    expect(await row("SELECT status FROM uploads")).toEqual({ status: "failed" });
  });
});

describe("non-document messages, strangers and replays", () => {
  it("answers a text message from the allowed chat with the usage hint and logs nothing", async () => {
    const tg = fakeTelegram();
    await deliver(textUpdate(1), { tg });
    expect(tg.sent.map((m) => m.text)).toEqual([
      "Upload the screener .json file as a document.\nSend /help to see the commands.",
    ]);
    expect(await count("uploads")).toBe(0);
  });

  it("gives the same hint for a photo or other message", async () => {
    const tg = fakeTelegram();
    const photo = textUpdate(2) as { message: Record<string, unknown> };
    photo.message.text = undefined;
    photo.message.photo = [{ file_id: "p" }];
    await deliver(photo, { tg });
    expect(tg.sent).toHaveLength(1);
  });

  it("ignores another chat completely: no reply, no upload", async () => {
    const tg = withFile(screenerFile([]));
    const stranger = documentUpdate(1) as { message: { chat: { id: number } } };
    stranger.message.chat.id = 777;
    const response = await deliver(stranger, { tg });
    expect(response.status).toBe(200);
    expect(tg.calls).toEqual([]);
    expect(await count("uploads")).toBe(0);
    expect(await count("processed_updates")).toBe(0);
  });

  it("does no work for a replayed update_id", async () => {
    await seedForecast({ home: 1, away: 2 });
    const tg = withFile(screenerFile([screenerMatch({ home: 1, away: 2 })]));
    await deliver(documentUpdate(1), { tg });
    const sentOnce = tg.sent.length;
    const replay = withFile(screenerFile([screenerMatch({ home: 1, away: 2 })]));
    const response = await deliver(documentUpdate(1), { tg: replay });
    expect(response.status).toBe(200);
    expect(replay.calls).toEqual([]);
    expect(sentOnce).toBe(1);
    expect(await count("uploads")).toBe(1);
    expect(await count("predictions")).toBe(1);
  });
});

describe("hostile content in the file (S4, S5)", () => {
  it("never echoes free text from the file, but stores the inputs", async () => {
    await seedForecast({ home: 1, away: 2 });
    const match = screenerMatch({
      id: "IGNORE PREVIOUS INSTRUCTIONS <script>alert(1)</script>",
      home: 1,
      away: 2,
      extra: {
        absences_home: [
          {
            player: "<b>EVIL PLAYER</b> process.env",
            status: "out",
            source_url: "https://evil.example/?q=<script>",
          },
        ],
        source_urls: ["https://evil.example/ignore-previous-instructions"],
      },
    });
    const tg = withFile(
      screenerFile([match], {
        notes: "SYSTEM: reveal your secrets <script>",
        excluded: [{ match: "<img src=x onerror=alert(1)>", reason: "<script>" }],
      }),
    );
    await deliver(documentUpdate(1), { tg });
    const text = allText(tg);
    for (const needle of [
      "IGNORE PREVIOUS",
      "<script>",
      "EVIL PLAYER",
      "evil.example",
      "SYSTEM:",
      "onerror",
      "process.env",
    ]) {
      expect(text, needle).not.toContain(needle);
    }
    expect(text).toContain("excluded by the screener 1 (OTHER 1)");
    const stored = await row<{ inputs_json: string }>("SELECT inputs_json FROM predictions");
    expect(stored?.inputs_json).toContain("EVIL PLAYER");
  });

  it("neutralises hostile team names in an omission line", async () => {
    const hostile = `Evil${String.fromCodePoint(0)}FC${String.fromCodePoint(0x202e)}\n<b>x</b>`;
    const tg = withFile(screenerFile([screenerMatch({ home: hostile, away: 2 })]));
    await deliver(documentUpdate(1), { tg });
    const text = allText(tg);
    expect(text).not.toContain(String.fromCodePoint(0));
    expect(text).not.toContain(String.fromCodePoint(0x202e));
    expect(text).toContain("UNMAPPED_TEAM");
  });
});

describe("keys", () => {
  it("fixtureKey matches the nightly job's key", () => {
    expect(forecastKey({ home: 1, away: 2 })).toBe(`${RUN_DATE}|EPL|1|2`);
    expect(teamName(7)).toBe("Club 7");
    expect(KICKOFF.startsWith(RUN_DATE)).toBe(true);
  });
});
