// @ts-check
import { readdirSync, statSync } from "node:fs";
import path from "node:path";

/** Directories that never hold project source (dependencies, caches, build output). */
export const SKIP_DIRS = new Set([
  ".git",
  "node_modules",
  ".venv",
  ".wrangler",
  ".measurements",
  "__pycache__",
  ".pytest_cache",
  ".mypy_cache",
  ".ruff_cache",
  "dist",
  "coverage",
]);

/**
 * Recursively lists files under `dir`, skipping SKIP_DIRS. Paths are returned relative to `root`
 * with forward slashes so rules behave the same on Windows and Linux.
 * @param {string} root
 * @param {string} [dir]
 * @returns {string[]}
 */
export function walk(root, dir = root) {
  /** @type {string[]} */
  const out = [];
  let entries;
  try {
    entries = readdirSync(dir, { withFileTypes: true });
  } catch {
    return out;
  }
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (!SKIP_DIRS.has(entry.name)) out.push(...walk(root, full));
    } else if (entry.isFile()) {
      out.push(path.relative(root, full).split(path.sep).join("/"));
    }
  }
  return out.sort();
}

/** @param {string} file */
export const sizeOf = (file) => statSync(file).size;

/**
 * Runs a check's CLI wrapper: prints violations and sets the exit code.
 * @param {string} name
 * @param {string[]} violations
 */
export function report(name, violations) {
  if (violations.length === 0) {
    console.log(`${name}: ok`);
    return 0;
  }
  console.error(`${name}: ${violations.length} violation(s)`);
  for (const v of violations) console.error(`  - ${v}`);
  return 1;
}
