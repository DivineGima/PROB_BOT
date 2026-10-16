import { createExecutionContext, waitOnExecutionContext } from "cloudflare:test";
import { env } from "cloudflare:workers";
import { describe, expect, it } from "vitest";
import { handleFetch } from "../src/index";
import { bpGrid, CELLS, dcGrid, GRID_SIZE, markets, mixGrids, piGrid } from "../src/spike/grids";
import { buildSyntheticModelRows, buildSyntheticUpload, MODEL_KINDS } from "../src/spike/payload";
import { runWorkload, SpikeInputError } from "../src/spike/workload";

const sum = (grid: Float64Array) => grid.reduce((a, b) => a + b, 0);
const upload = (matches = 60, seed?: number) => JSON.stringify(buildSyntheticUpload(matches, seed));
const poisson = (k: number, lambda: number) =>
  Math.exp(-lambda) *
  lambda ** k *
  (k === 0 ? 1 : 1 / [...Array(k).keys()].reduce((a, i) => a * (i + 1), 1));

function moments(grid: Float64Array) {
  let home = 0;
  let away = 0;
  let cross = 0;
  for (let i = 0; i < GRID_SIZE; i++) {
    for (let j = 0; j < GRID_SIZE; j++) {
      const p = grid[i * GRID_SIZE + j] ?? 0;
      home += i * p;
      away += j * p;
      cross += i * j * p;
    }
  }
  return { home, away, covariance: cross - home * away };
}

describe("spike grids (workload sanity, not the production engine)", () => {
  const grids = {
    dc: dcGrid(1.45, 1.1, -0.05),
    pi: piGrid(1.3, 1.2),
    bp: bpGrid(1.2, 0.9, 0.12),
  };

  it("each grid has 169 non-negative cells summing to 1", () => {
    for (const grid of Object.values(grids)) {
      expect(grid.length).toBe(CELLS);
      expect(Math.min(...grid)).toBeGreaterThanOrEqual(0);
      expect(sum(grid)).toBeCloseTo(1, 9);
    }
  });

  it("independent grid cells equal the hand-computed Poisson product", () => {
    const grid = piGrid(1.3, 1.2);
    expect(grid[0]).toBeCloseTo(Math.exp(-2.5), 6);
    expect(grid[2 * GRID_SIZE + 1]).toBeCloseTo(Math.exp(-2.5) * ((1.3 * 1.3) / 2) * 1.2, 6);
  });

  it("bivariate Poisson has the textbook moments: E[X]=l1+l3, E[Y]=l2+l3, Cov=l3", () => {
    const { home, away, covariance } = moments(bpGrid(1.2, 0.9, 0.12));
    expect(home).toBeCloseTo(1.32, 5);
    expect(away).toBeCloseTo(1.02, 5);
    expect(covariance).toBeCloseTo(0.12, 5);
  });

  it("bivariate Poisson P(0,0) is e^-(l1+l2+l3), and with l3 -> 0 it equals independent Poisson", () => {
    expect(bpGrid(1.2, 0.9, 0.12)[0]).toBeCloseTo(Math.exp(-2.22), 6);
    const bp = bpGrid(1.4, 1.1, 1e-12);
    const independent = piGrid(1.4, 1.1);
    for (let c = 0; c < CELLS; c++) expect(bp[c]).toBeCloseTo(independent[c] ?? 0, 9);
  });

  it("Dixon-Coles scales the four low-score cells by tau and renormalises, hand-computed", () => {
    const [lh, la, rho] = [1.4, 1.1, -0.1];
    const p = (i: number, j: number) => poisson(i, lh) * poisson(j, la);
    const tau = {
      "0,0": 1 - lh * la * rho,
      "0,1": 1 + lh * rho,
      "1,0": 1 + la * rho,
      "1,1": 1 - rho,
    };
    const lowMass = p(0, 0) + p(0, 1) + p(1, 0) + p(1, 1);
    const adjusted =
      p(0, 0) * tau["0,0"] + p(0, 1) * tau["0,1"] + p(1, 0) * tau["1,0"] + p(1, 1) * tau["1,1"];
    const norm = 1 - lowMass + adjusted;
    const grid = dcGrid(lh, la, rho);
    expect(grid[0]).toBeCloseTo((p(0, 0) * tau["0,0"]) / norm, 5);
    expect(grid[GRID_SIZE + 1]).toBeCloseTo((p(1, 1) * tau["1,1"]) / norm, 5);
    expect(grid[2 * GRID_SIZE + 2]).toBeCloseTo(p(2, 2) / norm, 5); // untouched cell, only rescaled
  });

  it("the pooled grid yields 1X2 summing to 1 and overs that never increase", () => {
    const pooled = mixGrids(Object.values(grids), [0.4, 0.3, 0.3]);
    const m = markets(pooled);
    expect(m.home + m.draw + m.away).toBeCloseTo(1, 9);
    expect(m.overs[0]).toBeLessThanOrEqual(1);
    for (let i = 1; i < m.overs.length; i++) {
      expect(m.overs[i] ?? 1).toBeLessThanOrEqual(m.overs[i - 1] ?? 0);
    }
  });

  it("equal means give equal home and away probabilities", () => {
    const m = markets(piGrid(1.3, 1.3));
    expect(m.home).toBeCloseTo(m.away, 12);
  });
});

