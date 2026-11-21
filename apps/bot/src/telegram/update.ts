/**
 * Telegram update helpers that carry no secrets: the update kind for the `processed_updates` row
 * and the document fields of an upload. Sending and downloading live in `client.ts`.
 */
/** [v3] `command`: a text whose first character is `/` (architecture 3, section 6.2). */
export type UpdateKind = "document" | "command" | "text" | "other";

export function classifyUpdate(update: unknown): UpdateKind {
  if (typeof update !== "object" || update === null) return "other";
  const message = (update as { message?: unknown }).message;
  if (typeof message !== "object" || message === null) return "other";
  const fields = message as { document?: unknown; text?: unknown };
  if (typeof fields.document === "object" && fields.document !== null) return "document";
  if (typeof fields.text === "string") return fields.text.startsWith("/") ? "command" : "text";
  return "other";
}

/** The text of a message (at most 4,096 characters, Telegram's own limit), or null. */
export function extractText(update: unknown): string | null {
  if (typeof update !== "object" || update === null) return null;
  const message = (update as { message?: unknown }).message;
  if (typeof message !== "object" || message === null) return null;
  const value = (message as { text?: unknown }).text;
  return typeof value === "string" ? value.slice(0, 4096) : null;
}

export interface DocumentFields {
  fileId: string;
  fileUniqueId?: string;
  fileName?: string;
  mimeType?: string;
  fileSize?: number;
}

const text = (value: unknown, max: number): string | undefined =>
  typeof value === "string" && value.length > 0 ? value.slice(0, max) : undefined;

/** The document of a message, or null. Fields are length-capped; nothing here is trusted yet. */
export function extractDocument(update: unknown): DocumentFields | null {
  if (typeof update !== "object" || update === null) return null;
  const message = (update as { message?: unknown }).message;
  if (typeof message !== "object" || message === null) return null;
  const doc = (message as { document?: unknown }).document;
  if (typeof doc !== "object" || doc === null) return null;
  const d = doc as Record<string, unknown>;
  const fileId = text(d.file_id, 256);
  if (!fileId) return null;
  const fields: DocumentFields = { fileId };
  const unique = text(d.file_unique_id, 128);
  const name = text(d.file_name, 256);
  const mime = text(d.mime_type, 128);
  if (unique !== undefined) fields.fileUniqueId = unique;
  if (name !== undefined) fields.fileName = name;
  if (mime !== undefined) fields.mimeType = mime;
  if (typeof d.file_size === "number" && Number.isFinite(d.file_size))
    fields.fileSize = d.file_size;
  return fields;
}
