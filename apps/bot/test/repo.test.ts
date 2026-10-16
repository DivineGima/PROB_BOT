import { env } from "cloudflare:workers";
import { beforeEach, describe, expect, it } from "vitest";
import { createRepositories } from "../src/repo";

let now = new Date("2026-10-16T08:00:00Z");
const repos = () => createRepositories(env.DB, () => now);

beforeEach(async () => {
  now = new Date("2026-10-16T08:00:00Z");
  await env.DB.batch([
    env.DB.prepare("DELETE FROM processed_updates"),
    env.DB.prepare("DELETE FROM uploads"),
    env.DB.prepare("DELETE FROM events"),
  ]);
});

describe("migration 0001", () => {
  it("creates exactly the four Stage 1 tables (ADR-033)", async () => {
    const { results } = await env.DB.prepare(
      "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE '_cf_%' AND name <> 'd1_migrations' ORDER BY name",
    ).all<{ name: string }>();
    expect(results.map((r) => r.name)).toEqual([
      "events",
      "job_runs",
      "processed_updates",
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
