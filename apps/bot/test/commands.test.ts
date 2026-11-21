import { env } from "cloudflare:workers";
import { beforeEach, describe, expect, it } from "vitest";
import { type CommandDeps, handleCommand, matchTeam } from "../src/commands";
import { parseCommand } from "../src/commands/parse";
import { createRepositories, type Repositories } from "../src/repo";
import { createTelegramClient } from "../src/telegram/client";
import { collectFindings } from "../src/watchdog";
import {
  CHAT_ID,
  count,
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
  TOKEN,
  teamName,
} from "./helpers";

/** The command handlers (architecture 3, sections 6.10 and 8.12; essentials 3 step 5). */

const NOW = new Date("2026-10-17T06:00:00Z");

function deps(fake = fakeTelegram(), overrides: Partial<CommandDeps> = {}): CommandDeps {
  return {
    repos: createRepositories(env.DB, () => NOW),
    telegram: createTelegramClient(TOKEN, fake.fetch, async () => undefined),
    now: () => NOW,
    newErrorId: () => "err12345",
    ...overrides,
  };
}

async function ask(text: string, fake = fakeTelegram(), overrides: Partial<CommandDeps> = {}) {
  const outcome = await handleCommand(deps(fake, overrides), CHAT_ID, parseCommand(text));
  return { outcome, text: fake.sent.map((m) => m.text).join("\n---\n"), sent: fake.sent };
}

beforeEach(async () => {
  await resetWorld();
  await seedReference();
});

describe("routing inside the command module", () => {
  it("answers /help and /start with the list, to the allowed chat", async () => {
    for (const text of ["/help", "/start", "/HELP@ProbBot"]) {
      const { outcome, text: reply, sent } = await ask(text);
      expect(outcome).toMatchObject({ outcome: "command", command: "help" });
      expect(reply).toContain("/fixtures [today|tomorrow|YYYY-MM-DD]");
      expect(sent.every((m) => m.chatId === CHAT_ID)).toBe(true);
    }
  });

  it("answers an unknown command with the pointer to /help, never echoing it", async () => {
    const { outcome, text } = await ask("/rollback R20261016");
    expect(outcome).toEqual({ outcome: "unknown_command", counts: { n_messages: 1 } });
    expect(text).toBe("Unknown command. Send /help to see the commands.");
  });

  it("answers bad arguments with the usage line and reads nothing", async () => {
    for (const [text, usage] of [
      ["/fixtures someday", "Usage: /fixtures [today|tomorrow|YYYY-MM-DD]"],
      ["/logged 2026-02-30", "Usage: /logged [today|yesterday|YYYY-MM-DD]"],
      ["/results 50", "Usage: /results [n]"],
      ["/team", "Usage: /team <name>"],
      [`/team ${"x".repeat(70)}`, "Usage: /team <name>"],
    ] as const) {
      const { outcome, text: reply } = await ask(text);
      expect(outcome.outcome, text).toBe("command_usage");
      expect(reply, text).toBe(usage);
    }
  });

  it("answers an unexpected failure with an error id and one command_failed event", async () => {
    const repos = createRepositories(env.DB, () => NOW);
    const broken: Repositories = {
      ...repos,
      queries: {
        ...repos.queries,
        latestUpload: async () => {
          throw new Error("D1 is down");
        },
      },
    };
    const { outcome, text } = await ask("/last", fakeTelegram(), { repos: broken });
    expect(outcome).toMatchObject({
      outcome: "command_failed",
      command: "last",
      errorCode: "E_INTERNAL",
    });
    expect(text).toBe("Internal error, id=err12345");
    expect(await count("events", "kind = 'command_failed'")).toBe(1);
    const detail = await env.DB.prepare(
      "SELECT detail_json FROM events WHERE kind = 'command_failed'",
    ).first<{
      detail_json: string;
    }>();
    expect(JSON.parse(detail?.detail_json ?? "{}")).toEqual({
      command: "last",
      error_id: "err12345",
    });
  });

  it("records bot_token_missing and sends nothing without a token", async () => {
    const { outcome, sent } = await ask("/status", fakeTelegram(), { telegram: null });
    expect(outcome).toMatchObject({ outcome: "no_telegram_client", command: "status" });
    expect(sent).toEqual([]);
    expect(await count("events", "kind = 'bot_token_missing'")).toBe(1);
  });

  it("stops after a failed send and says so in the outcome", async () => {
    const { outcome } = await ask("/help", fakeTelegram({ failSendFrom: 1 }));
    expect(outcome.outcome).toBe("command_reply_failed");
  });
});

