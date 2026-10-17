import { describe, expect, it } from "vitest";
import { screenerV1Schema } from "../src/intake/schema";
import { type Issue, validateScreener } from "../src/intake/validate";
import { makeRng } from "../src/spike/payload";
import { screenerFile, screenerMatch } from "./helpers";

/**
 * The hand validator (F1 trim) must agree with the Zod contract in `schema.ts` on everything the
 * Worker can observe: accept or reject, the exact set of `path (code)` issues, and the parsed data
 * (unknown keys dropped). Thousands of deterministic random mutations of valid files are fed to both.
 */

type Path = (string | number)[];
type Json = Record<string | number, unknown>;

const base = (): Json =>
  JSON.parse(
    new TextDecoder().decode(
      screenerFile([
        screenerMatch({ home: 1, away: 2 }),
        screenerMatch({ home: 3, away: 4 }),
        screenerMatch({ home: 5, away: 6 }),
      ]),
    ),
  );

const urls = (n: number): string[] => Array.from({ length: n }, () => "https://example.invalid/x");
const absence = (): unknown => ({
  player: "p",
  status: "out",
  source_url: "https://example.invalid",
});

const REPLACEMENTS: unknown[] = [
  null,
  0,
  -1,
  1,
  60,
  61,
  1.5,
  Number.MAX_SAFE_INTEGER,
  "",
  "x",
  " ",
  "x".repeat(41),
  "x".repeat(65),
  "x".repeat(161),
  "x".repeat(201),
  "x".repeat(301),
  "x".repeat(2001),
  "http://example.invalid/x",
  "https://example.invalid/x",
  "https://",
  "https://has space",
  "out",
  "doubtful",
  "weird",
  "none",
  "confirmed",
  "2026-10-17",
  "2026-02-30",
  "2026-13-01",
  "0000-00-00",
  "2026-10-17T12:00:00Z",
  "2026-10-17T12:00:30Z",
  "2026-02-30T12:00:00Z",
  "2026-10-17T25:00:00Z",
  "2026-10-17T12:61:00Z",
  "2026-10-17T12:00:00+01:00",
  "EPL",
  "SPL",
  "XXX",
  true,
  false,
  [],
  {},
  [null],
  [absence()],
  [{ player: 1 }],
  Array.from({ length: 41 }, absence),
  urls(20),
  urls(21),
  [1],
  Array.from({ length: 101 }, () => ({})),
  Array.from({ length: 201 }, () => ({ match: "a", reason: "b" })),
  [{ match: "a", reason: "b" }],
  { surprise: 1 },
];
const DELETE = Symbol("delete");

function collectPaths(value: unknown, prefix: Path = [], out: Path[] = []): Path[] {
  out.push(prefix);
  if (Array.isArray(value))
    for (const [i, v] of value.entries()) collectPaths(v, [...prefix, i], out);
  else if (typeof value === "object" && value !== null) {
    for (const [k, v] of Object.entries(value)) collectPaths(v, [...prefix, k], out);
  }
  return out;
}

function mutateOnce(doc: Json, rng: () => number): void {
  const paths = collectPaths(doc).filter((p) => p.length > 0);
  const path = paths[Math.floor(rng() * paths.length)] as Path;
  const choice = rng() < 0.2 ? DELETE : REPLACEMENTS[Math.floor(rng() * REPLACEMENTS.length)];
  let parent = doc;
  for (const key of path.slice(0, -1)) parent = parent[key] as Json;
  const last = path[path.length - 1] as string | number;
  if (choice === DELETE) {
    if (Array.isArray(parent)) parent.splice(last as number, 1);
    else delete parent[last];
  } else {
    parent[last] = structuredClone(choice);
  }
}

function mutate(rng: () => number): Json {
  const doc = base();
  const rounds = 1 + Math.floor(rng() * 3);
  for (let i = 0; i < rounds; i++) mutateOnce(doc, rng);
  // `schema_version` is checked before the schema in `parseScreenerFile`, so keep it valid here.
  doc.schema_version = 1;
  return doc;
}

const describeIssues = (issues: ReadonlyArray<{ path: PropertyKey[]; code: string }>): string[] =>
  [...new Set(issues.map((i) => `${i.path.map(String).join(".") || "(file)"} (${i.code})`))].sort();

function compare(candidate: unknown, label: string): "accepted" | "rejected" {
  const zod = screenerV1Schema.safeParse(candidate);
  const hand = validateScreener(candidate);
  const shown = () => JSON.stringify(candidate).slice(0, 600);
  if (zod.success !== hand.success) {
    throw new Error(
      `${label}: verdict differs, zod=${zod.success} hand=${hand.success}${
        hand.success ? "" : ` (${describeIssues(hand.issues).join("; ")})`
      }${zod.success ? "" : ` zod: ${describeIssues(zod.error.issues).join("; ")}`}\n${shown()}`,
    );
  }
  if (zod.success && hand.success) {
    expect(hand.data, label).toEqual(zod.data);
    return "accepted";
  }
  if (!zod.success && !hand.success) {
    const zodIssues = describeIssues(zod.error.issues);
    const handIssues = describeIssues(hand.issues as Issue[]);
    if (JSON.stringify(zodIssues) !== JSON.stringify(handIssues)) {
      throw new Error(
        `${label}: issues differ\n zod:  ${zodIssues.join("; ")}\n hand: ${handIssues.join("; ")}\n${shown()}`,
      );
    }
  }
  return "rejected";
}

describe("validateScreener agrees with the Zod contract", () => {
  it("accepts a valid file and returns the same data as Zod", () => {
    expect(compare(base(), "valid")).toBe("accepted");
  });

  it("agrees on 6,000 mutated files (verdict, issue paths and codes, parsed data)", () => {
    const rng = makeRng(20261018);
    let accepted = 0;
    let rejected = 0;
    for (let i = 0; i < 6000; i++) {
      if (compare(mutate(rng), `case ${i}`) === "accepted") accepted++;
      else rejected++;
    }
    expect(rejected).toBeGreaterThan(2000);
    expect(accepted).toBeGreaterThan(300);
  }, 60_000);

  it("agrees on non-objects and on the hard caps", () => {
    for (const bad of [null, undefined, 1, "x", [], true])
      compare(bad, `non-object ${String(bad)}`);
    const full = (n: number) => ({
      ...base(),
      matches: Array.from({ length: n }, (_, i) => screenerMatch({ home: 1 + i, away: 1000 + i })),
    });
    expect(compare(full(100), "100 matches")).toBe("accepted");
    expect(compare(full(101), "101 matches")).toBe("rejected");
    const excluded = (n: number) => ({
      ...base(),
      excluded: Array.from({ length: n }, () => ({ match: "a", reason: "b" })),
    });
    expect(compare(excluded(200), "200 excluded")).toBe("accepted");
    expect(compare(excluded(201), "201 excluded")).toBe("rejected");
  });

  it("drops unknown keys everywhere and keeps only the contract keys", () => {
    const doc = base();
    (doc as Json).surprise = { a: 1 };
    ((doc.matches as Json[])[0] as Json).extra = "x";
    const hand = validateScreener(doc);
    expect(hand.success).toBe(true);
    if (hand.success) {
      expect("surprise" in hand.data).toBe(false);
      expect("extra" in (hand.data.matches[0] as object)).toBe(false);
    }
    compare(doc, "extra keys");
  });
});
