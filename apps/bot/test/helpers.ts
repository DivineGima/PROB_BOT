import { env } from "cloudflare:workers";

/** Shared test doubles for the Stage 5b suites: a seeded world, screener files, a fake Telegram. */

export const RUN_ID = "R20261017T011700Z";
export const RUN_DATE = "2026-10-17";
export const NOW = new Date("2026-10-17T06:00:00Z");
export const KICKOFF = "2026-10-17T15:00:00Z";
export const CHAT_ID = Number(env.ALLOWED_CHAT_ID);
export const TOKEN = env.TELEGRAM_BOT_TOKEN as string;

const OVERS = [0.97, 0.84, 0.61, 0.36, 0.17, 0.07];
const TOTAL = [0.03, 0.13, 0.23, 0.25, 0.19, 0.1, 0.04, 0.02, 0.005, 0.003, 0.001, 0.0005, 0.0005];

export interface ForecastSpec {
  home: number;
  away: number;
  comp?: string;
  date?: string;
  verdict?: "ok" | "INSUFFICIENT_HISTORY" | "DRIFT" | "NO_MODEL";
  /** Home win probability; draw and away split the rest 50/50. */
  pHome?: number;
  detail?: Record<string, unknown>;
}

export function forecastKey(spec: ForecastSpec): string {
  return `${spec.date ?? RUN_DATE}|${spec.comp ?? "EPL"}|${spec.home}|${spec.away}`;
}

/** Wipes everything the Stage 5b suites write, children first. */
export async function resetWorld(): Promise<void> {
  await env.DB.batch([
    env.DB.prepare("DELETE FROM omissions"),
    env.DB.prepare("DELETE FROM predictions"),
    env.DB.prepare("DELETE FROM uploads"),
    env.DB.prepare("DELETE FROM fixture_forecasts"),
    env.DB.prepare("DELETE FROM active_run"),
    env.DB.prepare("DELETE FROM team_form"),
    env.DB.prepare("DELETE FROM model_params"),
    env.DB.prepare("DELETE FROM model_runs"),
    env.DB.prepare("DELETE FROM events"),
    env.DB.prepare("DELETE FROM processed_updates"),
    env.DB.prepare("DELETE FROM matches"),
    env.DB.prepare("DELETE FROM teams"),
    env.DB.prepare("DELETE FROM competitions"),
  ]);
}

export async function seedReference(teamCount = 40): Promise<void> {
  const statements = [
    env.DB.prepare("INSERT INTO competitions (comp_code, name) VALUES ('EPL', 'Premier League')"),
    env.DB.prepare("INSERT INTO competitions (comp_code, name) VALUES ('UCL', 'Champions League')"),
    env.DB.prepare("INSERT INTO competitions (comp_code, name) VALUES ('LL', 'La Liga')"),
  ];
  for (let id = 1; id <= teamCount; id++) {
    statements.push(
      env.DB.prepare(
        "INSERT INTO teams (team_id, canonical_name, home_comp, is_ucl_only, active) VALUES (?1, ?2, 'EPL', 0, 1)",
      ).bind(id, teamName(id)),
    );
  }
  await env.DB.batch(statements);
}

export const teamName = (id: number): string => `Club ${id}`;

export interface RunSpec {
  runId?: string;
  activatedAt?: string;
  config?: Record<string, unknown>;
  ensemble?: Record<string, unknown>;
  status?: string;
}

export async function seedRun(spec: RunSpec = {}): Promise<string> {
  const runId = spec.runId ?? RUN_ID;
  await env.DB.prepare(
    `INSERT INTO model_runs (run_id, status, started_at, data_cutoff_utc, config_json, ensemble_json)
     VALUES (?1, ?2, '2026-10-17T01:17:00Z', '2026-10-16', ?3, ?4)`,
  )
    .bind(
      runId,
      spec.status ?? "active",
      JSON.stringify(spec.config ?? { models: ["dc", "pi", "bp"], stale_hours: 36 }),
      JSON.stringify(spec.ensemble ?? { weights: { dc: 0.4, pi: 0.3, bp: 0.3 } }),
    )
    .run();
  if ((spec.status ?? "active") === "active") {
    await env.DB.prepare("DELETE FROM active_run").run();
    await env.DB.prepare("INSERT INTO active_run (id, run_id, activated_at) VALUES (1, ?1, ?2)")
      .bind(runId, spec.activatedAt ?? "2026-10-17T01:30:00Z")
      .run();
  }
  return runId;
}

