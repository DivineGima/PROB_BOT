// @ts-check
// CI rule (architecture section 6.5, claude.md "Auth"): only the `auth` module reads the webhook
// secrets and the allowlist. The Env type declaration in config/env.ts is the one exemption.
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { report, walk } from "./lib/walk.mjs";

const NAMES = /\b(WEBHOOK_PATH_SECRET|TELEGRAM_WEBHOOK_SECRET|ALLOWED_CHAT_ID|ALLOWED_USER_ID)\b/;
const SCANNED = /^apps\/bot\/src\/.*\.ts$/;
const EXEMPT = /^apps\/bot\/src\/(auth\/|config\/env\.ts$)/;

/**
 * @param {string} root
 * @returns {string[]}
 */
export function findSecretReaders(root) {
  /** @type {string[]} */
  const violations = [];
  for (const file of walk(root)) {
    if (!SCANNED.test(file) || EXEMPT.test(file)) continue;
    readFileSync(path.join(root, file), "utf8")
      .split(/\r?\n/)
      .forEach((line, i) => {
        if (NAMES.test(line))
          violations.push(`${file}:${i + 1}: reads an auth secret outside auth/`);
      });
  }
  return violations;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const root = path.resolve(process.argv[2] ?? path.join(import.meta.dirname, ".."));
  process.exitCode = report("check-secret-readers", findSecretReaders(root));
}
