// @ts-check
// Repository check (architecture 3, sections 6.10 and 8.12, risk R-O8; essentials 3 step 3): the alert
// definitions the bot commands use must equal the ones in the Python job and in the watchdog, so
// /status and /alerts can never quietly disagree with the alert delivery and the health check.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, it } from "node:test";

const ROOT = path.resolve(import.meta.dirname, "..");
const read = (/** @type {string} */ rel) => readFileSync(path.join(ROOT, rel), "utf8");

/** Every double-quoted string inside the first `[...]` or `(...)` after `marker`. */
function listAfter(/** @type {string} */ text, /** @type {string} */ marker) {
  const start = text.indexOf(marker);
  assert.ok(start >= 0, `marker not found: ${marker}`);
  const rest = text.slice(start + marker.length);
  const open = rest.search(/[[(]/);
  const close = rest.indexOf(rest[open] === "[" ? "]" : ")", open);
  return [...rest.slice(open, close).matchAll(/"([^"]+)"/g)].map((m) => m[1]);
}

const queries = read("apps/bot/src/repo/queries.ts");

describe("alert definitions shared with Python and the watchdog", () => {
  it("flush kinds equal _WARN_ALERT_KINDS in footy/repo/ops.py", () => {
    const python = listAfter(read("apps/fit/src/footy/repo/ops.py"), "_WARN_ALERT_KINDS =");
    assert.deepEqual(listAfter(queries, "FLUSH_ALERT_KINDS ="), python);
  });

  it("the anomaly prefix matches the LIKE pattern in ops.py", () => {
    const ops = read("apps/fit/src/footy/repo/ops.py");
    assert.ok(ops.includes("kind LIKE 'anomaly\\\\_%'"), "ops.py anomaly pattern changed");
    assert.ok(queries.includes('FLUSH_ALERT_PREFIX = "anomaly_"'));
  });

  it("alert-path kinds equal BOT_PROBLEM_KINDS in footy/health.py", () => {
    const python = listAfter(read("apps/fit/src/footy/health.py"), "BOT_PROBLEM_KINDS =");
    assert.deepEqual(listAfter(queries, "ALERT_PATH_KINDS ="), python);
  });

  it("watchdog finding kinds equal the kinds collectFindings reports", () => {
    const watchdog = read("apps/bot/src/watchdog/index.ts");
    const body = watchdog.slice(
      watchdog.indexOf("export async function collectFindings"),
      watchdog.indexOf("export async function runWatchdog"),
    );
    const kinds = [...body.matchAll(/kind: "(watchdog_[a-z_]+)"/g)].map((m) => m[1]);
    assert.ok(kinds.length > 0);
    assert.deepEqual(listAfter(queries, "WATCHDOG_FINDING_KINDS ="), kinds);
  });
});
