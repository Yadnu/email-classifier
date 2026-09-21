import { redactState } from "@/lib/redact";
import { cycleTheme, formatUpdateStatus, stepIndex } from "@/lib/chrome";
import { describe, expect, it } from "vitest";

describe("redactState", () => {
  it("masks subject and body_excerpt only", () => {
    const out = redactState(
      { subject: "Invoice 12", body_excerpt: "Pay now", spf_result: "pass" },
      true,
    );
    expect(String(out.subject)).toMatch(/^█+$/);
    expect(out.spf_result).toBe("pass");
  });

  it("is a no-op when off", () => {
    const state = { subject: "Hi" };
    expect(redactState(state, false)).toEqual(state);
  });
});

describe("chrome helpers", () => {
  it("cycles theme prefs", () => {
    expect(cycleTheme("system")).toBe("light");
    expect(cycleTheme("light")).toBe("dark");
    expect(cycleTheme("dark")).toBe("system");
  });

  it("wraps list selection", () => {
    expect(stepIndex(3, 2, 1)).toBe(0);
    expect(stepIndex(3, 0, -1)).toBe(2);
  });
});

describe("formatUpdateStatus", () => {
  it("reports gmail counts without inventing rows", () => {
    expect(
      formatUpdateStatus({
        ingest_ok: true,
        ingested_new: 3,
        classified: 8,
        unclassified_remaining: 40,
      }),
    ).toBe("3 new from gmail · 8 classified · 40 waiting");
  });
});
