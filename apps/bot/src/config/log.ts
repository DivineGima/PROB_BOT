/**
 * One JSON line per request (architecture section 9.2). Only whitelisted, non-secret fields are
 * ever logged: request bodies, headers, paths and ids of other chats never reach this function.
 */
export interface RequestLog {
  request_id: string;
  route: "webhook" | "spike" | "other";
  outcome: string;
  update_id?: number;
  error_code?: string;
  duration_ms?: number;
  /** [v3] A KNOWN command name only; arguments are never logged (S15). */
  command?: string;
  [extra: `n_${string}`]: number;
}

export function logRequest(line: RequestLog): void {
  console.log(JSON.stringify(line));
}
