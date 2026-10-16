// @ts-check
// CI rule (NFR-09, ADR-025): no raw source data is ever committed. Tests use synthetic data.
// Fails on any data-looking file above the size threshold outside packages/contracts and data/,
// and on ANY .csv or database file outside packages/contracts.
import { statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { report, walk } from "./lib/walk.mjs";

export const MAX_DATA_BYTES = 100 * 1024;
const DATA_EXTENSIONS = /\.(csv|json|ndjson|jsonl|tsv|parquet|xlsx?)$/i;
const ALWAYS_FORBIDDEN = /\.(csv|tsv|parquet|xlsx?|sqlite3?|db)$/i;
const LOCKFILES = new Set(["package-lock.json"]);
const ALLOWED_DIRS = /^(packages\/contracts\/|data\/)/;
const CONTRACTS_ONLY = /^packages\/contracts\//;

/**
 * @param {string} root
 * @returns {string[]}
 */
export function findDataFiles(root) {
  /** @type {string[]} */
  const violations = [];
  for (const file of walk(root)) {
    const base = path.posix.basename(file);
    if (LOCKFILES.has(base)) continue;
    if (ALWAYS_FORBIDDEN.test(file) && !CONTRACTS_ONLY.test(file)) {
      violations.push(`${file}: data/database files are not allowed in the repo`);
      continue;
    }
    if (DATA_EXTENSIONS.test(file) && !ALLOWED_DIRS.test(file)) {
      const size = statSync(path.join(root, file)).size;
      if (size > MAX_DATA_BYTES) {
        violations.push(
          `${file}: ${size} bytes exceeds ${MAX_DATA_BYTES} for a data file outside data/`,
        );
      }
    }
  }
  return violations;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const root = path.resolve(process.argv[2] ?? path.join(import.meta.dirname, ".."));
  process.exitCode = report("check-no-data-files", findDataFiles(root));
}
