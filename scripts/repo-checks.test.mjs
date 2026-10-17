// @ts-check
import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { copyFileSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { after, describe, it } from "node:test";
import { findDataFiles } from "./check-no-data-files.mjs";
import { findSecretReaders } from "./check-secret-readers.mjs";
import { findSqlViolations } from "./check-sql-locality.mjs";
import { installHooks } from "./install-hooks.mjs";
import { checkImmutability, lintMigrations, stripComments } from "./lint-migrations.mjs";

const REPO_ROOT = path.resolve(import.meta.dirname, "..");
/** @type {string[]} */
const temps = [];

/** @param {Record<string, string>} files */
function tree(files) {
  const root = mkdtempSync(path.join(tmpdir(), "probbot-"));
  temps.push(root);
  for (const [rel, content] of Object.entries(files)) {
    const full = path.join(root, rel);
    mkdirSync(path.dirname(full), { recursive: true });
    writeFileSync(full, content);
  }
  return root;
}

after(() => {
  for (const dir of temps) rmSync(dir, { recursive: true, force: true });
});

describe("check-sql-locality", () => {
  it("flags SQL text and D1 calls in the Worker outside repo/", () => {
    const root = tree({
      "apps/bot/src/index.ts": 'const r = await db.prepare("SELECT * FROM uploads WHERE a = ?");\n',
      "apps/bot/src/other.ts": "const q = `INSERT INTO events (a) VALUES (1)`;\n",
    });
    const v = findSqlViolations(root);
    assert.ok(v.some((x) => x.startsWith("apps/bot/src/index.ts:1:") && x.includes("SQL text")));
    assert.ok(
      v.some((x) => x.startsWith("apps/bot/src/index.ts:1:") && x.includes("database call")),
    );
    assert.ok(v.some((x) => x.startsWith("apps/bot/src/other.ts:1:")));
  });

  it("allows SQL inside repo/ in both languages and ignores tests and comments", () => {
    const root = tree({
      "apps/bot/src/repo/index.ts": 'db.prepare("INSERT INTO events (a) VALUES (?1)");\n',
      "apps/fit/src/footy/repo/d1_client.py": 'sql = "DELETE FROM events"\nimport sqlite3\n',
      "apps/bot/test/x.test.ts": 'db.prepare("SELECT * FROM events");\n',
      "apps/fit/tests/test_x.py": 'conn.execute("DELETE FROM events")\n',
      "apps/bot/src/auth/index.ts":
        "// we select the best option from the list\n/* delete from cache */\n",
      "apps/fit/src/footy/cli.py": "# update the table set of rows\nname = 'update'\n",
    });
    assert.deepEqual(findSqlViolations(root), []);
  });

  it("flags Python database access outside repo/", () => {
    const root = tree({
      "apps/fit/src/footy/ingest/x.py": 'import sqlite3\ncur.execute("select 1 from t")\n',
    });
    const v = findSqlViolations(root);
    assert.equal(v.filter((x) => x.includes("ingest/x.py")).length >= 2, true);
  });

  it("passes on the real repository", () => {
    assert.deepEqual(findSqlViolations(REPO_ROOT), []);
  });
});

describe("check-secret-readers", () => {
  it("flags secret names outside auth/ and config/env.ts", () => {
    const root = tree({
      "apps/bot/src/index.ts": "if (id === env.ALLOWED_CHAT_ID) {}\n",
      "apps/bot/src/telegram/x.ts": "const s = env.TELEGRAM_WEBHOOK_SECRET;\n",
    });
    assert.equal(findSecretReaders(root).length, 2);
  });

  it("allows auth/ and the Env type file, and ignores tests", () => {
    const root = tree({
      "apps/bot/src/auth/index.ts": "env.WEBHOOK_PATH_SECRET; env.ALLOWED_USER_ID;\n",
      "apps/bot/src/config/env.ts": "ALLOWED_CHAT_ID: string;\n",
      "apps/bot/test/auth.test.ts": "env.ALLOWED_CHAT_ID\n",
    });
    assert.deepEqual(findSecretReaders(root), []);
  });

  it("lets only telegram/ and the Env type read the bot token", () => {
    const root = tree({
      "apps/bot/src/telegram/client.ts": "env.TELEGRAM_BOT_TOKEN\n",
      "apps/bot/src/config/env.ts": "TELEGRAM_BOT_TOKEN?: string;\n",
      "apps/bot/src/upload/index.ts": "const t = env.TELEGRAM_BOT_TOKEN;\n",
      "apps/bot/src/auth/index.ts": "env.TELEGRAM_BOT_TOKEN\n",
    });
    const found = findSecretReaders(root);
    assert.equal(found.length, 2);
    assert.ok(found.every((v) => v.includes("bot token outside telegram/")));
  });

  it("passes on the real repository", () => {
    assert.deepEqual(findSecretReaders(REPO_ROOT), []);
  });
});

describe("check-no-data-files", () => {
  const big = "x".repeat(101 * 1024);

  it("flags large data files outside data/ and packages/contracts, and any CSV or DB file", () => {
    const root = tree({
      "docs/dump.json": big,
      "apps/fit/tests/results.csv": "a,b\n1,2\n",
      "scratch/store.sqlite": "x",
      "data/notes.csv": "a\n",
    });
    const v = findDataFiles(root).join("\n");
    assert.match(v, /docs\/dump\.json/);
    assert.match(v, /apps\/fit\/tests\/results\.csv/);
    assert.match(v, /scratch\/store\.sqlite/);
    assert.match(v, /data\/notes\.csv/);
  });

  it("allows small JSON anywhere, large JSON in data/ and contracts, CSV in contracts, lockfiles", () => {
    const root = tree({
      "docs/small.json": '{"a":1}',
      "data/canonical_teams.json": big,
      "packages/contracts/golden/vectors.json": big,
      "packages/contracts/golden/fixture.csv": "a,b\n",
      "package-lock.json": big,
      "apps/bot/node_modules/pkg/data.json": big,
    });
    assert.deepEqual(findDataFiles(root), []);
  });

  it("passes on the real repository", () => {
    assert.deepEqual(findDataFiles(REPO_ROOT), []);
  });
});

describe("lint-migrations", () => {
  const ok = "CREATE TABLE a (id INTEGER PRIMARY KEY);\n";

  it("accepts sequential additive migrations", () => {
    const root = tree({
      "m/0001_init.sql": ok,
      "m/0002_more.sql": "ALTER TABLE a ADD COLUMN b TEXT;\nCREATE INDEX i ON a (b);\n",
    });
    assert.deepEqual(lintMigrations(path.join(root, "m")), []);
  });

  it("rejects bad names, gaps, duplicates and an empty directory", () => {
    const root = tree({ "m/0001_init.sql": ok, "m/0003_gap.sql": ok, "m/readme.sql": ok });
    const v = lintMigrations(path.join(root, "m")).join("\n");
    assert.match(v, /0003_gap\.sql: expected number 0002/);
    assert.match(v, /readme\.sql: name must look like/);
    const empty = tree({ "m/.keep": "" });
    assert.match(lintMigrations(path.join(empty, "m")).join("\n"), /no migrations found/);
  });

  it("rejects a drop or rename that sits beside its replacement", () => {
    const root = tree({
      "m/0001_init.sql": ok,
      "m/0002_swap.sql":
        "-- DEPRECATED-SINCE: 0001_init.sql\nCREATE TABLE b (id INTEGER);\nDROP TABLE a;\n",
      "m/0003_rename.sql":
        "-- DEPRECATED-SINCE: 0001_init.sql\nALTER TABLE b ADD COLUMN c TEXT;\nALTER TABLE b RENAME COLUMN c TO d;\n",
    });
    const v = lintMigrations(path.join(root, "m")).join("\n");
    assert.match(v, /0002_swap\.sql: drops\/renames in the same migration/);
    assert.match(v, /0003_rename\.sql: drops\/renames in the same migration/);
  });

  it("requires a deprecation citation for a standalone removal, and accepts one that has it", () => {
    const root = tree({
      "m/0001_init.sql": ok,
      "m/0002_drop.sql": "DROP TABLE a;\n",
    });
    assert.match(lintMigrations(path.join(root, "m")).join("\n"), /must cite its deprecation/);

    const cited = tree({
      "m/0001_init.sql": ok,
      "m/0002_drop.sql": "-- DEPRECATED-SINCE: 0001_init.sql\nDROP TABLE a;\n",
    });
    assert.deepEqual(lintMigrations(path.join(cited, "m")), []);
  });

  it("ignores keywords that only appear in comments", () => {
    const root = tree({
      "m/0001_init.sql": `-- we never DROP TABLE or RENAME anything\n/* DROP COLUMN x */\n${ok}`,
    });
    assert.deepEqual(lintMigrations(path.join(root, "m")), []);
    assert.equal(stripComments("a -- x\nb /* y */ c").replace(/\s+/g, " ").trim(), "a b c");
  });

  it("flags modified, deleted or renamed merged migrations but allows additions", () => {
    const v = checkImmutability([
      { status: "A", file: "db/migrations/0002_new.sql" },
      { status: "M", file: "db/migrations/0001_foundations.sql" },
      { status: "D", file: "db/migrations/0001_foundations.sql" },
      { status: "R100", file: "db/migrations/0001_a.sql -> db/migrations/0001_b.sql" },
    ]);
    assert.equal(v.length, 3);
    assert.deepEqual(checkImmutability([{ status: "A", file: "db/migrations/0002_new.sql" }]), []);
  });

  it("passes on the real migrations", () => {
    assert.deepEqual(lintMigrations(path.join(REPO_ROOT, "db", "migrations")), []);
  });
});

describe("pre-push hook (never push to main)", () => {
  const hook = path.join(REPO_ROOT, "scripts", "hooks", "pre-push");
  const run = (/** @type {string} */ stdin) =>
    spawnSync("sh", [hook], { input: stdin, encoding: "utf8" });
  const zero = "0".repeat(40);
  const sha = "a".repeat(40);

  it("rejects pushes to main and master, including a branch deletion", () => {
    for (const ref of ["refs/heads/main", "refs/heads/master"]) {
      const result = run(`refs/heads/feat/x ${sha} ${ref} ${zero}\n`);
      assert.equal(result.status, 1, ref);
      assert.match(result.stderr, /refusing to push/);
    }
    assert.equal(run(`(delete) ${zero} refs/heads/main ${sha}\n`).status, 1);
  });

  it("rejects when main is one of several refs", () => {
    const stdin = `refs/heads/a ${sha} refs/heads/feat/a ${zero}\nrefs/heads/b ${sha} refs/heads/main ${zero}\n`;
    assert.equal(run(stdin).status, 1);
  });

  it("allows feature branches, lookalike names, tags and an empty push", () => {
    for (const ref of [
      "refs/heads/feat/stage-1",
      "refs/heads/fix/main-menu",
      "refs/heads/maintenance",
      "refs/heads/feat/main",
      "refs/tags/main",
    ]) {
      assert.equal(run(`refs/heads/x ${sha} ${ref} ${zero}\n`).status, 0, ref);
    }
    assert.equal(run("").status, 0);
  });

  it("is wired end to end: git blocks a real push to main and allows one to a feature branch", () => {
    const base = mkdtempSync(path.join(tmpdir(), "probbot-git-"));
    temps.push(base);
    const git = (/** @type {string} */ cwd, /** @type {string[]} */ ...args) =>
      spawnSync("git", args, { cwd, encoding: "utf8" });
    const remote = path.join(base, "remote.git");
    const work = path.join(base, "work");
    execFileSync("git", ["init", "--bare", "-b", "main", remote]);
    execFileSync("git", ["init", "-b", "main", work]);
    git(work, "config", "user.email", "t@example.invalid");
    git(work, "config", "user.name", "t");
    git(work, "remote", "add", "origin", remote);
    mkdirSync(path.join(work, "scripts", "hooks"), { recursive: true });
    copyFileSync(hook, path.join(work, "scripts", "hooks", "pre-push"));
    writeFileSync(path.join(work, "f.txt"), "x");
    git(work, "add", ".");
    git(work, "commit", "-m", "init");

    assert.deepEqual(installHooks(work), ["pre-push"]);
    assert.equal(git(work, "config", "core.hooksPath").stdout.trim(), "scripts/hooks");

    const blocked = git(work, "push", "origin", "HEAD:main");
    assert.notEqual(blocked.status, 0);
    assert.match(blocked.stderr, /refusing to push to 'main'/);

    const allowed = git(work, "push", "origin", "HEAD:refs/heads/feat/x");
    assert.equal(allowed.status, 0, allowed.stderr);
  });

  it("installHooks fails loudly when the hook file is missing", () => {
    const root = tree({ "scripts/hooks/other": "" });
    assert.throws(() => installHooks(root), /pre-push is missing/);
  });
});