describe("synthetic payloads", () => {
  it("are deterministic for a seed and differ across seeds", () => {
    expect(upload(60)).toBe(upload(60));
    expect(upload(60, 7)).not.toBe(upload(60));
    const row = (seed: number) => buildSyntheticModelRows(seed).rows.dc["Synthetic Club 000"];
    expect(row(1)).toBe(row(1));
    expect(row(1)).not.toBe(row(2));
  });

  it("have a 60-match upload near 1 KB per match and model rows totalling 30-60 KB per model (sections 3.2, 5.4)", () => {
    const bytes = upload(60).length;
    expect(bytes).toBeGreaterThan(40_000);
    expect(bytes).toBeLessThan(90_000);
    const models = buildSyntheticModelRows();
    for (const kind of MODEL_KINDS) {
      const rows = Object.values(models.rows[kind]);
      expect(rows).toHaveLength(240);
      const total = rows.reduce((sum, r) => sum + r.length, 0);
      expect(total).toBeGreaterThan(25_000);
      expect(total).toBeLessThan(90_000);
      expect(models.meta[kind].length).toBeLessThan(300);
    }
  });
});

describe("runWorkload", () => {
  it("processes a 60-match upload into messages of at most 3,900 characters", () => {
    const result = runWorkload(upload(60));
    expect(result.matches).toBe(60);
    expect(result.messages).toBeGreaterThanOrEqual(1);
    expect(result.characters).toBeLessThanOrEqual(result.messages * 3900);
    expect(result.checksum).toBeGreaterThan(0);
    expect(result.checksum).toBeLessThan(60);
  });

  it("is deterministic", () => {
    expect(runWorkload(upload(20))).toEqual(runWorkload(upload(20)));
  });

  // Reference values from the version BEFORE the F1 trims (whole-blob parsing, Zod, log-factorial
  // tables). The trims must change the cost, not the numbers.
  it.each([
    [3, 1, 518, 1.2838745452319058],
    [60, 3, 10549, 28.10922765363446],
    [100, 5, 17608, 47.11782434466526],
  ])(
    "gives the same output as before the F1 trims for %i matches",
    (n, messages, characters, checksum) => {
      const result = runWorkload(upload(n));
      expect(result.matches).toBe(n);
      expect(result.messages).toBe(messages);
      expect(result.characters).toBe(characters);
      expect(result.checksum).toBeCloseTo(checksum, 9);
    },
  );

  it("reads only the rows of the teams in the upload, not the whole model", () => {
    const models = buildSyntheticModelRows();
    const touched = new Set<string>();
    const watched = {
      meta: models.meta,
      rows: Object.fromEntries(
        MODEL_KINDS.map((kind) => [
          kind,
          new Proxy(models.rows[kind], {
            get(target, prop) {
              if (typeof prop === "string" && prop.startsWith("Synthetic Club")) touched.add(prop);
              return Reflect.get(target, prop);
            },
          }),
        ]),
      ),
    } as typeof models;
    const small = buildSyntheticUpload(3) as { matches: { home: string; away: string }[] };
    runWorkload(JSON.stringify(small), watched);
    const expected = new Set(small.matches.flatMap((m) => [m.home, m.away]));
    expect(touched).toEqual(expected);
    expect(touched.size).toBeLessThanOrEqual(6);
  });

  it("handles an empty match list and the 100-match cap", () => {
    expect(runWorkload(upload(0)).matches).toBe(0);
    expect(runWorkload(upload(100)).matches).toBe(100);
  });

  it("rejects bad JSON, a bad upload, a 101-match upload and an unknown team", () => {
    expect(() => runWorkload("{nope")).toThrow(SpikeInputError);
    expect(() => runWorkload("{}")).toThrow(SpikeInputError);
    expect(() => runWorkload(upload(101))).toThrow(SpikeInputError);

    const badVersion = buildSyntheticUpload(3) as { schema_version: number };
    badVersion.schema_version = 2;
    expect(() => runWorkload(JSON.stringify(badVersion))).toThrow(SpikeInputError);

    const unknown = buildSyntheticUpload(3) as { matches: { home: string }[] };
    const first = unknown.matches[0];
    if (!first) throw new Error("fixture has no matches");
    first.home = "Not A Team";
    expect(() => runWorkload(JSON.stringify(unknown))).toThrow(SpikeInputError);
  });

  it("rejects a model with a missing team row or missing meta", () => {
    const models = buildSyntheticModelRows();
    const first = (buildSyntheticUpload(3) as { matches: { home: string }[] }).matches[0];
    if (!first) throw new Error("fixture has no matches");
    delete models.rows.dc[first.home];
    expect(() => runWorkload(upload(3), models)).toThrow(/unknown team/);

    const noMeta = buildSyntheticModelRows();
    (noMeta.meta as Record<string, unknown>).pi = undefined;
    expect(() => runWorkload(upload(3), noMeta)).toThrow(/no meta/);
  });
});

