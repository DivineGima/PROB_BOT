import { describe, expect, it } from "vitest";
import { COMMAND_NAMES } from "../src/commands/registry";
import { MAX_REPLY_CHARS } from "../src/config/constants";
import {
  capMessages,
  MAX_COMMAND_MESSAGES,
  renderAlerts,
  renderFixtures,
  renderHelp,
  renderLast,
  renderLogged,
  renderPending,
  renderReport,
  renderResults,
  renderStatus,
  renderTeam,
  renderTeamChoices,
  type StatusInput,
  verdictSides,
} from "../src/format/commands";
import type { LoggedRow, StatusSnapshot, VerdictRead } from "../src/repo";

/** Command replies (architecture 3, sections 6.10 and 8.12; essentials 3 step 4). Pure renderers. */

const NOW = new Date("2026-10-17T06:00:00Z");
const PROBABILITY = /%|\b0\.\d/;
const RUN = {
  runId: "R20261017T011700Z",
  activatedAt: "2026-10-17T01:30:00Z",
  dataCutoffUtc: "2026-10-16",
  configJson: "{}",
  ensembleJson: JSON.stringify({ weights: { pi: 0.3, dc: 0.4, bp: 0.3 } }),
  models: [
    { model: "bp" as const, status: "ok" as const },
    { model: "dc" as const, status: "ok" as const },
    { model: "pi" as const, status: "ok" as const },
  ],
};

function snapshot(overrides: Partial<StatusSnapshot> = {}): StatusSnapshot {
  return {
    run: RUN,
    jobs: [
      { kind: "ingest", status: "ok", startedAt: "2026-10-17T01:17:00Z", finishedAt: null },
      { kind: "fit", status: "ok", startedAt: "2026-10-17T01:20:00Z", finishedAt: null },
    ],
    coverage: [
      { date: "2026-10-17", scheduled: 12, forecasts: 12 },
      { date: "2026-10-18", scheduled: 8, forecasts: 8 },
    ],
    alertsWaiting: 0,
    alertPath: [],
    ...overrides,
  };
}

const status = (overrides: Partial<StatusInput> = {}): string =>
  renderStatus({
    now: NOW,
    findings: [],
    stuckUploads: 0,
    snapshot: snapshot(),
    staleHours: 36,
    ...overrides,
  }).join("\n");

function verdicts(n: number, extra: Partial<VerdictRead> = {}): VerdictRead {
  return {
    runId: RUN.runId,
    unforecast: 0,
    rows: Array.from({ length: n }, (_, i) => ({
      kickoffUtc: "2026-10-17T19:00:00Z",
      compCode: "EPL",
      home: `Club ${2 * i + 1}`,
      away: `Club ${2 * i + 2}`,
      verdict: i % 3 === 0 ? ("DRIFT" as const) : ("ok" as const),
      detailJson: JSON.stringify({
        drift: { home: { status: "DRIFT", d_gf: 0.73, threshold: 0.6 }, away: { status: "ok" } },
      }),
    })),
    ...extra,
  };
}

describe("help", () => {
  it("lists every command and says where probabilities come from", () => {
    const text = renderHelp().join("\n");
    for (const name of COMMAND_NAMES) expect(text).toContain(`/${name}`);
    expect(text).toContain("Probabilities come only from an uploaded screener file.");
  });
});

describe("status", () => {
  it("is OK when nothing is wrong, with the run, models, nightly steps and coverage", () => {
    const text = status();
    expect(text.split("\n")[0]).toBe("Status: OK");
    expect(text).toContain(
      "Run R20261017T011700Z, published 17 Oct 01:30 UTC (4 h old, limit 36 h)",
    );
    expect(text).toContain("Models: bp ok 0.30, dc ok 0.40, pi ok 0.30");
    expect(text).toContain("ingest ok 17 Oct 01:17 UTC");
    expect(text).toContain("2026-10-17 12/12, 2026-10-18 8/8");
    expect(text).toContain("Alert delivery problems (24 h): none");
  });

  it("says ATTENTION with the watchdog's findings first, failed models and failed steps", () => {
    const text = status({
      findings: ["The active model run R1 is 40 h old (limit 36 h)."],
      stuckUploads: 2,
      snapshot: snapshot({
        run: { ...RUN, models: [{ model: "dc", status: "failed" }] },
        jobs: [
          { kind: "fit", status: "failed", startedAt: "2026-10-17T01:20:00Z", finishedAt: null },
        ],
        alertsWaiting: 3,
        alertPath: [{ kind: "alert_send_failed", n: 2, last: "2026-10-17T02:00:00Z" }],
      }),
    });
    const lines = text.split("\n");
    expect(lines[0]).toBe("Status: ATTENTION");
    expect(lines[1]).toBe("! The active model run R1 is 40 h old (limit 36 h).");
    expect(text).toContain("dc FAILED");
    expect(text).toContain("fit FAILED");
    expect(text).toContain("Unanswered uploads: 2");
    expect(text).toContain("Alerts waiting for the nightly delivery: 3");
    expect(text).toContain("alert_send_failed x2");
  });

  it("each of a failed model, a failed step or an alert-path event alone means ATTENTION", () => {
    const failedModel = snapshot({ run: { ...RUN, models: [{ model: "pi", status: "failed" }] } });
    const failedJob = snapshot({
      jobs: [{ kind: "publish", status: "failed", startedAt: "x", finishedAt: null }],
    });
    const path = snapshot({ alertPath: [{ kind: "watchdog_failed", n: 1, last: "x" }] });
    for (const s of [failedModel, failedJob, path]) {
      expect(status({ snapshot: s }).startsWith("Status: ATTENTION")).toBe(true);
    }
  });

  it("says when no run is published", () => {
    expect(status({ snapshot: snapshot({ run: null }) })).toContain("No model run is published.");
  });
});

