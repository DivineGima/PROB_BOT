import path from "node:path";
import { cloudflareTest, readD1Migrations } from "@cloudflare/vitest-plugin";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [
    cloudflareTest(async () => {
      const migrations = await readD1Migrations(
        path.join(import.meta.dirname, "../../db/migrations"),
      );
      return {
        wrangler: { configPath: "./wrangler.toml" },
        miniflare: {
          bindings: {
            TEST_MIGRATIONS: migrations,
            // Test-only secrets, never real values. 24+ chars, A-Za-z0-9_-.
            WEBHOOK_PATH_SECRET: "test-path-secret-0123456789",
            TELEGRAM_WEBHOOK_SECRET: "test-header-secret-0123456789",
            ALLOWED_CHAT_ID: "1001",
            ALLOWED_USER_ID: "1001",
            SPIKE_ENABLED: "1",
          },
        },
      };
    }),
  ],
  test: {
    setupFiles: ["./test/apply-migrations.ts"],
  },
});
