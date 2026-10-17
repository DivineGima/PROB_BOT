import { describe, expect, it } from "vitest";
import {
  clean,
  formatKickoff,
  type PublishedMatch,
  renderError,
  renderMatch,
  renderOmission,
  renderReply,
  splitBlocks,
} from "../src/format";

const match = (over: Partial<PublishedMatch> = {}): PublishedMatch => ({
  comp: "EPL",
  home: "Arsenal",
  away: "Chelsea",
  kickoffUtc: "2026-10-17T15:00:00Z",
  p1x2: [0.521, 0.243, 0.236],
  overs: [0.97, 0.842, 0.61, 0.364, 0.178, 0.072],
  weights: [
    ["dc", 0.41],
    ["pi", 0.33],
    ["bp", 0.26],
  ],
  alreadyLogged: false,
  ...over,
});

describe("formatKickoff (UTC and IST)", () => {
  it("shows both times", () => {
    expect(formatKickoff("2026-10-17T15:00:00Z")).toBe("17 Oct 15:00 UTC (20:30 IST)");
  });

  it("an IST time on the next calendar day carries +1d (kickoff after 18:30 UTC)", () => {
    expect(formatKickoff("2026-10-17T18:29:00Z")).toBe("17 Oct 18:29 UTC (23:59 IST)");
    expect(formatKickoff("2026-10-17T18:30:00Z")).toBe("17 Oct 18:30 UTC (00:00 IST +1d)");
    expect(formatKickoff("2026-10-17T20:00:00Z")).toBe("17 Oct 20:00 UTC (01:30 IST +1d)");
  });

  it("handles the end of a month and of a year", () => {
    expect(formatKickoff("2026-10-31T19:00:00Z")).toBe("31 Oct 19:00 UTC (00:30 IST +1d)");
    expect(formatKickoff("2026-12-31T23:00:00Z")).toBe("31 Dec 23:00 UTC (04:30 IST +1d)");
  });

  it("does not crash on an unreadable instant", () => {
    expect(formatKickoff("garbage")).toBe("time unknown");
  });
});

describe("renderMatch", () => {
  it("renders the section 8.8 block", () => {
    expect(renderMatch(match())).toBe(
      [
        "EPL  Arsenal vs Chelsea   17 Oct 15:00 UTC (20:30 IST)",
        "1X2   H 52.1%  D 24.3%  A 23.6%",
        "Over  0.5 97.0 | 1.5 84.2 | 2.5 61.0 | 3.5 36.4 | 4.5 17.8 | 5.5 7.2   (Under = 100 - Over)",
        "Models dc+pi+bp   w 0.41/0.33/0.26   Drift: stable (goals only)",
      ].join("\n"),
    );
  });

  it("marks a fixture that was already logged", () => {
    expect(renderMatch(match({ alreadyLogged: true }))).toContain("[already logged]");
  });

  it("shows only the models that contributed", () => {
    const text = renderMatch(match({ weights: [["dc", 1]] }));
    expect(text).toContain("Models dc   w 1.00");
  });

  it("rounded display values stay within 0.15 points of 100 for any distribution", () => {
    let seed = 12345;
    const random = () => {
      seed = (seed * 1664525 + 1013904223) % 4294967296;
      return seed / 4294967296;
    };
    for (let i = 0; i < 2000; i++) {
      const a = random();
      const b = random() * (1 - a);
      const triple: [number, number, number] = [a, b, 1 - a - b];
      const text = renderMatch(match({ p1x2: triple }));
      const shown = [...text.matchAll(/[HDA] (\d+\.\d)%/g)].map((m) => Number(m[1]));
      expect(shown).toHaveLength(3);
      expect(Math.abs(shown.reduce((s, v) => s + v, 0) - 100)).toBeLessThanOrEqual(0.15 + 1e-9);
    }
  });
});

describe("clean (nothing hostile reaches the reply)", () => {
  // Built from code points so the source file itself contains no invisible characters.
  const chars = (...codes: number[]) => String.fromCodePoint(...codes);

  it("strips control characters, direction overrides and separators, and collapses whitespace", () => {
    expect(clean(`a${chars(0)}b${chars(0x202e)}${chars(10)}c${chars(9)} d`)).toBe("a b c d");
    expect(clean(`x${chars(0x200b)}y${chars(0xfeff)}z`)).toBe("x y z");
    expect(clean(`line1${chars(0x2028)}line2${chars(0x2029)}line3`)).toBe("line1 line2 line3");
    expect(clean("  x   y  ")).toBe("x y");
  });

  it("caps the length with an ellipsis", () => {
    expect(clean("z".repeat(100), 10)).toBe(`${"z".repeat(9)}…`);
  });
});

