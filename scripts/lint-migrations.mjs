// @ts-check
// CI migration lint (architecture section 9.3 and the locked Data-model rule):
//  * files are named NNNN_name.sql, numbered 0001.. without gaps or duplicates;
//  * additive-first: DROP / RENAME never appears in the same migration that adds a replacement
//    (CREATE TABLE / ADD COLUMN / CREATE INDEX), and a removal must cite the migration that
//    deprecated the thing, with a `-- DEPRECATED-SINCE: NNNN_name.sql` comment;
//  * merged migrations are immutable: with --base <ref>, an existing file that was modified,
//    deleted or renamed relative to <ref> is an error.
import { execFileSync } from "node:child_process";
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { report } from "./lib/walk.mjs";

const NAME = /^(\d{4})_[a-z0-9_]+\.sql$/;
const REMOVAL =
  /\b(drop\s+(table|column|index|view|trigger)|rename\s+(to|column)|rename\s+table)\b/i;
const ADDITION = /\b(create\s+(unique\s+)?(table|index|view|trigger)|add\s+column)\b/i;
const DEPRECATION_CITE = /--\s*DEPRECATED-SINCE:\s*\d{4}_[a-z0-9_]+\.sql/;

/**
 * Removes `-- line` and block comments so keywords inside comments do not count.
 * @param {string} sql
 */
export function stripComments(sql) {
  return sql.replace(/\/\*[\s\S]*?\*\//g, " ").replace(/--[^\n]*/g, " ");
}

/**
 * @param {string} dir migrations directory
 * @returns {string[]}
 */
export function lintMigrations(dir) {
  /** @type {string[]} */
  const violations = [];
  const files = readdirSync(dir)
    .filter((f) => f.endsWith(".sql"))
    .sort();
  if (files.length === 0) violations.push(`${dir}: no migrations found`);

  files.forEach((file, index) => {
    const match = NAME.exec(file);
    if (!match) {
      violations.push(`${file}: name must look like 0001_description.sql`);
      return;
    }
    if (Number(match[1]) !== index + 1) {
      violations.push(
        `${file}: expected number ${String(index + 1).padStart(4, "0")} (gap or duplicate)`,
      );
    }
    const raw = readFileSync(path.join(dir, file), "utf8");
    const code = stripComments(raw);
    if (REMOVAL.test(code)) {
      if (ADDITION.test(code)) {
        violations.push(`${file}: drops/renames in the same migration that adds a replacement`);
      }
      if (!DEPRECATION_CITE.test(raw)) {
        violations.push(
          `${file}: removal must cite its deprecation with "-- DEPRECATED-SINCE: NNNN_name.sql"`,
        );
      }
    }
  });
  return violations;
}

/**
 * @param {{status: string, file: string}[]} changes `git diff --name-status` entries under the migrations dir
 * @returns {string[]}
 */
export function checkImmutability(changes) {
  return changes
    .filter((c) => !c.status.startsWith("A"))
    .map(
      (c) =>
        `${c.file}: merged migrations are immutable (git status ${c.status}); add a new migration instead`,
    );
}

/**
 * @param {string} repoRoot
 * @param {string} base git ref to compare against, e.g. origin/main
 * @param {string} migrationsRel
 */
export function changesSince(repoRoot, base, migrationsRel) {
  const out = execFileSync(
    "git",
    ["diff", "--name-status", `${base}...HEAD`, "--", migrationsRel],
    { cwd: repoRoot, encoding: "utf8" },
  );
  return out
    .split("\n")
    .filter(Boolean)
    .map((line) => {
      const [status = "", ...rest] = line.split("\t");
      return { status, file: rest.join(" -> ") };
    });
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2);
  const baseIdx = args.indexOf("--base");
  const base = baseIdx >= 0 ? args[baseIdx + 1] : undefined;
  const repoRoot = path.resolve(import.meta.dirname, "..");
  const rel = "db/migrations";
  const violations = lintMigrations(path.join(repoRoot, rel));
  if (base) violations.push(...checkImmutability(changesSince(repoRoot, base, rel)));
  process.exitCode = report("lint-migrations", violations);
}
