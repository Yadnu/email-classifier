"use client";

import { CategoryPill } from "@/components/CategoryPill";
import { useChrome } from "@/components/ChromeProvider";
import { formatCostUsd, formatMs, formatProb } from "@/lib/format";
import { redactValue } from "@/lib/redact";
import type { MessageDetail } from "@/lib/types";

export function VerdictHeader({ detail }: { detail: MessageDetail }) {
  const { redact } = useChrome();
  const r = detail.result;
  return (
    <header className="border-b border-[var(--line)] pb-6">
      <div className="flex flex-wrap items-end gap-4">
        <CategoryPill category={r.category} large />
        <div className="font-display text-4xl leading-none tracking-tight">
          {r.spam ? "Spam" : "Ham"}
        </div>
      </div>
      <p className="mt-3 font-mono text-xs text-[var(--muted)]">
        {redactValue(detail.from_header ?? "", redact) || "no From header"} ·{" "}
        {redactValue(detail.subject ?? "", redact) || "(no subject)"}
      </p>
      <p className="mt-4 max-w-3xl text-lg leading-snug">{detail.explanation}</p>
      <dl className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-4 lg:grid-cols-6 font-mono text-sm">
        <Stat label="spam probability" value={formatProb(r.spam_probability, "probability")} />
        <Stat label="reply probability" value={formatProb(r.reply_probability, "probability")} />
        <Stat label="category confidence" value={formatProb(r.category_confidence, "confidence")} />
        <Stat label="total time" value={formatMs(r.classification_time_ms.total)} />
        <Stat label="cost this call" value={formatCostUsd(r.observability.cost_usd)} />
        <Stat label="model" value={r.observability.model_version} />
      </dl>
    </header>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-[11px] uppercase tracking-widest text-[var(--muted)]">{label}</dt>
      <dd className="mt-1 tabular-nums">{value}</dd>
    </div>
  );
}
