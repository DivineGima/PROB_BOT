import { describe, expect, it } from "vitest";
import vectors from "../../../packages/contracts/golden/strongest.json";
import {
  bar,
  callHit,
  callText,
  DISPLAY,
  favouriteLabel,
  favouriteOf,
  filledCells,
  grade,
  omissionIcon,
  pct0,
  strongestCall,
  verdictIcon,
} from "../src/format/display";

/** [v4] Display rules (architecture 4, ADR-053, ADR-056, ADR-057). */

describe("the shared strongest-call vectors (Python made them; TypeScript must agree)", () => {
  it("has the tricky cases", () => {
    expect(vectors.cases.length).toBeGreaterThanOrEqual(50);
    const notes = vectors.cases.map((c) => (c as { note?: string }).note ?? "").join(" ");
    expect(notes).toContain("tie");
  });

  for (const [i, c] of vectors.cases.entries()) {
    it(`case ${i}`, () => {
      const p1x2 = c.p1x2 as [number, number, number];
      const call = strongestCall(p1x2, c.overs);
      expect(call.key).toBe(c.expected.key);
      expect(Math.abs(call.p - c.expected.p)).toBeLessThanOrEqual(1e-9);
      expect(favouriteOf(p1x2).outcome).toBe(c.expected.favourite);
      expect(filledCells(p1x2[0])).toBe(c.expected.home_cells);
    });
  }
});

describe("bars and percentages", () => {
  it("rounds half up to 10 cells and clamps", () => {
    expect(filledCells(0.44)).toBe(4);
    expect(filledCells(0.45)).toBe(5);
    expect(filledCells(0.04)).toBe(0);
    expect(filledCells(1.2)).toBe(10);
    expect(filledCells(-1)).toBe(0);
    expect(filledCells(Number.NaN)).toBe(0);
    expect(bar(0.3, DISPLAY.bar.away)).toBe("🟥🟥🟥⬜⬜⬜⬜⬜⬜⬜");
  });

  it("shows whole percents", () => {
    expect(pct0(0.444)).toBe("44%");
    expect(pct0(0.445)).toBe("45%");
    expect(pct0(Number.NaN)).toBe("n/a");
  });
});

describe("labels, the strongest call and grades", () => {
  it("labels a favourite at 60% and 50%", () => {
    expect(favouriteLabel(0.6)).toBe("💪 clear favourite");
    expect(favouriteLabel(0.59)).toBe("👍 slight favourite");
    expect(favouriteLabel(0.5)).toBe("👍 slight favourite");
    expect(favouriteLabel(0.49)).toBe("🤷 open game");
  });

  it("never picks the near-certain 0.5, 4.5 or 5.5 lines", () => {
    const call = strongestCall([0.4, 0.3, 0.3], [0.99, 0.65, 0.5, 0.3, 0.02, 0.01]);
    expect(call.key).toBe("under_3.5");
    expect(call.p).toBeCloseTo(0.7, 12);
  });

  it("words each call and judges it on the 90-minute score", () => {
    expect(callText("away", "A", "Bayern")).toBe("Bayern win");
    expect(callText("over_1.5", "A", "B")).toBe("Over 1.5 goals (2+)");
    expect(callText("under_3.5", "A", "B")).toBe("Under 3.5 goals (3 or fewer)");
    expect(callHit("over_1.5", [1, 1])).toBe(true);
    expect(callHit("over_1.5", [1, 0])).toBe(false);
    expect(callHit("under_3.5", [2, 1])).toBe(true);
    expect(callHit("under_3.5", [2, 2])).toBe(false);
    expect(callHit("draw", [0, 0])).toBe(true);
    expect(callHit("home", [0, 1])).toBe(false);
  });

  it("grades an RPS", () => {
    expect(grade(0.04)).toBe("🟢 good");
    expect(grade(0.2)).toBe("🟡 fair");
    expect(grade(0.49)).toBe("🔴 poor");
    expect(grade(null)).toBe("n/a");
  });

  it("has an icon for every verdict and every omission reason", () => {
    for (const v of ["ok", "DRIFT", "INSUFFICIENT_HISTORY", "NO_MODEL"]) {
      expect(verdictIcon(v)).not.toBe("❔");
    }
    expect(omissionIcon("NO_FORECAST")).toBe("❓");
    expect(omissionIcon("SOMETHING_NEW")).toBe("❔");
  });
});
