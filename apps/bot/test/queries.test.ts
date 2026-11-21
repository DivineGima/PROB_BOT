import { env } from "cloudflare:workers";
import { beforeEach, describe, expect, it } from "vitest";
import { createRepositories } from "../src/repo";
import {
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
} from "./helpers";

/** Read-only queries of the bot commands (architecture 3, sections 6.5 and 6.10; essentials 3 step 2). */

const q = () => createRepositories(env.DB).queries;
const SINCE = "2026-10-16T06:00:00Z";

beforeEach(async () => {
  await resetWorld();
  await seedReference();
});

describe("statusSnapshot", () => {
  it("reads nothing but empty values when no run is published", async () => {
    const s = await q().statusSnapshot(["2026-10-17"], SINCE, SINCE);
    expect(s).toEqual({
      run: null,
      jobs: [],
      alertsWaiting: 0,
      alertPath: [],
      coverage: [{ date: "2026-10-17", scheduled: 0, forecasts: 0 }],
    });
  });

  it("summarises the run without payloads, the newest nightly step of each kind and coverage", async () => {
    await seedRun();
    await seedModelParams("dc", "ok");
    await seedModelParams("pi", "failed");
    await seedJob("fit", "failed", "2026-10-16T01:20:00Z");
    await seedJob("fit", "ok", "2026-10-17T01:20:00Z", "2026-10-17T01:25:00Z");
    await seedJob("ingest", "ok", "2026-10-17T01:17:00Z", "2026-10-17T01:19:00Z");
    await seedJob("backtest", "ok", "2026-10-17T03:00:00Z");
    await seedScheduledMatch("2026-10-17", 1, 2);
    await seedScheduledMatch("2026-10-17", 3, 4);
    await seedForecast({ home: 1, away: 2 });

    const s = await q().statusSnapshot(["2026-10-17", "2026-10-18"], SINCE, SINCE);
    expect(s.run?.runId).toBe(RUN_ID);
    expect(s.run?.models).toEqual([
      { model: "dc", status: "ok" },
      { model: "pi", status: "failed" },
    ]);
    expect(JSON.stringify(s.run)).not.toContain("payload");
    expect(s.jobs.map((j) => [j.kind, j.status])).toEqual([
      ["ingest", "ok"],
      ["fit", "ok"],
    ]);
    expect(s.coverage).toEqual([
      { date: "2026-10-17", scheduled: 2, forecasts: 1 },
      { date: "2026-10-18", scheduled: 0, forecasts: 0 },
    ]);
  });

  it("counts undelivered flush alerts and alert-path problems inside their windows", async () => {
    await seedEvent("2026-10-17T01:00:00Z", "promotion_rejected", { level: "alert" });
    await seedEvent("2026-10-17T01:00:00Z", "unmapped_team");
    await seedEvent("2026-10-17T01:00:00Z", "anomaly_status_regression");
    await seedEvent("2026-10-17T01:00:00Z", "anomalyx"); // not an anomaly kind: the _ is literal
    await seedEvent("2026-10-17T01:00:00Z", "unmapped_team", {
      deliveredAt: "2026-10-17T01:40:00Z",
    });
    await seedEvent("2026-10-15T01:00:00Z", "unmapped_team"); // outside the window
    await seedEvent("2026-10-17T02:00:00Z", "alert_send_failed", { level: "error" });
    await seedEvent("2026-10-17T03:00:00Z", "alert_send_failed", { level: "error" });
    await seedEvent("2026-10-17T03:00:00Z", "ignored_update", { level: "info" });

    const s = await q().statusSnapshot([], SINCE, SINCE);
    expect(s.alertsWaiting).toBe(3);
    expect(s.alertPath).toEqual([
      { kind: "alert_send_failed", n: 2, last: "2026-10-17T03:00:00Z" },
    ]);
  });
});

