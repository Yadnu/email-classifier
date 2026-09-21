import type { CompactMessage, StatsSeriesPoint } from "@/lib/types";

export type Bucket = "minute" | "hour" | "day";

export const CATEGORY_STACK = [
  "legitimate",
  "promotional",
  "spam",
  "phishing",
  "uncertain",
  "other",
] as const;

export const CATEGORY_COLORS: Record<string, string> = {
  legitimate: "#6e6758",
  promotional: "#3a7ca5",
  spam: "#d28a2a",
  phishing: "#b42318",
  uncertain: "#888888",
  other: "#7a6d8a",
};

export function seriesBucketKey(iso: string, bucket: Bucket): string {
  if (bucket === "day") return iso.slice(0, 10);
  if (bucket === "minute") return iso.slice(0, 16);
  return iso.slice(0, 13);
}

export function sliceByIndex<T>(items: T[], start?: number, end?: number): T[] {
  if (start == null || end == null) return items;
  return items.slice(start, end + 1);
}

export function filterByTime(
  rows: CompactMessage[],
  points: StatsSeriesPoint[],
  bucket: Bucket,
): CompactMessage[] {
  if (!points.length) return rows;
  const start = points[0].bucket;
  const end = points[points.length - 1].bucket;
  return rows.filter((row) => {
    const key = seriesBucketKey(row.classified_at, bucket);
    return key >= start && key <= end;
  });
}

export function filterByMs(
  rows: CompactMessage[],
  lo: number,
  hi: number | null,
): CompactMessage[] {
  return rows.filter((row) =>
    hi == null ? row.total_ms >= lo : row.total_ms >= lo && row.total_ms < hi,
  );
}

export function filterByRange(
  rows: CompactMessage[],
  lo: number,
  hi: number,
  pick: (row: CompactMessage) => number,
): CompactMessage[] {
  return rows.filter((row) => {
    const v = pick(row);
    return v >= lo && v < hi;
  });
}

export function flattenVolume(points: StatsSeriesPoint[]) {
  return points.map((p) => ({
    bucket: p.bucket,
    ...Object.fromEntries(CATEGORY_STACK.map((c) => [c, p.counts[c] ?? 0])),
    n: p.n,
    p50: p.latency_total["50"],
    p95: p.latency_total["95"],
    p99: p.latency_total["99"],
    jev50: p.latency_jev["50"],
    jev95: p.latency_jev["95"],
    jev99: p.latency_jev["99"],
    cost: p.cost_usd,
    costCum: p.cost_usd_cumulative,
    tokens: p.input_tokens,
    uncertain: p.uncertain_rate,
    agree: p.gmail_agreement,
    errors: p.errors,
    rate_limited: p.rate_limited,
    retries: p.retries,
  }));
}
