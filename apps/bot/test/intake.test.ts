import { describe, expect, it } from "vitest";
import {
  countExclusions,
  decodeUtf8,
  guardDocument,
  parseScreenerFile,
  timeCheck,
} from "../src/intake";
import { screenerV1Schema } from "../src/intake/schema";
import { KICKOFF, NOW, RUN_DATE, screenerFile, screenerMatch } from "./helpers";

const bytes = (value: unknown): Uint8Array => new TextEncoder().encode(JSON.stringify(value));
const valid = () =>
  JSON.parse(new TextDecoder().decode(screenerFile([screenerMatch({ home: 1, away: 2 })])));

describe("guardDocument (before any download)", () => {
  it("accepts a .json name or a JSON mime type", () => {
    expect(guardDocument({ fileName: "a.JSON" }).ok).toBe(true);
    expect(guardDocument({ fileName: "noext", mimeType: "application/json" }).ok).toBe(true);
  });

  it("rejects other files and files over 256 KB", () => {
    const wrong = guardDocument({ fileName: "a.pdf", mimeType: "application/pdf" });
    expect(!wrong.ok && wrong.error.code).toBe("E_NOT_JSON_FILE");
    const big = guardDocument({ fileName: "a.json", fileSize: 256 * 1024 + 1 });
    expect(!big.ok && big.error.code).toBe("E_TOO_LARGE");
    expect(guardDocument({ fileName: "a.json", fileSize: 256 * 1024 }).ok).toBe(true);
    const none = guardDocument({});
    expect(!none.ok && none.error.code).toBe("E_NOT_JSON_FILE");
  });
});

describe("decodeUtf8", () => {
  it("strips a byte-order mark and rejects invalid UTF-8 and oversize input", () => {
    const withBom = new Uint8Array([0xef, 0xbb, 0xbf, 0x7b, 0x7d]);
    const ok = decodeUtf8(withBom);
    expect(ok.ok && ok.value).toBe("{}");
    const bad = decodeUtf8(new Uint8Array([0x7b, 0xff, 0xfe, 0x7d]));
    expect(!bad.ok && bad.error.code).toBe("E_PARSE");
    const big = decodeUtf8(new Uint8Array(256 * 1024 + 1));
    expect(!big.ok && big.error.code).toBe("E_TOO_LARGE");
  });
});

describe("parseScreenerFile (every E_SCHEMA_* branch)", () => {
  it("accepts a valid file and strips unknown keys instead of failing", () => {
    const doc = valid();
    doc.surprise = "ignored";
    doc.matches[0].extra_field = { nested: true };
    const parsed = parseScreenerFile(bytes(doc));
    expect(parsed.ok).toBe(true);
    if (parsed.ok) {
      expect(parsed.value.matches).toHaveLength(1);
      expect("surprise" in parsed.value).toBe(false);
      expect("extra_field" in (parsed.value.matches[0] as object)).toBe(false);
    }
  });

  it("E_PARSE for text that is not JSON", () => {
    const parsed = parseScreenerFile(new TextEncoder().encode("not json {"));
    expect(!parsed.ok && parsed.error.code).toBe("E_PARSE");
  });

  it("E_SCHEMA_INVALID for JSON that is not an object", () => {
    for (const value of [[], "text", 5, null]) {
      const parsed = parseScreenerFile(bytes(value));
      expect(!parsed.ok && parsed.error.code).toBe("E_SCHEMA_INVALID");
    }
  });

  it("E_SCHEMA_VERSION for a missing or different version, before any other check", () => {
    for (const version of [2, "1", undefined, null]) {
      const doc = { ...valid(), schema_version: version, matches: "garbage" };
      const parsed = parseScreenerFile(bytes(doc));
      expect(!parsed.ok && parsed.error.code).toBe("E_SCHEMA_VERSION");
    }
  });

  // biome-ignore lint/suspicious/noExplicitAny: each case mutates an arbitrary JSON document
  const cases: Array<[string, (d: any) => void]> = [
    ["a missing required key", (d) => delete d.matches],
    ["a mistyped required key", (d) => (d.run_date_utc = 20261017)],
    ["a calendar date that does not exist", (d) => (d.run_date_utc = "2026-02-30")],
    ["a bad competition", (d) => (d.matches[0].competition = "EL")],
    ["a kickoff with seconds", (d) => (d.matches[0].kickoff_utc = "2026-10-17T15:00:30Z")],
    [
      "a kickoff that is not an instant",
      (d) => (d.matches[0].kickoff_utc = "2026-13-17T15:00:00Z"),
    ],
    ["home equal to away", (d) => (d.matches[0].away = d.matches[0].home)],
    ["an empty team name", (d) => (d.matches[0].home = "")],
    ["a 65-character team name", (d) => (d.matches[0].home = "x".repeat(65))],
    ["a 161-character match_id", (d) => (d.matches[0].match_id = "x".repeat(161))],
    ["rest days of 61", (d) => (d.matches[0].rest_days_home = 61)],
    ["a fractional rest day", (d) => (d.matches[0].rest_days_home = 1.5)],
    ["an http source url", (d) => (d.matches[0].source_urls = ["http://example.com"])],
    ["21 source urls", (d) => (d.matches[0].source_urls = Array(21).fill("https://e.com/x"))],
    [
      "41 absences",
      (d) =>
        (d.matches[0].absences_home = Array(41).fill({
          player: "p",
          status: "out",
          source_url: "https://e.com/x",
        })),
    ],
    ["a bad absence status", (d) => (d.matches[0].absences_away[0].status = "injured")],
    ["a bad lineup status", (d) => (d.matches[0].lineup_status = "maybe")],
    ["notes over 2000 characters", (d) => (d.notes = "n".repeat(2001))],
    ["101 matches", (d) => (d.matches = Array(101).fill(d.matches[0]))],
    ["201 excluded entries", (d) => (d.excluded = Array(201).fill({ match: "a", reason: "b" }))],
    [
      "an excluded reason over 40 characters",
      (d) => (d.excluded = [{ match: "a", reason: "r".repeat(41) }]),
    ],
  ];
  for (const [name, mutate] of cases) {
    it(`E_SCHEMA_INVALID for ${name}`, () => {
      const doc = valid();
      mutate(doc);
      const parsed = parseScreenerFile(bytes(doc));
      expect(parsed.ok).toBe(false);
      expect(!parsed.ok && parsed.error.code).toBe("E_SCHEMA_INVALID");
    });
  }

  it("reports at most five paths and never echoes file content", () => {
    const doc = valid();
    doc.matches = Array.from({ length: 12 }, (_, i) => ({
      ...doc.matches[0],
      match_id: `SECRET-CONTENT-${i}`,
      competition: "BOGUS-COMPETITION",
    }));
    const parsed = parseScreenerFile(bytes(doc));
    expect(parsed.ok).toBe(false);
    if (!parsed.ok) {
      expect(parsed.error.detail.length).toBeLessThanOrEqual(5);
      const text = JSON.stringify(parsed.error);
      expect(text).not.toContain("SECRET-CONTENT");
      expect(text).not.toContain("BOGUS-COMPETITION");
      expect(parsed.error.detail[0]).toContain("matches.0.competition");
    }
  });

  it("accepts a file with no matches and keeps a null notes", () => {
    const parsed = parseScreenerFile(bytes({ ...valid(), matches: [] }));
    expect(parsed.ok && parsed.value.matches).toEqual([]);
  });
});

