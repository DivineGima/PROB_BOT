import { applyD1Migrations } from "cloudflare:test";
import { env } from "cloudflare:workers";

// Applies db/migrations to the per-file local D1 before each test file (the real schema owner).
await applyD1Migrations(env.DB, env.TEST_MIGRATIONS);
