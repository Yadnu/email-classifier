import { prependUnique, rowKey } from "@/lib/live";
import { sparklineHour } from "@/lib/sparkline";
import type { CompactMessage } from "@/lib/types";
import { describe, expect, it } from "vitest";

function row(partial: Partial<CompactMessage> & Pick<CompactMessage, "id" | "message_id">): CompactMessage {
  return {
    classified_at: "2026-09-21T01:00:00Z",
    category: "spam",
    category_confidence: 0.9,
    spam: true,
    spam_probability: 0.94,
    reply_probability: 0.02,
    total_ms: 300,
    jev_ms: 280,
    cost_usd: 0.00004,
    sender_domain: "example.test",
    subject: "hello",
    gmail_spam: true,
    disagreed_with_gmail: false,
    decision_path: "is_spam_noul",
    model_version: "jev-1.13.0",
    retries: 0,
    rate_limited: false,
    jev_category: "spam",
    credential_request: 0.1,
    brand_impersonation: 0.1,
    ...partial,
  };
}

describe("prependUnique", () => {
  it("puts newest first and drops duplicates", () => {
    const a = row({ id: 1, message_id: "a" });
    const b = row({ id: 2, message_id: "b" });
    const merged = prependUnique([a], [b, a]);
    expect(merged.map(rowKey)).toEqual(["b:2", "a:1"]);
  });
});

describe("sparklineHour", () => {
  it("counts a row in its minute and leaves empty minutes at 0", () => {
    const now = Date.parse("2026-09-21T12:00:30Z");
    const classified = "2026-09-21T11:59:10Z";
    const points = sparklineHour(
      [row({ id: 1, message_id: "m", classified_at: classified, total_ms: 322, cost_usd: 0.0001 })],
      now,
      3,
    );
    expect(points).toHaveLength(3);
    expect(points.map((p) => p.n)).toEqual([0, 1, 0]);
    expect(points[1].p95_ms).toBe(322);
    expect(points[1].cost_usd).toBeCloseTo(0.0001);
  });
});
