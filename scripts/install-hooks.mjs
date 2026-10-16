// @ts-check
// Points git at the committed hooks in scripts/hooks (claude.md section 4: "Install the committed
// pre-push hook"). Idempotent. Run once per clone: `npm run hooks:install`.
import { execFileSync } from "node:child_process";
import { chmodSync, existsSync, readdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const HOOKS_DIR = "scripts/hooks";

/**
 * @param {string} repoRoot
 * @returns {string[]} names of the hooks now active
 */
export function installHooks(repoRoot) {
  const dir = path.join(repoRoot, HOOKS_DIR);
  if (!existsSync(path.join(dir, "pre-push"))) {
    throw new Error(`${HOOKS_DIR}/pre-push is missing`);
  }
  const hooks = readdirSync(dir);
  for (const name of hooks) {
    // No effect on Windows, required on Linux/macOS for git to run the hook.
    chmodSync(path.join(dir, name), 0o755);
  }
  execFileSync("git", ["config", "core.hooksPath", HOOKS_DIR], { cwd: repoRoot });
  return hooks;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const root = path.resolve(import.meta.dirname, "..");
  console.log(`hooks installed from ${HOOKS_DIR}: ${installHooks(root).join(", ")}`);
}
