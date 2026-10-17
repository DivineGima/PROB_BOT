import { env } from "cloudflare:workers";
import { beforeEach, describe, expect, it } from "vitest";
import { clearActiveRunCache, createRepositories, payloadVerifies, sha256Hex } from "../src/repo";

let now = new Date("2026-10-16T08:00:00Z");
const repos = () => createRepositories(env.DB, () => now);

beforeEach(async () => {
  now = new Date("2026-10-16T08:00:00Z");
  clearActiveRunCache();
  await env.DB.batch([
    env.DB.prepare("DELETE FROM processed_updates"),
    env.DB.prepare("DELETE FROM uploads"),
    env.DB.prepare("DELETE FROM events"),
    env.DB.prepare("DELETE FROM active_run"),
    env.DB.prepare("DELETE FROM team_form"),
    env.DB.prepare("DELETE FROM model_params"),
    env.DB.prepare("DELETE FROM model_runs"),
  ]);
});

describe("migrations 0001 to 0003", () => {
  it("create exactly the Stage 1, 2 and 4 tables, no later-stage ones (ADR-033)", async () => {
    const { results } = await env.DB.prepare(
      "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE '_cf_%' AND name <> 'd1_migrations' ORDER BY name",
    ).all<{ name: string }>();
    expect(results.map((r) => r.name)).toEqual([
      "active_run",
      "competitions",
      "events",
      "job_runs",
      "matches",
      "model_params",
      "model_runs",
      "processed_updates",
      "source_fetch_log",
      "team_aliases",
      "team_form",
      "teams",
      "uploads",
    ]);
  });

  it("rejects an upload status outside the CHECK list", async () => {
    await expect(
      env.DB.prepare(
        "INSERT INTO uploads (update_id, received_at, status) VALUES (1, '2026-10-16T08:00:00Z', 'bogus')",
      ).run(),
    ).rejects.toThrow();
  });

  it("enforces a unique update_id on uploads", async () => {
    const insert = env.DB.prepare(
      "INSERT INTO uploads (update_id, received_at) VALUES (7, '2026-10-16T08:00:00Z')",
    );
    await insert.run();
    await expect(insert.run()).rejects.toThrow();
  });

  it("defaults a new upload to status received", async () => {
    await env.DB.prepare("INSERT INTO uploads (update_id, received_at) VALUES (8, 'x')").run();
    const row = await env.DB.prepare("SELECT status FROM uploads WHERE update_id = 8").first();
    expect(row).toEqual({ status: "received" });
  });
});

describe("UpdateRepository.markProcessed", () => {
  it("is true the first time and false for a replay, keeping the first kind", async () => {
    const { updates } = repos();
    expect(await updates.markProcessed(100, "document")).toBe(true);
    expect(await updates.markProcessed(100, "text")).toBe(false);
    const row = await env.DB.prepare(
      "SELECT kind, received_at FROM processed_updates WHERE update_id = 100",
    ).first();
    expect(row).toEqual({ kind: "document", received_at: "2026-10-16T08:00:00Z" });
  });

  it("treats different update ids independently and defaults kind to unknown", async () => {
    const { updates } = repos();
    expect(await updates.markProcessed(101)).toBe(true);
    expect(await updates.markProcessed(102)).toBe(true);
    const row = await env.DB.prepare(
      "SELECT kind FROM processed_updates WHERE update_id = 101",
    ).first();
    expect(row).toEqual({ kind: "unknown" });
  });

  it("uses bound parameters: a hostile kind string is stored verbatim, not executed", async () => {
    const hostile = "x'); DROP TABLE processed_updates; --";
    expect(await repos().updates.markProcessed(103, hostile)).toBe(true);
    const row = await env.DB.prepare(
      "SELECT kind FROM processed_updates WHERE update_id = 103",
    ).first();
    expect(row).toEqual({ kind: hostile });
  });
});