describe("/status", () => {
  it("reports the same findings as the watchdog on the same data", async () => {
    await seedRun({ activatedAt: "2026-10-15T01:30:00Z" }); // 52 h old: stale
    await seedScheduledMatch("2026-10-17", 1, 2); // no forecast stored
    await seedUpload(9, { status: "received", received_at: "2026-10-17T05:00:00Z" });
    const findings = await collectFindings(
      createRepositories(env.DB, () => NOW),
      NOW,
    );
    expect(findings.length).toBe(3);

    const { text } = await ask("/status");
    expect(text.split("\n")[0]).toBe("Status: ATTENTION");
    for (const f of findings) expect(text).toContain(`! ${f.text}`);
    expect(text).toContain("Unanswered uploads: 1");
  });

  it("is OK on a healthy system", async () => {
    await seedRun();
    for (const m of ["dc", "pi", "bp"]) await seedModelParams(m, "ok");
    await seedJob("fit", "ok", "2026-10-17T01:20:00Z", "2026-10-17T01:25:00Z");
    await seedScheduledMatch("2026-10-17", 1, 2);
    await seedForecast({ home: 1, away: 2 });
    await seedScheduledMatch("2026-10-18", 3, 4);
    await seedForecast({ home: 3, away: 4, date: "2026-10-18" });
    const { text } = await ask("/status");
    expect(text.split("\n")[0]).toBe("Status: OK");
    expect(text).toContain(`Run ${RUN_ID}`);
    expect(text).toContain("limit 36 h");
    expect(text).toContain("2026-10-17 1/1, 2026-10-18 1/1");
  });
});

describe("/fixtures", () => {
  it("shows today's verdicts by default and tomorrow's on request, never a probability", async () => {
    await seedRun();
    await seedForecast({ home: 1, away: 2, pHome: 0.61 });
    await seedForecast({ home: 3, away: 4, date: "2026-10-18", verdict: "INSUFFICIENT_HISTORY" });
    const today = await ask("/fixtures");
    expect(today.text).toContain(`${teamName(1)} vs ${teamName(2)}`);
    expect(today.text).not.toMatch(/%|\b0\.\d/);
    const tomorrow = await ask("/fixtures tomorrow");
    expect(tomorrow.text).toContain("INSUFFICIENT_HISTORY");
    expect(tomorrow.text).not.toContain(teamName(1));
  });

  it("refuses dates outside today to today + 4, and says when no run is published", async () => {
    for (const text of ["/fixtures yesterday", "/fixtures 2026-10-22"]) {
      expect((await ask(text)).text).toBe(
        "Forecasts are stored for 2026-10-17 to 2026-10-21 (UTC dates). Usage: /fixtures [today|tomorrow|YYYY-MM-DD]",
      );
    }
    expect((await ask("/fixtures 2026-10-21")).text).toContain("No model run is published");
  });
});

describe("predictions: /logged, /results, /pending", () => {
  beforeEach(async () => {
    await seedRun();
    const upload = await seedUpload(1);
    await seedPrediction({ home: 1, away: 2, uploadId: upload });
    await seedPrediction({
      home: 3,
      away: 4,
      uploadId: upload,
      date: "2026-10-16",
      status: "scored",
      goals: [2, 0],
    });
    await seedPrediction({
      home: 5,
      away: 6,
      uploadId: upload,
      date: "2026-10-15",
      status: "void",
      voidReason: "NO_RESULT",
    });
  });

  it("re-shows a day's logged predictions with their status", async () => {
    expect((await ask("/logged")).text).toContain("Status: pending");
    const yesterday = (await ask("/logged yesterday")).text;
    expect(yesterday).toContain("Status: scored 2-0");
    expect(yesterday).toContain("1X2   H 50.0%");
    expect((await ask("/logged 2026-10-01")).text).toBe(
      "Nothing logged for 2026-10-01 (UTC date).",
    );
  });

  it("lists settled predictions newest first, limited by n", async () => {
    const all = (await ask("/results")).text;
    expect(all.indexOf(teamName(3))).toBeLessThan(all.indexOf(teamName(5)));
    expect(all).toContain("void (NO_RESULT)");
    const one = (await ask("/results 1")).text;
    expect(one).toContain(teamName(3));
    expect(one).not.toContain(teamName(5));
  });

  it("lists pending predictions", async () => {
    const text = (await ask("/pending")).text;
    expect(text).toContain("Waiting for a result: 1");
    expect(text).toContain(`${teamName(1)} vs ${teamName(2)}`);
  });
});

