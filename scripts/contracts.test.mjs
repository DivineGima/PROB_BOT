// @ts-check
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";
import { generate, SCHEMA_PATH } from "./gen-screener-schema.mjs";

describe("screener_v1.schema.json", () => {
  it("is exactly what the Zod schema the Worker validates with produces", () => {
    const committed = JSON.parse(readFileSync(SCHEMA_PATH, "utf8"));
    assert.deepEqual(
      committed,
      generate(),
      "regenerate with: node scripts/gen-screener-schema.mjs && npx biome format --write packages/contracts",
    );
  });

  it("states the contract's hard limits", () => {
    const schema = /** @type {any} */ (generate());
    assert.equal(schema.properties.matches.maxItems, 100);
    assert.equal(schema.properties.excluded.maxItems, 200);
    assert.equal(schema.properties.schema_version.const, 1);
    assert.deepEqual(schema.properties.matches.items.properties.competition.enum, [
      "EPL",
      "LL",
      "BL",
      "SA",
      "L1",
      "UCL",
      "ERE",
      "PPL",
      "CHA",
      "SPL",
    ]);
    assert.ok(schema.required.includes("matches"));
  });
});