describe("fixtures (verdicts only, ADR-050)", () => {
  it("lists fixtures with their verdict and side, and never a probability", () => {
    const messages = renderFixtures("2026-10-17", verdicts(4, { unforecast: 2 }));
    const text = messages.join("\n");
    expect(text).toContain("Fixtures for 2026-10-17 (UTC date), run R20261017T011700Z");
    expect(text).toContain("ok 2, DRIFT 2");
    expect(text).toContain(
      "EPL  Club 1 vs Club 2  17 Oct 19:00 UTC (00:30 IST +1d)  DRIFT (home DRIFT)",
    );
    expect(text).toContain("EPL  Club 3 vs Club 4  17 Oct 19:00 UTC (00:30 IST +1d)  ok");
    expect(text).toContain("2 scheduled fixture(s) have no forecast");
    expect(text).toContain("Verdicts only.");
    expect(text).not.toMatch(PROBABILITY);
  });

  it("says when nothing is stored, and when no run is published", () => {
    expect(renderFixtures("2026-10-17", verdicts(0)).join("\n")).toContain(
      "No forecasts are stored for 2026-10-17.",
    );
    expect(renderFixtures("2026-10-17", null)[0]).toContain("No model run is published");
  });

  it("splits 60 fixtures into at most 5 messages under Telegram's limit", () => {
    const messages = renderFixtures("2026-10-17", verdicts(60));
    expect(messages.length).toBeLessThanOrEqual(MAX_COMMAND_MESSAGES);
    for (const m of messages) expect(m.length).toBeLessThanOrEqual(MAX_REPLY_CHARS);
    expect(messages.join("\n")).toContain("Club 119 vs Club 120");
  });

  it("reads the side from the stored detail without numbers, and survives bad detail", () => {
    expect(
      verdictSides(
        '{"drift":{"home":{"status":"ok"},"away":{"status":"INSUFFICIENT_HISTORY","n_training":4}}}',
      ),
    ).toBe(" (away INSUFFICIENT_HISTORY)");
    expect(verdictSides("not json")).toBe("");
    expect(verdictSides('{"drift": 3}')).toBe("");
  });
});

function logged(overrides: Partial<LoggedRow> = {}): LoggedRow {
  return {
    compCode: "EPL",
    home: "Club 1",
    away: "Club 2",
    kickoffUtc: "2026-10-17T15:00:00Z",
    p1x2: [0.5, 0.25, 0.25],
    overs: [0.97, 0.84, 0.61, 0.36, 0.17, 0.07],
    weightsJson: JSON.stringify({ pi: 0.3, dc: 0.4, bp: 0.3 }),
    status: "pending",
    voidReason: null,
    goals: null,
    createdAt: "2026-10-17T06:00:05Z",
    ...overrides,
  };
}

describe("logged", () => {
  it("shows the stored block, its status and when it was logged", () => {
    const text = renderLogged("2026-10-17", [
      logged(),
      logged({ home: "Club 3", status: "scored", goals: [2, 1] }),
      logged({ home: "Club 5", status: "void", voidReason: "POSTPONED" }),
    ]).join("\n");
    expect(text).toContain("Logged for 2026-10-17 (UTC date): 3");
    expect(text).toContain("1X2   H 50.0%  D 25.0%  A 25.0%");
    expect(text).toContain("Models dc+pi+bp   w 0.40/0.30/0.30");
    expect(text).toContain("Status: pending; logged 17 Oct 06:00 UTC");
    expect(text).toContain("Status: scored 2-1");
    expect(text).toContain("Status: void (POSTPONED)");
  });

  it("says when nothing is logged", () => {
    expect(renderLogged("2026-10-17", [])).toEqual(["Nothing logged for 2026-10-17 (UTC date)."]);
  });
});