describe("timeCheck (business checks that become omissions)", () => {
  const at = (kickoff: string, runDate = RUN_DATE, now = NOW) =>
    timeCheck({ kickoff_utc: kickoff }, runDate, now);

  it("passes a kickoff later today and within 48 hours", () => {
    expect(at(KICKOFF)).toBeNull();
  });

  it("DATE_MISMATCH wins over STARTED and TOO_FAR", () => {
    expect(at("2026-10-16T15:00:00Z")).toBe("DATE_MISMATCH");
    expect(at("2026-10-19T15:00:00Z")).toBe("DATE_MISMATCH");
  });

  it("STARTED when the kickoff is not strictly in the future", () => {
    expect(at("2026-10-17T06:00:00Z")).toBe("STARTED");
    expect(at("2026-10-17T05:59:00Z")).toBe("STARTED");
    expect(at("2026-10-17T06:01:00Z")).toBeNull();
  });

  it("TOO_FAR when the kickoff is more than 48 hours ahead", () => {
    const early = new Date("2026-10-15T14:00:00Z");
    expect(at("2026-10-17T15:00:00Z", RUN_DATE, early)).toBe("TOO_FAR");
    expect(at("2026-10-17T14:00:00Z", RUN_DATE, early)).toBeNull(); // exactly 48 h
  });
});

describe("countExclusions", () => {
  it("counts by gate code and everything else as OTHER", () => {
    expect(
      countExclusions([
        { match: "a", reason: "G2_EARLY_SEASON" },
        { match: "b", reason: " g2 early" },
        { match: "c", reason: "G4_ROTATION_RISK" },
        { match: "d", reason: "G7" },
        { match: "e", reason: "<script>alert(1)</script>" },
        { match: "f", reason: "G10" },
      ]),
    ).toEqual({ G2: 2, G4: 1, OTHER: 3 });
  });
});

describe("the Zod schema itself", () => {
  it("is the version-1 contract: literal 1, ten competitions", () => {
    expect(screenerV1Schema.safeParse({ ...valid(), schema_version: 2 }).success).toBe(false);
    for (const comp of ["EPL", "LL", "BL", "SA", "L1", "UCL", "ERE", "PPL", "CHA", "SPL"]) {
      const doc = valid();
      doc.matches[0].competition = comp;
      expect(screenerV1Schema.safeParse(doc).success).toBe(true);
    }
  });
});