export function forecastValues(pHome = 0.5): {
  p: [number, number, number];
  overs: number[];
} {
  const rest = (1 - pHome) / 2;
  return { p: [pHome, rest, rest], overs: [...OVERS] };
}

export async function seedForecast(spec: ForecastSpec, runId = RUN_ID): Promise<void> {
  const verdict = spec.verdict ?? "ok";
  const { p, overs } = forecastValues(spec.pHome ?? 0.5);
  const comp = spec.comp ?? "EPL";
  const date = spec.date ?? RUN_DATE;
  const ok = verdict === "ok";
  const model = (shift: number) => ({
    p: [p[0] + shift, p[1] - shift / 2, p[2] - shift / 2],
    total: TOTAL,
  });
  await env.DB.prepare(
    `INSERT INTO fixture_forecasts (
       run_id, fixture_key, comp_code, match_date, kickoff_utc, home_team_id, away_team_id, verdict,
       p_home, p_draw, p_away, p_over_05, p_over_15, p_over_25, p_over_35, p_over_45, p_over_55,
       total_json, models_json, weights_json, baseline_json, detail_json, created_at)
     VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15, ?16, ?17, ?18, ?19,
       ?20, ?21, ?22, '2026-10-17T01:20:00Z')`,
  )
    .bind(
      runId,
      forecastKey(spec),
      comp,
      date,
      `${date}T15:00:00Z`,
      spec.home,
      spec.away,
      verdict,
      ok ? p[0] : null,
      ok ? p[1] : null,
      ok ? p[2] : null,
      ...overs.map((v) => (ok ? v : null)),
      ok ? JSON.stringify(TOTAL) : null,
      ok ? JSON.stringify({ dc: model(0.02), pi: model(-0.02), bp: model(0) }) : null,
      ok ? JSON.stringify({ bp: 0.3, dc: 0.4, pi: 0.3 }) : null,
      ok ? JSON.stringify({ p_home: 0.45, p_draw: 0.27, p_away: 0.28 }) : null,
      JSON.stringify(spec.detail ?? { drift: { verdict } }),
    )
    .run();
}

// -- screener files -----------------------------------------------------------------------------

export interface MatchSpec {
  id?: string;
  comp?: string;
  home: number | string;
  away: number | string;
  kickoff?: string;
  extra?: Record<string, unknown>;
}

export function screenerMatch(spec: MatchSpec): Record<string, unknown> {
  const name = (v: number | string) => (typeof v === "number" ? teamName(v) : v);
  return {
    match_id: spec.id ?? `${RUN_DATE}_${spec.comp ?? "EPL"}_${spec.home}_${spec.away}`,
    competition: spec.comp ?? "EPL",
    home: name(spec.home),
    away: name(spec.away),
    kickoff_utc: spec.kickoff ?? KICKOFF,
    lineup_status: "expected",
    absences_home: null,
    absences_away: [{ player: "A. Player", status: "out", source_url: "https://example.com/a" }],
    rest_days_home: 5,
    rest_days_away: null,
    source_urls: ["https://example.com/fixture"],
    ...spec.extra,
  };
}

export function screenerFile(
  matches: Array<Record<string, unknown>>,
  overrides: Record<string, unknown> = {},
): Uint8Array {
  const doc = {
    schema_version: 1,
    run_date_utc: RUN_DATE,
    notes: null,
    matches,
    excluded: [
      { match: "X vs Y", reason: "G2_EARLY_SEASON" },
      { match: "P vs Q", reason: "g4 rotation" },
      { match: "R vs S", reason: "something else" },
    ],
    ...overrides,
  };
  return new TextEncoder().encode(JSON.stringify(doc));
}

