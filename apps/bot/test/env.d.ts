import type { D1Migration } from "@cloudflare/vitest-plugin";
import type { Env as AppEnv } from "../src/config/env";

// Types the `env` imported from "cloudflare:workers" in tests (the global Cloudflare.Env).
declare global {
  namespace Cloudflare {
    interface Env extends AppEnv {
      /** Migrations read by vitest.config.ts and applied in test/apply-migrations.ts. */
      TEST_MIGRATIONS: D1Migration[];
    }
  }
}
