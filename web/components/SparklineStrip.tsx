"use client";

import { formatCostUsd, formatMs } from "@/lib/format";
import { hourTotals, type MinutePoint } from "@/lib/sparkline";
import { Line, LineChart, ResponsiveContainer } from "recharts";

function Spark({
  data,
  dataKey,
  caption,
  value,
}: {
  data: MinutePoint[];
  dataKey: "n" | "p95_ms" | "cost_usd";
  caption: string;
  value: string;
}) {
  return (
    <div className="min-w-0 border border-[var(--line)] bg-[var(--paper-2)] px-3 py-2">
      <div className="flex items-baseline justify-between gap-2">
        <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--muted)]">
          {caption}
        </p>
        <p className="font-mono text-sm tabular-nums">{value}</p>
      </div>
      <div className="mt-1 h-10 text-[var(--ink)]">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 4, right: 2, bottom: 0, left: 2 }}>
            <Line
              type="monotone"
              dataKey={dataKey}
              stroke="currentColor"
              strokeWidth={1.4}
              dot={false}
              isAnimationActive={false}
              connectNulls
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export function SparklineStrip({ points }: { points: MinutePoint[] }) {
  const totals = hourTotals(points);
  return (
    <section aria-label="Last 60 minutes" className="grid gap-2 sm:grid-cols-3">
      <Spark
        data={points}
        dataKey="n"
        caption="throughput / min"
        value={`${totals.n} in 60 min`}
      />
      <Spark
        data={points}
        dataKey="p95_ms"
        caption="p95 latency"
        value={totals.p95_ms == null ? "—" : formatMs(totals.p95_ms)}
      />
      <Spark
        data={points}
        dataKey="cost_usd"
        caption="cost / hour"
        value={formatCostUsd(totals.cost_usd)}
      />
    </section>
  );
}
