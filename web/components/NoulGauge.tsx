"use client";

import { formatProb } from "@/lib/format";

export function NoulGauge({
  value,
  threshold,
  label = "noul",
}: {
  value: number;
  threshold?: number;
  label?: string;
}) {
  const v = Math.min(1, Math.max(0, value));
  const t = threshold ?? 0.75;
  const atThreshold = Math.abs(v - t) < 1e-9;

  return (
    <div className="space-y-1" data-testid="noul-gauge" data-value={v} data-threshold={t} data-at-threshold={atThreshold ? "true" : "false"}>
      <div className="relative h-3 w-full border border-[var(--line)] bg-[var(--track)]">
        <div
          className="absolute inset-y-0 left-0 bg-[var(--ink)]"
          style={{ width: `${v * 100}%` }}
        />
        <div
          className="absolute top-[-3px] bottom-[-3px] w-px bg-[var(--spam-fg)]"
          style={{ left: `${t * 100}%` }}
          title={`decision threshold ${formatProb(t, "threshold")}`}
        />
      </div>
      <div className="flex justify-between font-mono text-[11px] text-[var(--muted)]">
        <span>0 {label}</span>
        <span>
          {formatProb(v, label)}
          {atThreshold ? " (exactly at threshold)" : v > t ? " (above threshold)" : " (below threshold)"}
        </span>
        <span>1</span>
      </div>
    </div>
  );
}