describe("UploadRepository", () => {
  it("records a received upload and is idempotent per update id", async () => {
    const { uploads } = repos();
    const first = await uploads.record({ updateId: 200, tgFileUniqueId: "u1", sizeBytes: 1234 });
    const again = await uploads.record({ updateId: 200 });
    expect(again).toBe(first);
    const row = await env.DB.prepare(
      "SELECT status, tg_file_unique_id, size_bytes FROM uploads WHERE upload_id = ?",
    )
      .bind(first)
      .first();
    expect(row).toEqual({ status: "received", tg_file_unique_id: "u1", size_bytes: 1234 });
  });

  it("finalises a received upload once; a second finalise changes nothing", async () => {
    const { uploads } = repos();
    const id = await uploads.record({ updateId: 201 });
    expect(
      await uploads.finalise(id, {
        status: "processed",
        nMatchesIn: 12,
        nPublished: 9,
        nOmitted: 3,
      }),
    ).toBe(true);
    expect(await uploads.finalise(id, { status: "failed", errorCode: "E_INTERNAL" })).toBe(false);
    const row = await env.DB.prepare(
      "SELECT status, n_matches_in, n_published, n_omitted, error_code FROM uploads WHERE upload_id = ?",
    )
      .bind(id)
      .first();
    expect(row).toEqual({
      status: "processed",
      n_matches_in: 12,
      n_published: 9,
      n_omitted: 3,
      error_code: null,
    });
  });

  it("finalise on an unknown id returns false", async () => {
    expect(await repos().uploads.finalise(99999, { status: "failed" })).toBe(false);
  });

  it("findStale returns only uploads still received for at least the given minutes", async () => {
    const { uploads } = repos();
    const stuck = await uploads.record({ updateId: 300 });
    const done = await uploads.record({ updateId: 301 });
    await uploads.finalise(done, { status: "processed" });

    now = new Date("2026-10-16T08:09:59Z");
    expect(await repos().uploads.findStale(10)).toEqual([]);

    now = new Date("2026-10-16T08:10:00Z");
    expect(await repos().uploads.findStale(10)).toEqual([
      { uploadId: stuck, updateId: 300, receivedAt: "2026-10-16T08:00:00Z" },
    ]);
  });
});

describe("EventRepository.record", () => {
  it("stores level, source, kind, JSON detail and dedupe key", async () => {
    await repos().events.record({
      level: "warn",
      source: "bot",
      kind: "test_event",
      detail: { n: 1, text: "é" },
      dedupeKey: "k:2026-10-16",
    });
    const row = await env.DB.prepare(
      "SELECT at, level, source, kind, detail_json, dedupe_key FROM events",
    ).first();
    expect(row).toEqual({
      at: "2026-10-16T08:00:00Z",
      level: "warn",
      source: "bot",
      kind: "test_event",
      detail_json: '{"n":1,"text":"é"}',
      dedupe_key: "k:2026-10-16",
    });
  });
});

describe("EventRepository.record dedupe", () => {
  const count = async (where = "1=1") =>
    (await env.DB.prepare(`SELECT COUNT(*) AS n FROM events WHERE ${where}`).first<{ n: number }>())
      ?.n;

  it("writes a keyed event once per 24 hours and again after the window", async () => {
    const event = { level: "info", source: "bot", kind: "k", dedupeKey: "same" } as const;
    await repos().events.record(event);
    now = new Date("2026-10-16T20:00:00Z");
    await repos().events.record(event);
    expect(await count()).toBe(1);

    now = new Date("2026-10-17T08:00:01Z");
    await repos().events.record(event);
    expect(await count()).toBe(2);
  });

  it("keeps different keys apart and never dedupes events without a key", async () => {
    await repos().events.record({ level: "info", source: "bot", kind: "k", dedupeKey: "a" });
    await repos().events.record({ level: "info", source: "bot", kind: "k", dedupeKey: "b" });
    await repos().events.record({ level: "info", source: "bot", kind: "k" });
    await repos().events.record({ level: "info", source: "bot", kind: "k" });
    expect(await count()).toBe(4);
  });
});

