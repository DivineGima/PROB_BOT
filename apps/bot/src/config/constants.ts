/** Route prefixes. The secret path segment follows the prefix (section 6.2). */
export const WEBHOOK_PATH_PREFIX = "/tg/";
/** Stage 1 CPU spike (ADR-013). Deprecated once the Stage 1 gate is recorded; never deleted outright. */
export const SPIKE_PATH_PREFIX = "/spike/";

export const SECRET_HEADER = "x-telegram-bot-api-secret-token";

/**
 * Secrets must look like Telegram secret tokens (A-Z a-z 0-9 _ -) and be at least this long.
 * An empty or short secret would make the path or header check trivially satisfiable, so a
 * misconfigured Worker fails closed (everything answers 404/401).
 */
export const MIN_SECRET_LENGTH = 16;
export const MAX_SECRET_LENGTH = 256;

/** Telegram updates are small; anything larger is not from Telegram. */
export const MAX_UPDATE_BODY_BYTES = 64 * 1024;
/** The spike payload (60 matches + model blobs, about 250 KB) is far larger than an update. */
export const MAX_SPIKE_BODY_BYTES = 1024 * 1024;
