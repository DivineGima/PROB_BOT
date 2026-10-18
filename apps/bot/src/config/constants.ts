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

/** Screener file limits (section 3.2, 6.1). The cap is ours: Telegram would allow far more. */
export const MAX_FILE_BYTES = 256 * 1024;
/** A prediction is only made for a kickoff strictly in the future and at most this far away. */
export const MAX_KICKOFF_AHEAD_MS = 48 * 60 * 60 * 1000;
/** Replies are split at match-block boundaries below Telegram's 4,096-character limit (section 8.8). */
export const MAX_REPLY_CHARS = 3900;
/** The STALE MODELS banner age when the run's config does not say (ADR-015). */
export const DEFAULT_STALE_HOURS = 36;
/** An upload still `received` this long was acknowledged and never answered (ADR-029). */
export const STUCK_UPLOAD_MINUTES = 10;
/** The watchdog wants forecasts for today and the next day when fixtures are scheduled (ADR-015). */
export const WATCHDOG_FORECAST_DAYS = 2;
/** At most this many validation paths are shown for a rejected file (section 6.3). */
export const MAX_ERROR_PATHS = 5;

export const TELEGRAM_API_BASE = "https://api.telegram.org";
/** A 429 with a longer `retry_after` than this is not waited out (section 9.4). */
export const MAX_RETRY_AFTER_SECONDS = 5;
