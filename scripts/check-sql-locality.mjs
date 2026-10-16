// @ts-check
// CI rule (architecture sections 9.1 S10 and the locked Database rule): SQL and D1 calls live ONLY in
// apps/bot/src/repo and apps/fit/src/footy/repo. Tests, migrations and scripts are not scanned.
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { report, walk } from "./lib/walk.mjs";

const SQL_IN_TEXT = [
  /\bselect\b[^;"'`]{0,300}?\bfrom\b/i,
  /\binsert\s+(or\s+\w+\s+)?into\b/i,
  /\bupdate\s+\w+\s+set\b/i,
  /\bdelete\s+from\b/i,
  /\b(create|drop|alter)\s+(unique\s+)?(table|index|view|trigger)\b/i,
  /\bpragma\s+\w+/i,
];

/** Rule table: where to look, what is exempt, which extra call patterns are forbidden. */
const RULES = [
  {
    include: /^apps\/bot\/src\/.*\.ts$/,
    exempt: /^apps\/bot\/src\/repo\//,
    calls: [/\.prepare\s*\(/, /\.exec\s*\(/, /\bbatch\s*\(\s*\[/],
  },
  {
    include: /^apps\/fit\/src\/.*\.py$/,
    exempt: /^apps\/fit\/src\/footy\/repo\//,
    calls: [/\bimport\s+sqlite3\b/, /\bfrom\s+sqlite3\b/, /\.execute(many|script)?\s*\(/],
  },
];

/** @param {string} line */
function isCommentOnly(line) {
  const t = line.trim();
  return (
    t === "" || t.startsWith("//") || t.startsWith("*") || t.startsWith("/*") || t.startsWith("#")
  );
}

/**
 * @param {string} root repository root
 * @returns {string[]} violations as "file:line: reason"
 */
export function findSqlViolations(root) {
  /** @type {string[]} */
  const violations = [];
  for (const file of walk(root)) {
    const rule = RULES.find((r) => r.include.test(file) && !r.exempt.test(file));
    if (!rule) continue;
    const lines = readFileSync(path.join(root, file), "utf8").split(/\r?\n/);
    lines.forEach((line, i) => {
      if (isCommentOnly(line)) return;
      const quoted = /["'`]/.test(line);
      if (quoted && SQL_IN_TEXT.some((p) => p.test(line))) {
        violations.push(`${file}:${i + 1}: SQL text outside the repo layer`);
      }
      if (rule.calls.some((p) => p.test(line))) {
        violations.push(`${file}:${i + 1}: database call outside the repo layer`);
      }
    });
  }
  return violations;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const root = path.resolve(process.argv[2] ?? path.join(import.meta.dirname, ".."));
  process.exitCode = report("check-sql-locality", findSqlViolations(root));
}
