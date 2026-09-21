import { filterByTime, seriesBucketKey, sliceByIndex } from "@/lib/metrics";
import type { CompactMessage, StatsSeriesPoint } from "@/lib/types";
import { describe, expect, it } from "vitest";

function msg(partial: Partial<CompactMessage>): CompactMessage {
  return {
    id: 1,
    message_id: "m",
    classified_at: "2026-09-21T01:10:00Z",
    category: "spam",
    category_confidence: 0.9,
    spam: true,
    spam_probability: 0.9,
    reply_probability: 0.1,
    total_ms: 300,
    jev_ms: 280,
    cost_usd: 0.00004,
    sender_domain: "ex.test",
    subject: "s",
    gmail_spam: true,
    disagreed_with_gmail: false,
    decision_path: "x",
    model_version: "jev-1.13.0",
    retries: 0,
    rate_limited: false,
    jev_category: "spam",
    credential_request: 0.1,
    brand_impersonation: 0.1,
    ...partial,
  };
}

function pt(bucket: string): StatsSeriesPoint {
  return {
    bucket,
    n: 1,
    counts: { spam: 1 },
    latency_total: { "50": 1, "95": 1, "99": 1 },
    latency_jev: { "50": 1, "95": 1, "99": 1 },
    cost_usd: 0,
    cost_usd_cumulative: 0,
    input_tokens: 0,
    uncertain_n: 0,
    uncertain_rate: 0,
    errors: 0,
    rate_limited: 0,
    retries: 0,
    gmail_agreement: 1,
  };
}

describe("metrics brush filters", () => {
  it("keeps hour keys aligned with stats buckets", () => {
    expect(seriesBucketKey("2026-09-21T01:36:29Z", "hour")).toBe("2026-09-21T01");
  });

  it("filters rows to the brushed series window", () => {
    const rows = [
      msg({ id: 1, classified_at: "2026-09-21T01:10:00Z" }),
      msg({ id: 2, classified_at: "2026-09-21T03:10:00Z" }),
    ];
    const kept = filterByTime(rows, [pt("2026-09-21T01")], "hour");
    expect(kept.map((r) => r.id)).toEqual([1]);
  });

  it("sliceByIndex is inclusive on the end", () => {
    expect(sliceByIndex(["a", "b", "c"], 1, 2)).toEqual(["b", "c"]);
  });
});