describe("spike route through the Worker", () => {
  const url = `https://bot.example/spike/${env.WEBHOOK_PATH_SECRET}`;
  const headers = { "X-Telegram-Bot-Api-Secret-Token": env.TELEGRAM_WEBHOOK_SECRET };

  async function call(init: RequestInit & { headers?: Record<string, string> }) {
    const ctx = createExecutionContext();
    const response = await handleFetch(new Request(url, { method: "POST", ...init }), env, ctx);
    await waitOnExecutionContext(ctx);
    return response;
  }

  it("requires the secret header", async () => {
    expect((await call({ body: "{}" })).status).toBe(401);
  });

  it("returns a JSON summary for a valid synthetic upload", async () => {
    const response = await call({ headers, body: upload(60) });
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({ matches: 60 });
  });

  it("answers the preparation request with 204 and still measures normally afterwards", async () => {
    const prime = await call({ headers: { ...headers, "x-spike-prime": "1" }, body: "{}" });
    expect(prime.status).toBe(204);
    const after = await call({ headers, body: upload(5) });
    expect(after.status).toBe(200);
  });

  it("does not run the preparation shortcut without the secret header", async () => {
    expect((await call({ headers: { "x-spike-prime": "1" }, body: "{}" })).status).toBe(401);
  });

  it("returns 400 for an invalid payload and 413 for an oversize one", async () => {
    expect((await call({ headers, body: "{}" })).status).toBe(400);
    expect((await call({ headers, body: "x".repeat(1024 * 1024 + 1) })).status).toBe(413);
  });
});
