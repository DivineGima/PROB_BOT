import { env } from "cloudflare:workers";
import { beforeEach, describe, expect, it } from "vitest";
import { createRepositories, type NewPrediction } from "../src/repo";
import {
  count,
  forecastValues,
  RUN_DATE,
  RUN_ID,
  resetWorld,
  seedForecast,
  seedReference,
  seedRun,
  teamName,
} from "./helpers";

const repos = () => createRepositories(env.DB, () => new Date("2026-10-17T06:00:00Z"));

beforeEach(async () => {
  await resetWorld();
  await seedReference(200);
});

const prediction = (home: number, away: number, p: [number, number, number]): NewPrediction => ({
  fixtureKey: `${RUN_DATE}|EPL|${home}|${away}`,
  label: `m${home}`,
  compCode: "EPL",
  matchDate: RUN_DATE,
  kickoffUtc: `${RUN_DATE}T15:00:00Z`,
  homeTeamId: home,
  awayTeamId: away,
  p1x2: p,
  overs: forecastValues().overs,
  totalJson: "[]",
  modelsJson: "{}",
  weightsJson: "{}",
  driftJson: "{}",
  baselineJson: "{}",
  inputsJson: "{}",
});

const newUpload = async (updateId = 1) => repos().uploads.record({ updateId });

describe("ForecastRepository.readActiveForDate", () => {
  it("reports no run when nothing is published", async () => {
    const read = await repos().forecasts.readActiveForDate(RUN_DATE);
    expect(read).toEqual({ pointer: null, forecasts: [], runHasForecasts: false });
  });

  it("returns the active run's forecasts for the date only, with numbers for ok rows", async () => {
    await seedRun();
    await seedForecast({ home: 1, away: 2, pHome: 0.55 });
    await seedForecast({ home: 3, away: 4, verdict: "DRIFT" });
    await seedForecast({ home: 5, away: 6, date: "2026-10-18" });
    const read = await repos().forecasts.readActiveForDate(RUN_DATE);
    expect(read.pointer?.runId).toBe(RUN_ID);
    expect(read.runHasForecasts).toBe(true);
    expect(read.forecasts.map((f) => f.fixtureKey)).toEqual([
      `${RUN_DATE}|EPL|1|2`,
      `${RUN_DATE}|EPL|3|4`,
    ]);
    const [ok, drift] = read.forecasts;
    expect(ok?.verdict).toBe("ok");
    expect(ok?.p1x2?.[0]).toBe(0.55);
    expect(ok?.overs).toHaveLength(6);
    expect(drift?.p1x2).toBeNull();
    expect(drift?.overs).toBeNull();
  });

  it("distinguishes a run with no forecasts at all from a day with none", async () => {
    await seedRun();
    await seedForecast({ home: 1, away: 2, date: "2026-10-18" });
    const read = await repos().forecasts.readActiveForDate(RUN_DATE);
    expect(read.forecasts).toEqual([]);
    expect(read.runHasForecasts).toBe(true);
  });

  it("follows the pointer and never mixes in another run's forecasts (rollback)", async () => {
    await seedRun({ runId: "R1", status: "superseded" });
    await seedRun({ runId: "R2" });
    await seedForecast({ home: 1, away: 2, pHome: 0.3 }, "R1");
    await seedForecast({ home: 1, away: 2, pHome: 0.7 }, "R2");
    expect((await repos().forecasts.readActiveForDate(RUN_DATE)).forecasts[0]?.p1x2?.[0]).toBe(0.7);
    await env.DB.prepare("UPDATE active_run SET run_id = 'R1' WHERE id = 1").run();
    const back = await repos().forecasts.readActiveForDate(RUN_DATE);
    expect(back.pointer?.runId).toBe("R1");
    expect(back.forecasts[0]?.p1x2?.[0]).toBe(0.3);
  });
});

