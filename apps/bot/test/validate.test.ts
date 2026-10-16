import { describe, expect, it } from "vitest";
import { buildSyntheticUpload, makeRng } from "../src/spike/payload";
import { spikeUploadSchema } from "../src/spike/schema";
import { validateUpload } from "../src/spike/validate";

/**
 * The hand validator (F1 trim) must accept and reject exactly what the Zod placeholder schema does.
 * Hundreds of deterministic random mutations of a valid upload are fed to both and must agree.
 */

type Path = (string | number)[];

function collectPaths(value: unknown, prefix: Path = [], out: Path[] = []): Path[] {
  out.push(prefix);
  if (Array.isArray(value))
    for (const [i, v] of value.entries()) collectPaths(v, [...prefix, i], out);
  else if (typeof value === "object" && value !== null) {
    for (const [k, v] of Object.entries(value)) collectPaths(v, [...prefix, k], out);
  }
  return out;
}

const REPLACEMENTS: unknown[] = [
  null,
  0,
  -1,
  1,
  61,
  1.5,
  "",
  "x",
  "x".repeat(65),
  "x".repeat(161),
  "x".repeat(301),
  "http://example.invalid/x",
  "https://example.invalid/x",
  "out",
  "doubtful",
  "weird",
  "2026-10-17",
  "2026-10-17T12:00:00Z",
  "2026-10-17T12:00:30Z",
  "EPL",
  "XXX",
  true,
  [],
  {},
  [null],
  Array.from({ length: 41 }, () => ({ player: "p", status: "out", source_url: "https://x" })),
  Array.from({ length: 21 }, () => "https://x"),
  Array.from({ length: 101 }, () => ({})),
];
const DELETE = Symbol("delete");

function mutate(base: unknown, rng: () => number): unknown {
  const copy = structuredClone(base) as Record<string, unknown>;
  const paths = collectPaths(copy).filter((p) => p.length > 0);
  const path = paths[Math.floor(rng() * paths.length)] as Path;
  const choice = rng() < 0.2 ? DELETE : REPLACEMENTS[Math.floor(rng() * REPLACEMENTS.length)];
  type Node = Record<string | number, unknown>;
  let parent = copy as Node;
  for (const key of path.slice(0, -1)) parent = parent[key] as Node;
  const last = path[path.length - 1] as string | number;
  if (choice === DELETE) {
    if (Array.isArray(parent)) parent.splice(last as number, 1);
    else delete parent[last];
  } else {
    parent[last] = structuredClone(choice);
  }
  return copy;
}

describe("validateUpload agrees with the Zod placeholder schema", () => {
  const base = buildSyntheticUpload(6);

  it("accepts the valid synthetic upload and returns it", () => {
    expect(spikeUploadSchema.safeParse(base).success).toBe(true);
    expect(validateUpload(base)).not.toBeNull();
  });

  it("agrees on 1,500 mutated payloads, with both outcomes well represented", () => {
    const rng = makeRng(99);
    let accepted = 0;
    let rejected = 0;
    for (let i = 0; i < 1500; i++) {
      const candidate = mutate(base, rng);
      const zod = spikeUploadSchema.safeParse(candidate).success;
      const hand = validateUpload(candidate) !== null;
      if (zod !== hand)
        throw new Error(
          `disagreement on case ${i}: zod=${zod} hand=${hand}\n${JSON.stringify(candidate).slice(0, 400)}`,
        );
      if (zod) accepted++;
      else rejected++;
    }
    expect(rejected).toBeGreaterThan(300);
    expect(accepted).toBeGreaterThan(100);
  });

  it("ignores unknown extra keys like Zod does, and rejects non-objects", () => {
    const withExtra = { ...(base as object), extra: { anything: 1 } };
    expect(spikeUploadSchema.safeParse(withExtra).success).toBe(true);
    expect(validateUpload(withExtra)).not.toBeNull();
    for (const bad of [null, undefined, 1, "x", [], true]) {
      expect(validateUpload(bad)).toBeNull();
      expect(spikeUploadSchema.safeParse(bad).success).toBe(false);
    }
  });

  it("enforces the hard caps: 100 matches, 200 excluded", () => {
    expect(validateUpload(buildSyntheticUpload(100))).not.toBeNull();
    expect(validateUpload(buildSyntheticUpload(101))).toBeNull();
    const tooManyExcluded = {
      ...(buildSyntheticUpload(1) as object),
      excluded: Array.from({ length: 201 }, () => ({ match: "a", reason: "b" })),
    };
    expect(validateUpload(tooManyExcluded)).toBeNull();
  });
});