describe("alertEvents", () => {
  it("lists flush alerts and the watchdog's sent findings, newest first, with their state", async () => {
    await seedEvent("2026-10-17T01:00:00Z", "unmapped_team");
    await seedEvent("2026-10-17T02:00:00Z", "anomaly_score_change", {
      deliveredAt: "2026-10-17T02:05:00Z",
    });
    await seedEvent("2026-10-17T03:00:00Z", "watchdog_stale_run", {
      level: "error",
      source: "watchdog",
    });
    await seedEvent("2026-10-17T04:00:00Z", "watchdog_failed", {
      level: "error",
      source: "watchdog",
    });
    await seedEvent("2026-10-17T04:00:00Z", "reply_failed", { level: "warn", source: "bot" });

    const read = await q().alertEvents(SINCE, 20);
    expect(read.rows).toEqual([
      { at: "2026-10-17T03:00:00Z", kind: "watchdog_stale_run", state: "watchdog" },
      { at: "2026-10-17T02:00:00Z", kind: "anomaly_score_change", state: "delivered" },
      { at: "2026-10-17T01:00:00Z", kind: "unmapped_team", state: "waiting" },
    ]);
    expect(read.total).toBe(3);
    expect(read.waiting).toBe(1);
  });

  it("limits the rows but counts every alert, by kind", async () => {
    for (let h = 0; h < 5; h++) await seedEvent(`2026-10-17T0${h}:00:00Z`, "unmapped_team");
    await seedEvent("2026-10-17T06:00:00Z", "promotion_rejected", { level: "alert" });
    const read = await q().alertEvents(SINCE, 2);
    expect(read.rows).toHaveLength(2);
    expect(read.total).toBe(6);
    expect(read.byKind).toEqual([
      { kind: "unmapped_team", n: 5 },
      { kind: "promotion_rejected", n: 1 },
    ]);
  });
});

describe("forecastVerdicts", () => {
  it("is null without an active run", async () => {
    expect(await q().forecastVerdicts("2026-10-17")).toBeNull();
  });

  it("reads the active run's verdicts with names, and never a probability", async () => {
    await seedRun();
    await seedForecast({ home: 1, away: 2, pHome: 0.61 });
    await seedForecast({ home: 3, away: 4, verdict: "DRIFT" });
    await seedForecast({ home: 5, away: 6, date: "2026-10-18" });
    await seedRun({ runId: "R20261016T011700Z", status: "superseded" });
    await seedForecast({ home: 7, away: 8 }, "R20261016T011700Z");
    await seedScheduledMatch("2026-10-17", 1, 2); // has a forecast
    await seedScheduledMatch("2026-10-17", 9, 10); // has none: an upload would say NO_FORECAST

    const read = await q().forecastVerdicts("2026-10-17");
    expect(read?.runId).toBe(RUN_ID);
    expect(read?.unforecast).toBe(1);
    expect(read?.rows.map((r) => [r.home, r.away, r.verdict])).toEqual([
      [teamName(1), teamName(2), "ok"],
      [teamName(3), teamName(4), "DRIFT"],
    ]);
    for (const row of read?.rows ?? []) {
      expect(Object.keys(row).sort()).toEqual([
        "away",
        "compCode",
        "detailJson",
        "home",
        "kickoffUtc",
        "verdict",
      ]);
    }
    expect(JSON.stringify(read)).not.toContain("0.61");
  });
});

