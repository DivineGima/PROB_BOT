/** Error catalogue shared by code, tests, replies and logs (architecture section 6.6). */
export const ERROR_CODES = {
  E_NOT_JSON_FILE: "E_NOT_JSON_FILE",
  E_TOO_LARGE: "E_TOO_LARGE",
  E_DOWNLOAD_FAILED: "E_DOWNLOAD_FAILED",
  E_PARSE: "E_PARSE",
  E_SCHEMA_VERSION: "E_SCHEMA_VERSION",
  E_SCHEMA_INVALID: "E_SCHEMA_INVALID",
  E_NO_RUN: "E_NO_RUN",
  E_INTERNAL: "E_INTERNAL",
  E_AUTH: "E_AUTH",
} as const;

export type ErrorCode = (typeof ERROR_CODES)[keyof typeof ERROR_CODES];

/** Expected failures use Result; exceptions are reserved for bugs (section 6.6). */
export type Result<T, E> = { ok: true; value: T } | { ok: false; error: E };

export const ok = <T>(value: T): Result<T, never> => ({ ok: true, value });
export const err = <E>(error: E): Result<never, E> => ({ ok: false, error });