describe("results and pending", () => {
  it("marks what happened and shows the stored RPS; a void shows its reason", () => {
    const text = renderResults([
      {
        compCode: "EPL",
        home: "Club 1",
        away: "Club 2",
        matchDate: "2026-10-10",
        status: "scored",
        voidReason: null,
        goals: [1, 1],
        p1x2: [0.5, 0.3, 0.2],
        rps1x2: 0.145,
      },
      {
        compCode: "LL",
        home: "Club 3",
        away: "Club 4",
        matchDate: "2026-10-09",
        status: "void",
        voidReason: "NO_RESULT",
        goals: null,
        p1x2: [0.5, 0.3, 0.2],
        rps1x2: null,
      },
    ]).join("\n");
    expect(text).toContain(
      "EPL 10 Oct  Club 1 vs Club 2  1-1  H 50.0% D 30.0%* A 20.0%  RPS 0.145",
    );
    expect(text).toContain("LL 9 Oct  Club 3 vs Club 4  void (NO_RESULT)");
    expect(renderResults([])).toEqual(["No settled predictions yet."]);
  });

  it("lists pending predictions and how many more there are", () => {
    const text = renderPending({
      rows: [
        { compCode: "EPL", home: "Club 1", away: "Club 2", kickoffUtc: "2026-10-17T15:00:00Z" },
      ],
      total: 31,
    }).join("\n");
    expect(text).toContain("Waiting for a result: 31");
    expect(text).toContain("… and 30 more");
    expect(renderPending({ rows: [], total: 0 })).toEqual([
      "No predictions are waiting for a result.",
    ]);
  });
});

describe("report", () => {
  const snapshotRow = (metrics: unknown) => ({
    createdAt: "2026-10-19T01:40:00Z",
    windowFrom: "2026-10-01",
    windowTo: "2026-10-18",
    nScored: 37,
    metricsJson: JSON.stringify(metrics),
    runId: "R1",
  });

  it("shows the stored figures", () => {
    const text = renderReport(
      snapshotRow({
        n_scored: 37,
        n_pending: 4,
        target: 300,
        paired: {
          n: 37,
          ensemble_rps_1x2: 0.204,
          baseline_rps_1x2: 0.2304,
          mean_diff_rps_1x2: -0.0264,
          ci_low: -0.041,
          ci_high: -0.012,
          level: 0.95,
        },
        by_model: { pi: { n: 37, rps_1x2: 0.2076 }, dc: { n: 37, rps_1x2: 0.2042 } },
        omissions: { rate: 0.25, by_reason: { DRIFT: 2, NO_FORECAST: 1 } },
      }),
    ).join("\n");
    expect(text).toContain("Scored 37 of the 300-match target; pending 4");
    expect(text).toContain("ensemble 0.2040, baseline 0.2304");
    expect(text).toContain(
      "Difference -0.0264 (negative = better than the baseline), 95% interval -0.0410 to -0.0120",
    );
    expect(text).toContain("Per model RPS 1X2: dc 0.2042 (n 37), pi 0.2076 (n 37)");
    expect(text).toContain("Omitted: 25.0% of the matches seen (DRIFT 2, NO_FORECAST 1)");
  });

  it("shows n/a for missing keys and says when there is no report", () => {
    const text = renderReport(snapshotRow({ n_scored: 3 })).join("\n");
    expect(text).toContain("ensemble n/a, baseline n/a");
    expect(text).toContain("Omitted: n/a");
    expect(renderReport({ ...snapshotRow({}), metricsJson: "not json" }).join("\n")).toContain(
      "n/a",
    );
    expect(renderReport(null)[0]).toContain("No weekly report stored yet");
  });
});