describe("PredictionRepository", () => {
  it("inserts many rows with one statement and the first row for a fixture wins", async () => {
    const uploadId = await newUpload(1);
    const inserted = await repos().predictions.insertManyIgnoreDuplicates(uploadId, RUN_ID, [
      prediction(1, 2, [0.5, 0.25, 0.25]),
      prediction(3, 4, [0.4, 0.3, 0.3]),
    ]);
    expect(inserted).toBe(2);
    const second = await newUpload(2);
    const again = await repos().predictions.insertManyIgnoreDuplicates(second, RUN_ID, [
      prediction(1, 2, [0.9, 0.05, 0.05]),
      prediction(5, 6, [0.2, 0.4, 0.4]),
    ]);
    expect(again).toBe(1);
    const stored = await repos().predictions.findByDate(RUN_DATE);
    expect(
      stored.map((p) => [p.fixtureKey.split("|").slice(2).join("-"), p.p1x2[0], p.uploadId]),
    ).toEqual([
      ["1-2", 0.5, uploadId],
      ["3-4", 0.4, uploadId],
      ["5-6", 0.2, second],
    ]);
  });

  it("does nothing for an empty list", async () => {
    expect(
      await repos().predictions.insertManyIgnoreDuplicates(await newUpload(), RUN_ID, []),
    ).toBe(0);
  });

  it("round-trips a double exactly through the JSON document the insert unpacks", async () => {
    const third = 1 / 3;
    const oddOne = 0.1 + 0.2;
    const rest = 1 - third - oddOne;
    await repos().predictions.insertManyIgnoreDuplicates(await newUpload(), RUN_ID, [
      prediction(1, 2, [third, oddOne, rest]),
    ]);
    const [stored] = await repos().predictions.findByDate(RUN_DATE);
    expect(stored?.p1x2).toEqual([third, oddOne, rest]);
  });

  it("returns only the requested date, oldest first", async () => {
    const uploadId = await newUpload();
    const other = {
      ...prediction(7, 8, [0.5, 0.25, 0.25]),
      matchDate: "2026-10-18",
      fixtureKey: "2026-10-18|EPL|7|8",
    };
    await repos().predictions.insertManyIgnoreDuplicates(uploadId, RUN_ID, [
      prediction(1, 2, [0.5, 0.25, 0.25]),
      other,
    ]);
    expect((await repos().predictions.findByDate(RUN_DATE)).map((p) => p.homeTeamId)).toEqual([1]);
    expect((await repos().predictions.findByDate("2026-10-18")).map((p) => p.homeTeamId)).toEqual([
      7,
    ]);
  });
});

describe("predictions and omissions constraints (section 5.7)", () => {
  const insert = async (overrides: Record<string, unknown>) => {
    const uploadId = await newUpload(Math.floor(Math.random() * 1e9));
    const base = prediction(1, 2, [0.5, 0.25, 0.25]);
    const row = { ...base, ...overrides };
    return repos().predictions.insertManyIgnoreDuplicates(uploadId, RUN_ID, [row as NewPrediction]);
  };

  // INSERT OR IGNORE skips a row that violates a CHECK instead of raising, so a bad row is simply
  // never stored (and the upload pipeline then fails loudly when it cannot read the row back).
  it("never stores probabilities that do not sum to 1 within 1e-6", async () => {
    await expect(insert({ p1x2: [0.5, 0.25, 0.26] })).resolves.toBe(0);
    expect(await count("predictions")).toBe(0);
    await expect(insert({ p1x2: [0.5, 0.25, 0.25 + 5e-7] })).resolves.toBe(1);
  });

  it("never stores overs that increase with the line", async () => {
    await expect(insert({ overs: [0.9, 0.8, 0.85, 0.3, 0.2, 0.1] })).resolves.toBe(0);
    expect(await count("predictions")).toBe(0);
  });

  it("rejects a scored row without a result and a void row without a reason", async () => {
    await insert({});
    await expect(
      env.DB.prepare("UPDATE predictions SET status = 'scored'").run(),
    ).rejects.toThrow();
    await expect(env.DB.prepare("UPDATE predictions SET status = 'void'").run()).rejects.toThrow();
    await expect(
      env.DB.prepare("UPDATE predictions SET status = 'void', void_reason = 'BOGUS'").run(),
    ).rejects.toThrow();
    await env.DB.prepare("UPDATE predictions SET status = 'void', void_reason = 'NO_RESULT'").run();
    await expect(
      env.DB.prepare("UPDATE predictions SET status = 'pending'").run(),
    ).rejects.toThrow();
  });

  it("allows one omission per label per upload and only known reasons", async () => {
    const uploadId = await newUpload();
    const add = (label: string, reason: string) =>
      env.DB.prepare("INSERT INTO omissions (upload_id, label, reason_code) VALUES (?1, ?2, ?3)")
        .bind(uploadId, label, reason)
        .run();
    await add("a", "NO_FORECAST");
    await expect(add("a", "DRIFT")).rejects.toThrow();
    await expect(add("b", "MADE_UP")).rejects.toThrow();
    await add("b", "NO_FORECAST");
    expect(await count("omissions")).toBe(2);
  });
});

describe("TeamRepository.resolveCanonical", () => {
  it("maps exact canonical names to ids and leaves unknown names out", async () => {
    const found = await repos().teams.resolveCanonical([
      teamName(1),
      teamName(2),
      "Nobody FC",
      "club 1",
    ]);
    expect([...found.entries()]).toEqual([
      [teamName(1), 1],
      [teamName(2), 2],
    ]);
  });

  it("handles more names than one statement can bind (chunked)", async () => {
    const names = Array.from({ length: 200 }, (_, i) => teamName(i + 1));
    const found = await repos().teams.resolveCanonical([...names, ...names]);
    expect(found.size).toBe(200);
    expect(found.get(teamName(200))).toBe(200);
  });

  it("returns an empty map for no names", async () => {
    expect((await repos().teams.resolveCanonical([])).size).toBe(0);
  });
});