describe("predictions", () => {
  beforeEach(async () => {
    await seedRun();
  });

  it("reads a date's logged predictions with names, result and logging time", async () => {
    const upload = await seedUpload(1);
    await seedPrediction({ home: 1, away: 2, uploadId: upload, pHome: 0.6 });
    await seedPrediction({ home: 3, away: 4, uploadId: upload, status: "scored", goals: [0, 0] });
    await seedPrediction({ home: 5, away: 6, uploadId: upload, date: "2026-10-18" });

    const rows = await q().loggedForDate("2026-10-17");
    expect(rows.map((r) => [r.home, r.status, r.goals])).toEqual([
      [teamName(1), "pending", null],
      [teamName(3), "scored", [0, 0]],
    ]);
    expect(rows[0]?.p1x2[0]).toBeCloseTo(0.6, 12);
    expect(rows[0]?.overs).toHaveLength(6);
    expect(rows[0]?.createdAt).toBe("2026-10-17T06:00:05Z");
  });

  it("lists settled predictions newest kickoff first, and pending ones soonest first", async () => {
    const upload = await seedUpload(1);
    await seedPrediction({
      home: 1,
      away: 2,
      uploadId: upload,
      date: "2026-10-10",
      status: "scored",
    });
    await seedPrediction({
      home: 3,
      away: 4,
      uploadId: upload,
      date: "2026-10-12",
      status: "void",
    });
    await seedPrediction({ home: 5, away: 6, uploadId: upload, date: "2026-10-20" });
    await seedPrediction({ home: 7, away: 8, uploadId: upload, date: "2026-10-19" });

    const settled = await q().settled(10);
    expect(settled.map((r) => [r.matchDate, r.status, r.voidReason])).toEqual([
      ["2026-10-12", "void", "POSTPONED"],
      ["2026-10-10", "scored", null],
    ]);
    expect(settled[1]?.rps1x2).toBeCloseTo(0.1875, 12);
    expect(await q().settled(1)).toHaveLength(1);

    const pending = await q().pending(1);
    expect(pending.total).toBe(2);
    expect(pending.rows.map((r) => r.home)).toEqual([teamName(7)]);
  });
});

describe("snapshot and upload", () => {
  it("returns null when there is none", async () => {
    expect(await q().latestSnapshot()).toBeNull();
    expect(await q().latestUpload()).toBeNull();
  });

  it("returns the newest one", async () => {
    for (const [created, n] of [
      ["2026-10-12T02:00:00Z", 10],
      ["2026-10-19T02:00:00Z", 25],
    ] as const) {
      await env.DB.prepare(
        `INSERT INTO calibration_snapshots (created_at, window_from, window_to, n_scored, metrics_json)
         VALUES (?1, '2026-10-01', '2026-10-18', ?2, '{"n_scored": 1}')`,
      )
        .bind(created, n)
        .run();
    }
    expect((await q().latestSnapshot())?.nScored).toBe(25);

    await seedUpload(1, { status: "rejected", error_code: "E_PARSE" });
    await seedUpload(2, { status: "processed", n_published: 3, run_date_utc: "2026-10-17" });
    const last = await q().latestUpload();
    expect(last).toMatchObject({ status: "processed", nPublished: 3, errorCode: null });
  });
});

describe("teams", () => {
  it("returns every team and the alias hits for a normalised spelling", async () => {
    await env.DB.prepare(
      "INSERT INTO team_aliases (source, alias_norm, team_id) VALUES ('fd_org', 'club five', 5), ('manual', 'club five', 5)",
    ).run();
    const c = await q().teamCandidates("club five");
    expect(c.teams).toHaveLength(40);
    expect(c.teams[0]).toEqual({ id: 1, name: teamName(1), homeComp: "EPL", active: true });
    expect(c.aliasTeamIds).toEqual([5]);
    expect((await q().teamCandidates("nobody")).aliasTeamIds).toEqual([]);
  });

  it("reads the active run's form and the next stored fixture from a date", async () => {
    expect(await q().teamForm(1, "2026-10-17")).toBeNull();
    await seedRun();
    await env.DB.prepare(
      `INSERT INTO team_form (run_id, team_id, n_training, n_season, season_gf, season_ga, l10_n,
         l10_gf, l10_ga, latest_match_date)
       VALUES (?1, 1, 80, 9, 1.8, 0.9, 9, 2.1, 1.0, '2026-10-12')`,
    )
      .bind(RUN_ID)
      .run();
    await seedForecast({ home: 2, away: 1, date: "2026-10-16" }); // before the date
    await seedForecast({ home: 1, away: 3, date: "2026-10-19", verdict: "DRIFT" });
    await seedForecast({ home: 4, away: 1, date: "2026-10-18" });

    const read = await q().teamForm(1, "2026-10-17");
    expect(read?.form).toMatchObject({ nTraining: 80, nSeason: 9, l10N: 9, seasonGf: 1.8 });
    expect(read?.nextFixture).toMatchObject({
      matchDate: "2026-10-18",
      home: teamName(4),
      away: teamName(1),
      verdict: "ok",
    });
    expect((await q().teamForm(2, "2026-10-17"))?.form).toBeNull();
  });
});