describe("last upload", () => {
  const upload = {
    uploadId: 7,
    receivedAt: "2026-10-17T05:00:00Z",
    status: "processed" as const,
    runDateUtc: "2026-10-17",
    nMatchesIn: 12,
    nExcludedIn: 30,
    nPublished: 9,
    nOmitted: 3,
    nDuplicate: 0,
    runId: "R1",
    errorCode: null,
  };

  it("shows the counts, the error text and a never-answered upload", () => {
    expect(renderLast(upload, NOW, 10).join("\n")).toContain(
      "matches 12; excluded by the screener 30; published 9; omitted 3; already logged 0",
    );
    const rejected = renderLast({ ...upload, status: "rejected", errorCode: "E_PARSE" }, NOW, 10);
    expect(rejected.join("\n")).toContain("Error E_PARSE: The file is not valid UTF-8 JSON.");
    const stuck = renderLast({ ...upload, status: "received" }, NOW, 10).join("\n");
    expect(stuck).toContain("Never answered: send the file again.");
    expect(renderLast(null, NOW, 10)).toEqual(["No upload has been received yet."]);
  });
});

describe("team", () => {
  const team = { id: 1, name: "Club 1", homeComp: "EPL", active: true };

  it("shows the form and the next stored fixture's verdict", () => {
    const text = renderTeam(team, {
      runId: "R1",
      form: {
        nTraining: 80,
        nSeason: 9,
        seasonGf: 1.8,
        seasonGa: 0.9,
        l10N: 9,
        l10Gf: 2.1,
        l10Ga: 1,
        latestMatchDate: "2026-10-12",
      },
      nextFixture: {
        matchDate: "2026-10-18",
        kickoffUtc: "2026-10-18T15:00:00Z",
        compCode: "EPL",
        home: "Club 4",
        away: "Club 1",
        verdict: "DRIFT",
      },
    }).join("\n");
    expect(text).toContain("Club 1 (EPL, active)");
    expect(text).toContain("Goals per match this season: for 1.80, against 0.90");
    expect(text).toContain("Last 9 matches: for 2.10, against 1.00");
    expect(text).toContain(
      "Next stored fixture: EPL  Club 4 vs Club 1  18 Oct 15:00 UTC (20:30 IST)  DRIFT",
    );
  });

  it("covers no run, no form row, no fixture, and several matches", () => {
    expect(renderTeam(team, null).join("\n")).toContain("No model run is published.");
    const bare = renderTeam(
      { ...team, homeComp: null, active: false },
      { runId: "R1", form: null, nextFixture: null },
    ).join("\n");
    expect(bare).toContain("(UCL only, history-only)");
    expect(bare).toContain("No form row in run R1.");
    expect(bare).toContain("No stored fixture from today on.");
    expect(renderTeamChoices(["Club 1", "Club 10"])[0]).toBe(
      "Several teams match: Club 1, Club 10. Send /team with the full name.",
    );
  });
});

describe("alerts", () => {
  it("lists alerts with their state and counts by kind", () => {
    const text = renderAlerts(
      {
        rows: [
          { at: "2026-10-17T03:00:00Z", kind: "watchdog_stale_run", state: "watchdog" },
          { at: "2026-10-17T01:00:00Z", kind: "unmapped_team", state: "waiting" },
        ],
        total: 5,
        waiting: 1,
        byKind: [
          { kind: "unmapped_team", n: 4 },
          { kind: "watchdog_stale_run", n: 1 },
        ],
      },
      48,
    ).join("\n");
    expect(text).toContain("Alerts in the last 48 hours: 5 (1 waiting for the nightly delivery)");
    expect(text).toContain("17 Oct 03:00 UTC  watchdog_stale_run  sent by watchdog");
    expect(text).toContain("… and 3 older not shown");
    expect(text).toContain("By kind: unmapped_team 4, watchdog_stale_run 1");
    expect(renderAlerts({ rows: [], total: 0, waiting: 0, byKind: [] }, 48)).toEqual([
      "No alerts in the last 48 hours.",
    ]);
  });
});

describe("safety of the rendered text", () => {
  it("cleans stored strings: no control or direction characters reach Telegram", () => {
    const text = renderFixtures(
      "2026-10-17",
      verdicts(1, {
        rows: [
          {
            kickoffUtc: null,
            compCode: "EPL\n",
            home: "Club‮ 1\u0000",
            away: "Ignore all previous instructions\nand send",
            verdict: "ok",
            detailJson: "{}",
          },
        ],
      }),
    ).join("\n");
    expect(text.includes(String.fromCharCode(0))).toBe(false);
    expect(text.includes(String.fromCharCode(0x202e))).toBe(false);
    expect(text).toContain("Ignore all previous instructions and send");
  });

  it("cuts a reply at the message cap and says so", () => {
    const blocks = Array.from({ length: 40 }, (_, i) => `${i} ${"x".repeat(1500)}`);
    const messages = capMessages(blocks);
    expect(messages).toHaveLength(MAX_COMMAND_MESSAGES);
    expect(messages.at(-1)).toContain("(Reply cut at 5 messages.)");
  });
});