// -- fake Telegram ----------------------------------------------------------------------------------

export interface FakeTelegramOptions {
  files?: Record<string, { path?: string; bytes: Uint8Array; declaredSize?: number }>;
  /** Fail every sendMessage from this call number on (1-based). */
  failSendFrom?: number;
  failGetFile?: boolean;
  /** Answer the first sendMessage with 429 and this retry_after. */
  rateLimitOnce?: number;
}

export interface FakeTelegram {
  fetch: typeof fetch;
  sent: Array<{ chatId: number; text: string }>;
  calls: string[];
  sleeps: number[];
}

export function fakeTelegram(options: FakeTelegramOptions = {}): FakeTelegram {
  const sent: FakeTelegram["sent"] = [];
  const calls: string[] = [];
  const sleeps: number[] = [];
  let sendCalls = 0;
  let rateLimited = false;

  const json = (body: unknown, status = 200) =>
    new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

  const fetchFn = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = url.split("/").pop() ?? "";
    calls.push(method);
    if (!url.includes(`/bot${TOKEN}/`) && !url.includes(`/file/bot${TOKEN}/`)) {
      throw new Error("a request that does not carry the bot token");
    }
    if (url.includes("/file/bot")) {
      const entry = Object.values(options.files ?? {}).find((f) => url.endsWith(f.path ?? ""));
      if (!entry) return new Response("not found", { status: 404 });
      const headers = new Headers();
      if (entry.declaredSize !== undefined)
        headers.set("content-length", String(entry.declaredSize));
      return new Response(entry.bytes, { status: 200, headers });
    }
    const body = JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>;
    if (method === "getFile") {
      if (options.failGetFile) return json({ ok: false }, 400);
      const entry = options.files?.[String(body.file_id)];
      if (!entry) return json({ ok: false }, 400);
      return json({
        ok: true,
        result: {
          file_path: entry.path ?? `docs/${String(body.file_id)}.json`,
          file_size: entry.bytes.byteLength,
        },
      });
    }
    if (method === "sendMessage") {
      sendCalls++;
      if (options.rateLimitOnce !== undefined && !rateLimited) {
        rateLimited = true;
        return json({ ok: false, parameters: { retry_after: options.rateLimitOnce } }, 429);
      }
      if (options.failSendFrom !== undefined && sendCalls >= options.failSendFrom) {
        return json({ ok: false }, 400);
      }
      sent.push({ chatId: Number(body.chat_id), text: String(body.text) });
      return json({ ok: true, result: {} });
    }
    return json({ ok: false }, 404);
  }) as typeof fetch;

  return { fetch: fetchFn, sent, calls, sleeps };
}

/** A Telegram update carrying a document from the allowed chat. */
export function documentUpdate(
  updateId: number,
  fileId = "file1",
  document: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    update_id: updateId,
    message: {
      message_id: updateId,
      chat: { id: CHAT_ID, type: "private" },
      from: { id: Number(env.ALLOWED_USER_ID), is_bot: false },
      document: {
        file_id: fileId,
        file_unique_id: `u-${fileId}`,
        file_name: "screener_2026-10-17.json",
        mime_type: "application/json",
        ...document,
      },
    },
  };
}

export function textUpdate(updateId: number, text = "hello"): Record<string, unknown> {
  return {
    update_id: updateId,
    message: {
      message_id: updateId,
      chat: { id: CHAT_ID, type: "private" },
      from: { id: Number(env.ALLOWED_USER_ID), is_bot: false },
      text,
    },
  };
}

export async function count(table: string, where = "1=1"): Promise<number> {
  const row = await env.DB.prepare(`SELECT COUNT(*) AS n FROM ${table} WHERE ${where}`).first<{
    n: number;
  }>();
  return row?.n ?? -1;
}