describe("RunRepository.readActive (Stage 4: a promoted run is readable through the Worker repo)", () => {
  const insertRun = (runId: string, status: string) =>
    env.DB.prepare(
      `INSERT INTO model_runs (run_id, status, started_at, data_cutoff_utc, config_json, ensemble_json)
       VALUES (?1, ?2, '2026-10-16T01:17:00Z', '2026-10-15', '{"unvalidated":true}', '{"weights":{"dc":1}}')`,
    ).bind(runId, status);

  const insertParams = async (runId: string, model: string, payload: string) =>
    env.DB.prepare(
      `INSERT INTO model_params (run_id, model, status, payload_version, payload_json, payload_sha256)
       VALUES (?1, ?2, 'ok', 1, ?3, ?4)`,
    )
      .bind(runId, model, payload, await sha256Hex(payload))
      .run();

  it("returns null before anything is published", async () => {
    await insertRun("R1", "building").run();
    expect(await repos().runs.readActive()).toBeNull();
  });

  it("reads the run the pointer names, with its models, and nothing from other runs", async () => {
    await insertRun("R1", "superseded").run();
    await insertRun("R2", "active").run();
    await insertParams("R1", "dc", '{"payload_version":1,"teams":{}}');
    await insertParams("R2", "dc", '{"payload_version":1,"teams":{"1":[0.1,0.2,"EPL"]}}');
    await insertParams("R2", "pi", '{"payload_version":1,"teams":{}}');
    await env.DB.prepare(
      "INSERT INTO model_params (run_id, model, status, error) VALUES ('R2', 'bp', 'failed', 'x')",
    ).run();
    await env.DB.prepare(
      "INSERT INTO active_run (id, run_id, activated_at) VALUES (1, 'R2', '2026-10-16T01:30:00Z')",
    ).run();

    const run = await repos().runs.readActive();
    expect(run).not.toBeNull();
    expect(run?.runId).toBe("R2");
    expect(run?.activatedAt).toBe("2026-10-16T01:30:00Z");
    expect(run?.dataCutoffUtc).toBe("2026-10-15");
    expect(JSON.parse(run?.ensembleJson ?? "{}")).toEqual({ weights: { dc: 1 } });
    expect(run?.params.map((p) => [p.model, p.status])).toEqual([
      ["bp", "failed"],
      ["dc", "ok"],
      ["pi", "ok"],
    ]);
    expect(run?.params.find((p) => p.model === "bp")?.error).toBe("x");
    const dc = run?.params.find((p) => p.model === "dc");
    expect(dc?.payloadJson).toContain('"1":[0.1,0.2,"EPL"]');
    expect(dc && (await payloadVerifies(dc))).toBe(true);
  });

  it("follows the pointer when it moves (rollback) and sees nothing half-published", async () => {
    await insertRun("R1", "superseded").run();
    await insertRun("R2", "active").run();
    await insertParams("R1", "dc", '{"payload_version":1,"v":"old"}');
    await insertParams("R2", "dc", '{"payload_version":1,"v":"new"}');
    await env.DB.prepare(
      "INSERT INTO active_run (id, run_id, activated_at) VALUES (1, 'R2', 't')",
    ).run();
    expect((await repos().runs.readActive())?.params[0]?.payloadJson).toContain("new");
    await env.DB.prepare("UPDATE active_run SET run_id = 'R1' WHERE id = 1").run();
    const back = await repos().runs.readActive();
    expect(back?.runId).toBe("R1");
    expect(back?.params[0]?.payloadJson).toContain("old");
  });

  it("detects a corrupted payload and rejects failed or incomplete rows", async () => {
    const text = '{"payload_version":1}';
    const good = {
      model: "dc",
      status: "ok",
      payloadVersion: 1,
      payloadJson: text,
      error: null,
    } as const;
    expect(await payloadVerifies({ ...good, payloadSha256: await sha256Hex(text) })).toBe(true);
    expect(await payloadVerifies({ ...good, payloadSha256: await sha256Hex(`${text} `) })).toBe(
      false,
    );
    expect(await payloadVerifies({ ...good, payloadSha256: null })).toBe(false);
    expect(await payloadVerifies({ ...good, payloadJson: null, payloadSha256: "x" })).toBe(false);
    expect(await payloadVerifies({ ...good, status: "failed", payloadSha256: "x" })).toBe(false);
  });

  it("computes SHA-256 the same way the fit job does", async () => {
    // sha256("abc"), the standard test vector; Python's hashlib gives the same digest
    expect(await sha256Hex("abc")).toBe(
      "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
    );
  });
});

