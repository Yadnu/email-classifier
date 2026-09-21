import { binaryScores } from "@/lib/scores";
import { describe, expect, it } from "vitest";

describe("binaryScores", () => {
  it("counts one false positive", () => {
    const s = binaryScores([true, false, false], [true, true, false]);
    expect(s.fp).toBe(1);
    expect(s.tp).toBe(1);
    expect(s.tn).toBe(1);
    expect(s.precision).toBeCloseTo(0.5);
    expect(s.recall).toBe(1);
  });
});
