-- 0007_event_delivery.sql
-- Stage 7 (architecture sections 5.6 and 9.2): which alert events have reached Telegram.
-- Additive-first: one nullable column; nothing is renamed or dropped.
-- Timestamps are UTC ISO-8601 text.

-- Set by the fit job's alert delivery once the message went out. NULL means "not sent yet" (every
-- event written before this migration is NULL too; the delivery step ignores events older than
-- 48 hours, so old alerts are never replayed).
ALTER TABLE events ADD COLUMN delivered_at TEXT;

-- No index on it: the delivery step reads the last 48 hours through `idx_events_at`, a small range.