describe("RunRepository.readPointer and readActiveVerified (Worker CPU and D1 budget)", () => {
  const seed = async (runId: string, payload: string, activatedAt = "2026-10-16T01:30:00Z") => {
    await env.DB.prepare(
      `INSERT INTO model_runs (run_id, status, started_at, data_cutoff_utc, config_json, ensemble_json)
       VALUES (?1, 'active', 't', '2026-10-15', '{"unvalidated":true}', '{}')`,
    )
      .bind(runId)
      .run();
    await env.DB.prepare(
      `INSERT INTO model_params (run_id, model, status, payload_version, payload_json, payload_sha256)
       VALUES (?1, 'dc', 'ok', 1, ?2, ?3)`,
    )
      .bind(runId, payload, await sha256Hex(payload))
      .run();
    await env.DB.prepare(
      `INSERT INTO active_run (id, run_id, activated_at) VALUES (1, ?1, ?2)
       ON CONFLICT (id) DO UPDATE SET run_id = excluded.run_id, activated_at = excluded.activated_at`,
    )
      .bind(runId, activatedAt)
      .run();
  };

  it("reads the pointer without any payload", async () => {
    expect(await repos().runs.readPointer()).toBeNull();
    await seed("R1", '{"payload_version":1,"big":"payload"}');
    const pointer = await repos().runs.readPointer();
    expect(pointer).toEqual({
      runId: "R1",
      activatedAt: "2026-10-16T01:30:00Z",
      dataCutoffUtc: "2026-10-15",
      configJson: '{"unvalidated":true}',
      ensembleJson: "{}",
    });
    expect(JSON.stringify(pointer)).not.toContain("payload");
  });

  it("verifies once and then serves the cached run while the pointer is unchanged", async () => {
    await seed("R1", '{"payload_version":1,"v":"first"}');
    const first = await repos().runs.readActiveVerified();
    expect(first?.verified.dc).toBe(true);
    // Corrupt the stored payload behind the cache: an unchanged pointer must not re-read it.
    await env.DB.prepare("UPDATE model_params SET payload_json = 'tampered'").run();
    const second = await repos().runs.readActiveVerified();
    expect(second).toBe(first);
  });

  it("re-reads and re-verifies when the active run changes, including a rollback", async () => {
    await seed("R1", '{"payload_version":1,"v":"one"}');
    const one = await repos().runs.readActiveVerified();
    await seed("R2", '{"payload_version":1,"v":"two"}', "2026-10-16T02:30:00Z");
    const two = await repos().runs.readActiveVerified();
    expect(two?.run.runId).toBe("R2");
    expect(two?.run.params[0]?.payloadJson).toContain("two");
    await env.DB.prepare(
      "UPDATE active_run SET run_id = 'R1', activated_at = '2026-10-16T03:30:00Z'",
    ).run();
    const back = await repos().runs.readActiveVerified();
    expect(back?.run.runId).toBe("R1");
    expect(back).not.toBe(one);
  });

  it("reports a corrupted payload as unverified and returns null with no active run", async () => {
    await seed("R1", '{"payload_version":1}');
    await env.DB.prepare("UPDATE model_params SET payload_sha256 = 'wrong'").run();
    expect((await repos().runs.readActiveVerified())?.verified.dc).toBe(false);
    clearActiveRunCache();
    await env.DB.prepare("DELETE FROM active_run").run();
    expect(await repos().runs.readActiveVerified()).toBeNull();
  });
});
