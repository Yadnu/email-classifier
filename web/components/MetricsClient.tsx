"use client";

import { ChartFrame, StatChip } from "@/components/metrics/ChartFrame";
import { MessageTable } from "@/components/MessageTable";
import { ApiDown, EmptyState, PageSkeleton } from "@/components/States";
import { swrFetcher } from "@/lib/api";
import { formatCostUsd, formatMs, formatProb, formatTokens } from "@/lib/format";
import {
  CATEGORY_COLORS,
  CATEGORY_STACK,
  filterByTime,
  flattenVolume,
  sliceByIndex,
  type Bucket,
} from "@/lib/metrics";
import type { CalibrationResponse, CompactMessage, StatsResponse } from "@/lib/types";
import { useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  Brush,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import useSWR from "swr";

type ListResponse = { items: CompactMessage[]; next_cursor: string | null };
type BrushIdx = { startIndex?: number; endIndex?: number };

const axis = { fontSize: 11, fill: "var(--muted)" };
const grid = { stroke: "var(--line)", strokeDasharray: "3 3" };
const tipStyle = { background: "var(--paper)", border: "1px solid var(--line)", fontSize: 11 };

function num(v: unknown): number {
  if (typeof v === "number") return v;
  if (Array.isArray(v)) return Number(v[0] ?? 0);
  return Number(v ?? 0);
}

export function MetricsClient() {
  const [bucket, setBucket] = useState<Bucket>("hour");
  const [timeBrush, setTimeBrush] = useState<BrushIdx>({});
  const [latBrush, setLatBrush] = useState<BrushIdx>({});
  const [confBrush, setConfBrush] = useState<BrushIdx>({});
  const [calBrush, setCalBrush] = useState<BrushIdx>({});

  const { data: stats, error, isLoading } = useSWR<StatsResponse>(
    `/api/stats?bucket=${bucket}`,
    swrFetcher,
  );
  const { data: cal } = useSWR<CalibrationResponse>("/api/calibration", swrFetcher);
  const { data: list } = useSWR<ListResponse>("/api/messages?limit=200", swrFetcher);

  const series = stats?.series ?? [];
  const timeSlice = sliceByIndex(series, timeBrush.startIndex, timeBrush.endIndex);
  const volume = flattenVolume(series);

  const latBins = stats?.latency_histogram ?? [];
  const latSlice = sliceByIndex(latBins, latBrush.startIndex, latBrush.endIndex);
  const confBins = stats?.confidence_histogram ?? [];
  const confSlice = sliceByIndex(confBins, confBrush.startIndex, confBrush.endIndex);
  const calBins = (cal?.spam ?? []).filter((b) => b.n > 0);
  const calSlice = sliceByIndex(calBins, calBrush.startIndex, calBrush.endIndex);

  const filtered = useMemo(() => {
    let rows = list?.items ?? [];
    if (timeSlice.length && timeSlice.length !== series.length) {
      rows = filterByTime(rows, timeSlice, bucket);
    }
    if (latSlice.length && latSlice.length !== latBins.length) {
      rows = rows.filter((r) =>
        latSlice.some((bin) =>
          bin.hi == null ? r.total_ms >= bin.lo : r.total_ms >= bin.lo && r.total_ms < bin.hi,
        ),
      );
    }
    if (confSlice.length && confSlice.length !== confBins.length) {
      rows = rows.filter((r) =>
        confSlice.some((bin) => r.category_confidence >= bin.lo && r.category_confidence < bin.hi),
      );
    }
    if (calSlice.length && calSlice.length !== calBins.length) {
      rows = rows.filter((r) =>
        calSlice.some((bin) => r.spam_probability >= bin.lo && r.spam_probability < bin.hi),
      );
    }
    return rows;
  }, [
    list?.items,
    timeSlice,
    series.length,
    bucket,
    latSlice,
    latBins.length,
    confSlice,
    confBins.length,
    calSlice,
    calBins.length,
  ]);

  const onTime = (s: BrushIdx) => setTimeBrush({ startIndex: s.startIndex, endIndex: s.endIndex });

  if (error) {
    return <ApiDown />;
  }
  if (isLoading || !stats) {
    return <PageSkeleton />;
  }
  if (stats.n === 0) {
    return (
      <EmptyState>
        No classifications in this range. Press{" "}
        <span className="font-mono">update</span> to classify real Gmail.
      </EmptyState>
    );
  }

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-[var(--muted)]">plates</p>
          <h1 className="font-display text-4xl tracking-tight">Metrics</h1>
          <p className="mt-1 max-w-2xl text-sm text-[var(--muted)]">
            Brush any chart to filter the ledger under it. Time charts share one window;
            histograms filter by latency, confidence, or spam probability.
          </p>
        </div>
        <label className="font-mono text-xs">
          bucket{" "}
          <select
            className="border border-[var(--line)] bg-[var(--paper)] px-2 py-1.5"
            value={bucket}
            onChange={(e) => {
              setBucket(e.target.value as Bucket);
              setTimeBrush({});
            }}
          >
            <option value="minute">minute</option>
            <option value="hour">hour</option>
            <option value="day">day</option>
          </select>
        </label>
      </header>

      <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-6">
        <StatChip label="classifications" value={String(stats.n)} />
        <StatChip label="p95 total" value={formatMs(stats.latency.total["95"])} />
        <StatChip label="p95 jev" value={formatMs(stats.latency.jev_call["95"])} />
        <StatChip label="cost / 1,000" value={formatCostUsd(stats.cost_usd_per_1000)} />
        <StatChip label="uncertain" value={formatProb(stats.uncertain_rate, "rate")} />
        <StatChip label="gmail agree" value={formatProb(stats.gmail_agreement, "rate")} />
      </dl>

      <ChartFrame
        title="Latency"
        caption="p50 / p95 / p99 of total time versus the Jev call. If the solid lines sit on the dashed ones, local parse and Gmail fetch are not the wait. The histogram next to it is the shape of total ms — a second hump usually means retries."
      >
        <div className="grid h-full gap-3 lg:grid-cols-2">
          <ResponsiveContainer>
            <LineChart data={volume} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid {...grid} />
              <XAxis dataKey="bucket" tick={axis} hide={volume.length > 12} />
              <YAxis tick={axis} unit="ms" />
              <Tooltip
                formatter={(v, name) => [formatMs(num(v)), String(name)]}
                contentStyle={tipStyle}
              />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Line dataKey="p50" name="total p50" stroke="var(--ink)" dot={false} strokeWidth={1.6} />
              <Line dataKey="p95" name="total p95" stroke="var(--spam-bd)" dot={false} />
              <Line dataKey="p99" name="total p99" stroke="var(--phishing-bd)" dot={false} />
              <Line dataKey="jev50" name="jev p50" stroke="var(--ink)" strokeDasharray="4 3" dot={false} />
              <Line dataKey="jev95" name="jev p95" stroke="var(--spam-bd)" strokeDasharray="4 3" dot={false} />
              <Line dataKey="jev99" name="jev p99" stroke="var(--phishing-bd)" strokeDasharray="4 3" dot={false} />
              <Brush dataKey="bucket" height={16} stroke="var(--ink)" onChange={onTime} />
            </LineChart>
          </ResponsiveContainer>
          <ResponsiveContainer>
            <BarChart data={latBins} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid {...grid} />
              <XAxis dataKey="label" tick={axis} interval={0} angle={-25} textAnchor="end" height={50} />
              <YAxis tick={axis} allowDecimals={false} />
              <Tooltip contentStyle={{ background: "var(--paper)", border: "1px solid var(--line)", fontSize: 11 }} />
              <Bar dataKey="n" name="emails" fill="var(--bar)" />
              <Brush dataKey="label" height={16} stroke="var(--ink)" onChange={(s) => setLatBrush({ startIndex: s.startIndex, endIndex: s.endIndex })} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </ChartFrame>

      <ChartFrame
        title="Throughput"
        caption="How many classifications landed in each bucket, stacked by category. A sudden amber or red band is a spam/phishing spike, not a model outage."
      >
        <ResponsiveContainer>
          <BarChart data={volume} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid {...grid} />
            <XAxis dataKey="bucket" tick={axis} hide={volume.length > 16} />
            <YAxis tick={axis} allowDecimals={false} />
            <Tooltip contentStyle={{ background: "var(--paper)", border: "1px solid var(--line)", fontSize: 11 }} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            {CATEGORY_STACK.map((c) => (
              <Bar key={c} dataKey={c} stackId="v" fill={CATEGORY_COLORS[c]} />
            ))}
            <Brush dataKey="bucket" height={16} stroke="var(--ink)" onChange={onTime} />
          </BarChart>
        </ResponsiveContainer>
      </ChartFrame>

      <ChartFrame
        title="Cost"
        caption={`Cumulative spend in this range is ${formatCostUsd(stats.cost_usd_total)}. At the current ${formatCostUsd(stats.cost_usd_per_email)} per email, 10,000 classifications would be ${formatCostUsd(stats.projected_cost_usd.emails_10000)} and 100,000 would be ${formatCostUsd(stats.projected_cost_usd.emails_100000)}. Output tokens are free; the line is input tokens.`}
      >
        <ResponsiveContainer>
          <LineChart data={volume} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid {...grid} />
            <XAxis dataKey="bucket" tick={axis} hide={volume.length > 16} />
            <YAxis yAxisId="c" tick={axis} />
            <YAxis yAxisId="t" orientation="right" tick={axis} />
            <Tooltip
              formatter={(v, name) =>
                String(name).includes("token")
                  ? [formatTokens(num(v)), String(name)]
                  : [formatCostUsd(num(v)), String(name)]
              }
              contentStyle={tipStyle}
            />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Line yAxisId="c" dataKey="costCum" name="cumulative cost" stroke="var(--ink)" dot={false} />
            <Line yAxisId="t" dataKey="tokens" name="input tokens" stroke="var(--cat-promotional-bd)" dot={false} />
            <Brush dataKey="bucket" height={16} stroke="var(--ink)" onChange={onTime} />
          </LineChart>
        </ResponsiveContainer>
      </ChartFrame>

      <ChartFrame
        title="Quality"
        caption="Left: where category confidence piles up — a wall at 0.9+ is a model that's sure; mass under 0.5 is the uncertain bucket. Right: uncertain rate and agreement with Gmail's SPAM label over time. Agreement is not ground truth, just whether you and Gmail called the same mail junk."
      >
        <div className="grid h-full gap-3 lg:grid-cols-2">
          <ResponsiveContainer>
            <BarChart data={confBins} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid {...grid} />
              <XAxis dataKey="lo" tick={axis} tickFormatter={(v) => Number(v).toFixed(1)} />
              <YAxis tick={axis} allowDecimals={false} />
              <Tooltip contentStyle={{ background: "var(--paper)", border: "1px solid var(--line)", fontSize: 11 }} />
              <Bar dataKey="n" name="emails" fill="var(--bar)" />
              <Brush dataKey="lo" height={16} stroke="var(--ink)" onChange={(s) => setConfBrush({ startIndex: s.startIndex, endIndex: s.endIndex })} />
            </BarChart>
          </ResponsiveContainer>
          <ResponsiveContainer>
            <LineChart data={volume} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid {...grid} />
              <XAxis dataKey="bucket" tick={axis} hide={volume.length > 16} />
              <YAxis tick={axis} domain={[0, 1]} />
              <Tooltip
                formatter={(v, name) => [formatProb(num(v), "rate"), String(name)]}
                contentStyle={tipStyle}
              />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Line dataKey="uncertain" name="uncertain rate" stroke="var(--muted)" dot={false} />
              <Line dataKey="agree" name="gmail agreement" stroke="var(--ink)" dot={false} />
              <Brush dataKey="bucket" height={16} stroke="var(--ink)" onChange={onTime} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </ChartFrame>

      <ChartFrame
        title="Calibration"
        caption="Predicted spam probability bucket on x, actual Gmail-spam rate on y. Points on the diagonal mean the probability numbers can be trusted; above the line the model is under-confident, below it is over-confident."
      >
        <ResponsiveContainer>
          <ScatterChart margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
            <CartesianGrid {...grid} />
            <XAxis type="number" dataKey="mean_predicted" domain={[0, 1]} tick={axis} name="predicted" />
            <YAxis type="number" dataKey="actual_rate" domain={[0, 1]} tick={axis} name="actual" />
            <ReferenceLine
              segment={[
                { x: 0, y: 0 },
                { x: 1, y: 1 },
              ]}
              stroke="var(--muted)"
              strokeDasharray="4 4"
            />
            <Tooltip
              formatter={(v, name) => [
                formatProb(num(v), String(name) === "actual_rate" ? "actual" : "predicted"),
                String(name),
              ]}
              contentStyle={tipStyle}
            />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Scatter name="spam probability" data={calBins} fill="var(--cat-spam-bd)" />
            <Scatter name="reply probability" data={(cal?.reply ?? []).filter((b) => b.n > 0)} fill="var(--cat-promotional-bd)" />
            <Brush dataKey="mean_predicted" height={16} stroke="var(--ink)" onChange={(s) => setCalBrush({ startIndex: s.startIndex, endIndex: s.endIndex })} />
          </ScatterChart>
        </ResponsiveContainer>
      </ChartFrame>

      <ChartFrame
        title="Reliability"
        caption="Jev errors, HTTP 429 rate-limits, and retries per bucket. Any non-zero bar here is operational, not a verdict problem."
      >
        <ResponsiveContainer>
          <BarChart data={volume} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid {...grid} />
            <XAxis dataKey="bucket" tick={axis} hide={volume.length > 16} />
            <YAxis tick={axis} allowDecimals={false} />
            <Tooltip contentStyle={{ background: "var(--paper)", border: "1px solid var(--line)", fontSize: 11 }} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Bar dataKey="errors" name="jev errors" fill="var(--cat-phishing-bd)" />
            <Bar dataKey="rate_limited" name="rate limited" fill="var(--cat-spam-bd)" />
            <Bar dataKey="retries" name="retries" fill="var(--cat-promotional-bd)" />
            <Brush dataKey="bucket" height={16} stroke="var(--ink)" onChange={onTime} />
          </BarChart>
        </ResponsiveContainer>
      </ChartFrame>

      <section>
        <h2 className="font-display text-2xl">Messages in the brush</h2>
        <p className="mb-4 text-sm text-[var(--muted)]">
          {filtered.length} of {list?.items.length ?? 0} loaded rows match the current brushes (cap 200).
        </p>
        {filtered.length ? (
          <MessageTable rows={filtered} />
        ) : (
          <p className="border border-dashed border-[var(--line)] p-6 text-sm">No rows in this brush.</p>
        )}
      </section>
    </div>
  );
}