describe("/report, /last, /alerts", () => {
  it("shows the newest report, or says none is stored", async () => {
    expect((await ask("/report")).text).toContain("No weekly report stored yet");
    await env.DB.prepare(
      `INSERT INTO calibration_snapshots (created_at, window_from, window_to, n_scored, metrics_json)
       VALUES ('2026-10-19T01:40:00Z', '2026-10-01', '2026-10-18', 12, ?1)`,
    )
      .bind(JSON.stringify({ n_scored: 12, target: 300, n_pending: 2 }))
      .run();
    expect((await ask("/report")).text).toContain("Scored 12 of the 300-match target; pending 2");
  });

  it("shows the last upload", async () => {
    expect((await ask("/last")).text).toBe("No upload has been received yet.");
    await seedUpload(5, { status: "rejected", error_code: "E_SCHEMA_INVALID" });
    expect((await ask("/last")).text).toContain("Error E_SCHEMA_INVALID");
  });

  it("shows the alerts of the last 48 hours", async () => {
    expect((await ask("/alerts")).text).toBe("No alerts in the last 48 hours.");
    await seedEvent("2026-10-17T01:00:00Z", "unmapped_team");
    await seedEvent("2026-10-14T01:00:00Z", "unmapped_team"); // too old
    const text = (await ask("/alerts")).text;
    expect(text).toContain("Alerts in the last 48 hours: 1 (1 waiting for the nightly delivery)");
  });
});

describe("/team", () => {
  beforeEach(async () => {
    await env.DB.prepare(
      `INSERT INTO teams (team_id, canonical_name, home_comp, is_ucl_only, active) VALUES
         (101, 'Atlético Madrid', 'LL', 0, 1), (102, 'Real Madrid', 'LL', 0, 1),
         (103, 'Bodø/Glimt', NULL, 1, 1), (104, 'Old Madrid', 'LL', 0, 0)`,
    ).run();
    await env.DB.prepare(
      "INSERT INTO team_aliases (source, alias_norm, team_id) VALUES ('fd_org', 'club atletico de madrid', 101)",
    ).run();
    await seedRun();
  });

  it("finds a team by its canonical name without accents, by alias, or by a unique part", async () => {
    expect((await ask("/team atletico madrid")).text).toContain("Atlético Madrid (LL, active)");
    expect((await ask("/team Club Atlético de Madrid")).text).toContain(
      "Atlético Madrid (LL, active)",
    );
    expect((await ask("/team bodo")).text).toContain("Bodø/Glimt (UCL only, active)");
  });

  it("lists several matches, prefers active clubs, and does not repeat unknown text", async () => {
    expect((await ask("/team madrid")).text).toBe(
      "Several teams match: Atlético Madrid, Real Madrid. Send /team with the full name.",
    );
    const unknown = await ask("/team <script>Nowhere United</script>");
    expect(unknown.text).toBe(
      "No team by that name in our table. Use the canonical name, for example /team Arsenal.",
    );
    expect(unknown.text).not.toContain("Nowhere");
  });

  it("shows the form row and the next fixture's verdict", async () => {
    await env.DB.prepare(
      `INSERT INTO team_form (run_id, team_id, n_training, n_season, season_gf, season_ga, l10_n,
         l10_gf, l10_ga, latest_match_date) VALUES (?1, 102, 90, 9, 2.2, 0.8, 9, 2.5, 0.7, '2026-10-12')`,
    )
      .bind(RUN_ID)
      .run();
    await seedForecast({ home: 102, away: 101, date: "2026-10-18", comp: "LL", verdict: "DRIFT" });
    const text = (await ask("/team real madrid")).text;
    expect(text).toContain("Goals per match this season: for 2.20, against 0.80");
    expect(text).toContain("Next stored fixture: LL  Real Madrid vs Atlético Madrid");
    expect(text).toContain("DRIFT");
  });
});

describe("matchTeam", () => {
  const teams = [
    { id: 1, name: "Inter Milan", homeComp: "SA", active: true },
    { id: 2, name: "AC Milan", homeComp: "SA", active: true },
    { id: 3, name: "Milan Old", homeComp: "SA", active: false },
  ];

  it("prefers an exact name over a substring, and an alias over a substring", () => {
    expect(matchTeam("ac milan", teams, [])).toEqual({ team: teams[1] });
    expect(matchTeam("inter", teams, [2])).toEqual({ team: teams[1] });
    expect(matchTeam("inter", teams, [])).toEqual({ team: teams[0] });
  });

  it("keeps substrings of at least 3 characters and caps choices at 5", () => {
    expect(matchTeam("ac", teams, [])).toBeNull();
    expect(matchTeam("milan", teams, [])).toEqual({ choices: [teams[0], teams[1]] });
    const many = Array.from({ length: 9 }, (_, i) => ({
      id: i,
      name: `United ${i}`,
      homeComp: "EPL",
      active: true,
    }));
    expect((matchTeam("united", many, []) as { choices: unknown[] }).choices).toHaveLength(5);
    expect(matchTeam("", many, [])).toBeNull();
  });
});
