import { percentiles } from "@/lib/percentiles";
import type { CompactMessage } from "@/lib/types";

export type MinutePoint = {
  t: number;
  label: string;
  n: number;
  p95_ms: number | null;
  cost_usd: number;
};

export function lastHourMinutes(nowMs: number, minutes = 60): number[] {
  const last = Math.floor(nowMs / 60_000);
  return Array.from({ length: minutes }, (_, i) => last - (minutes - 1 - i));
}

export function sparklineHour(
  rows: CompactMessage[],
  nowMs: number,
  minutes = 60,
): MinutePoint[] {
  const keys = lastHourMinutes(nowMs, minutes);
  const bins = new Map<number, { latencies: number[]; cost: number }>();
  for (const k of keys) bins.set(k, { latencies: [], cost: 0 });

  for (const row of rows) {
    const ms = Date.parse(row.classified_at);
    if (Number.isNaN(ms)) continue;
    const k = Math.floor(ms / 60_000);
    const bin = bins.get(k);
    if (!bin) continue;
    bin.latencies.push(row.total_ms);
    bin.cost += row.cost_usd;
  }

  return keys.map((k) => {
    const bin = bins.get(k)!;
    const p95 = bin.latencies.length ? percentiles(bin.latencies)[95] : null;
    return {
      t: k * 60_000,
      label: new Date(k * 60_000).toISOString().slice(11, 16),
      n: bin.latencies.length,
      p95_ms: p95,
      cost_usd: bin.cost,
    };
  });
}

export function hourTotals(points: MinutePoint[]): {
  n: number;
  p95_ms: number | null;
  cost_usd: number;
} {
  const latencies: number[] = [];
  let n = 0;
  let cost = 0;
  for (const p of points) {
    n += p.n;
    cost += p.cost_usd;
    if (p.p95_ms != null) latencies.push(p.p95_ms);
  }
  return {
    n,
    p95_ms: latencies.length ? percentiles(latencies)[95] : null,
    cost_usd: cost,
  };
}
