/**
 * Worker environment bindings (type only). Secret values are set with `wrangler secret put`
 * and are read ONLY by the `auth` module (architecture section 6.5); every other module must
 * treat these four names as off limits. `scripts/check-secret-readers.mjs` enforces that in CI.
 */
export interface Env {
  DB: D1Database;
  TELEGRAM_WEBHOOK_SECRET: string;
  WEBHOOK_PATH_SECRET: string;
  ALLOWED_CHAT_ID: string;
  ALLOWED_USER_ID: string;
  /** Bot API token (Worker secret). Read ONLY by the `telegram` module; a missing token fails safe. */
  TELEGRAM_BOT_TOKEN?: string;
  /** "1" enables the Stage 1 CPU spike path; anything else (or unset) keeps it off. */
  SPIKE_ENABLED?: string;
}
