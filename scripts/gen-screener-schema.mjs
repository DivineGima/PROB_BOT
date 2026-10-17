// @ts-check
// Generates packages/contracts/screener_v1.schema.json from the Zod schema the Worker validates
// with (architecture section 6.1), so the JSON Schema copy can never describe a different file
// format. `node scripts/gen-screener-schema.mjs` writes it; the script test fails if the committed
// copy differs from what the Zod schema produces. Run `npx biome format --write` on the output.
import { writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { z } from "zod";
import { screenerV1Schema } from "../apps/bot/src/intake/schema.ts";

export const SCHEMA_PATH = path.join(
  import.meta.dirname,
  "..",
  "packages",
  "contracts",
  "screener_v1.schema.json",
);

/** The JSON Schema (draft 2020-12) of the screener file, version 1. */
export function generate() {
  return z.toJSONSchema(screenerV1Schema, { target: "draft-2020-12", io: "input" });
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  writeFileSync(SCHEMA_PATH, `${JSON.stringify(generate(), null, 2)}\n`);
  console.log(`wrote ${path.relative(process.cwd(), SCHEMA_PATH)}`);
}
