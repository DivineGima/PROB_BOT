import { describe, expect, it } from "vitest";
import vectors from "../../../packages/contracts/golden/normalise.json";
import { normaliseName } from "../src/commands/normalise";

/**
 * The TypeScript normaliser gives the Python reference's output on the shared vectors
 * (architecture 3, section 6.10; essentials 3 step 3). pytest checks the same file against
 * `footy/aliases/normalise.py` (`apps/fit/tests/test_bot_contracts.py`).
 */
describe("normaliseName", () => {
  it.each(vectors.cases)("normalises %j like the Python reference", ({ input, expected }) => {
    expect(normaliseName(input)).toBe(expected);
  });

  it("is idempotent on its own output", () => {
    for (const { expected } of vectors.cases) {
      expect(normaliseName(expected)).toBe(expected);
    }
  });
});
