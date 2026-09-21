"use client";

import { formatMs } from "@/lib/format";
import type { SpanNode } from "@/lib/types";
import { cn } from "@/lib/utils";

const LABELS: Record<string, string> = {
  gmail_fetch: "gmail fetch",
  parse: "parse",
  state_build: "state",
  jev_call: "jev",
  decision: "decide",
};

export function Waterfall({ root }: { root: SpanNode }) {
  const children = root.children?.length
    ? root.children
    : [{ name: root.name, duration_ms: root.duration_ms }];
  const total = Math.max(
    root.duration_ms,
    children.reduce((s, c) => s + c.duration_ms, 0),
    1,
  );

  return (
    <div className="space-y-2" data-testid="waterfall">
      {children.map((span) => {
        const pct = span.pct_of_total ?? (span.duration_ms / total) * 100;
        const isJev = span.name === "jev_call";
        return (
          <div key={span.name} className="grid grid-cols-[7rem_1fr_5.5rem] items-center gap-3">
            <div className="font-mono text-[11px] uppercase tracking-wider text-[var(--muted)]">
              {LABELS[span.name] ?? span.name}
            </div>
            <div className="relative h-7 bg-[var(--track)]">
              <div
                title={`${span.name}: start ${span.offset_ms ?? 0} ms, duration ${span.duration_ms} ms (${pct.toFixed(1)}% of total)`}
                className={cn(
                  "absolute inset-y-0 flex items-center justify-end pr-2 text-[11px] font-mono",
                  isJev ? "bg-[var(--ink)] text-[var(--paper)]" : "bg-[var(--bar)] text-[var(--ink)]",
                  span.rate_limited && "bg-stripes",
                )}
                style={{
                  left: `${((span.offset_ms ?? 0) / total) * 100}%`,
                  width: `${Math.max(pct, 1.5)}%`,
                }}
                data-span={span.name}
                data-duration={span.duration_ms}
                data-rate-limited={span.rate_limited ? "true" : "false"}
              >
                {pct >= 18 ? formatMs(span.duration_ms) : null}
              </div>
              {span.retries ? (
                <span
                  className="absolute -top-2 right-1 font-mono text-[10px] text-[var(--spam-fg)]"
                  data-retries={span.retries}
                >
                  {span.retries} retr{span.retries === 1 ? "y" : "ies"}
                </span>
              ) : null}
            </div>
            <div className="text-right font-mono text-xs tabular-nums">
              {formatMs(span.duration_ms)}{" "}
              <span className="text-[var(--muted)]">{pct.toFixed(0)}%</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