describe("renderOmission and renderError", () => {
  it("names the reason and keeps the note short", () => {
    expect(renderOmission({ comp: "EPL", home: "A", away: "B", reason: "NO_FORECAST" })).toBe(
      "- EPL A vs B: NO_FORECAST, no stored forecast for this fixture",
    );
    const text = renderOmission({
      comp: "EPL",
      home: "A",
      away: "B",
      reason: "DRIFT",
      note: "home: goals_for moved 0.70 vs limit 0.6",
    });
    expect(text).toContain("DRIFT");
    expect(text).toContain("(home: goals_for moved 0.70 vs limit 0.6)");
  });

  it("an error reply carries the catalogue text and at most the given detail lines", () => {
    expect(renderError("E_NO_RUN")).toBe("No usable model run — nothing computed.");
    expect(renderError("E_SCHEMA_INVALID", ["matches.0.home (too_small)"])).toContain(
      "- matches.0.home (too_small)",
    );
  });
});

describe("splitBlocks (3,900 characters, at block boundaries)", () => {
  it("never cuts a block and never exceeds the limit", () => {
    const blocks = Array.from({ length: 40 }, (_, i) => `block ${i}\n${"x".repeat(300)}`);
    const messages = splitBlocks(blocks, 1000);
    expect(messages.length).toBeGreaterThan(1);
    for (const message of messages) expect(message.length).toBeLessThanOrEqual(1000);
    expect(messages.join("\n\n")).toBe(blocks.join("\n\n"));
  });

  it("returns one message when everything fits", () => {
    expect(splitBlocks(["a", "b"])).toEqual(["a\n\nb"]);
  });

  it("truncates a single block that is longer than the limit rather than overflowing", () => {
    const [message] = splitBlocks(["y".repeat(5000)], 3900);
    expect(message?.length).toBe(3900);
  });
});

describe("renderReply", () => {
  const base = {
    runDateUtc: "2026-10-17",
    runId: "R20261017T011700Z",
    dataCutoff: "2026-10-16",
    published: [match()],
    omitted: [],
    excluded: { G2: 4, OTHER: 1 },
    banners: [] as string[],
    hasUcl: false,
  };

  it("has a header, the blocks and one footer with the counts", () => {
    const [text] = renderReply(base);
    expect(text).toContain("Probabilities for 2026-10-17");
    expect(text).toContain("Run R20261017T011700Z (results to 2026-10-16)");
    expect(text).toContain("Published 1; omitted 0; excluded by the screener 5 (G2 4, OTHER 1)");
    expect(text).toContain("Drift: goals only; thresholds are starting values, unvalidated.");
    expect(text).toContain("Probabilities, not advice.");
  });

  it("lists omissions by reason and shows banners and the UCL note", () => {
    const [text] = renderReply({
      ...base,
      omitted: [
        { comp: "EPL", home: "A", away: "B", reason: "NO_FORECAST" },
        { comp: "EPL", home: "C", away: "D", reason: "NO_FORECAST" },
        { comp: "LL", home: "E", away: "F", reason: "DRIFT", note: "home: goals_for moved 0.9" },
      ],
      banners: ["STALE MODELS: the active run is 40 h old (limit 36 h)."],
      hasUcl: true,
    });
    expect(text).toContain("Omitted:");
    expect(text).toContain("omitted 3 (DRIFT 1, NO_FORECAST 2)");
    expect(text).toContain("STALE MODELS");
    expect(text).toContain("the final may be at a neutral ground");
  });

  it("a valid file with nothing published says so", () => {
    const [text] = renderReply({ ...base, published: [], excluded: { G1: 2 } });
    expect(text).toContain("File valid: 0 matches passed the screener (2 excluded: G1 2).");
  });

  it("splits a big reply into several messages and keeps the footer in the last one", () => {
    const many = Array.from({ length: 100 }, (_, i) => match({ home: `Home ${i}` }));
    const messages = renderReply({ ...base, published: many });
    expect(messages.length).toBeGreaterThan(1);
    for (const message of messages) expect(message.length).toBeLessThanOrEqual(3900);
    expect(messages.at(-1)).toContain("Probabilities, not advice.");
    expect(messages[0]).toContain("Probabilities for");
  });

  it("never prints free text it was not given from our tables (hostile names are neutralised)", () => {
    const hostile = `Evil${String.fromCodePoint(0)}FC${String.fromCodePoint(10)}<b>x</b> `.repeat(
      10,
    );
    const [text] = renderReply({
      ...base,
      published: [],
      omitted: [{ comp: "EPL", home: hostile, away: "B", reason: "UNMAPPED_TEAM" }],
    });
    expect(text).not.toContain(String.fromCodePoint(0));
    expect(text).toContain("…");
  });
});
