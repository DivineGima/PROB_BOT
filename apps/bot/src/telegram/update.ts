/**
 * Telegram update helpers that carry no secrets. Stage 1 only needs the update kind for the
 * `processed_updates` row; send/download and 429 handling arrive in Stage 5.
 */
export type UpdateKind = "document" | "text" | "other";

export function classifyUpdate(update: unknown): UpdateKind {
  if (typeof update !== "object" || update === null) return "other";
  const message = (update as { message?: unknown }).message;
  if (typeof message !== "object" || message === null) return "other";
  const fields = message as { document?: unknown; text?: unknown };
  if (typeof fields.document === "object" && fields.document !== null) return "document";
  if (typeof fields.text === "string") return "text";
  return "other";
}
