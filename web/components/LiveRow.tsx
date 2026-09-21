"use client";

import { CategoryPill } from "@/components/CategoryPill";
import { useChrome } from "@/components/ChromeProvider";
import { cn } from "@/lib/utils";
import { formatCostUsd, formatMs, formatProb } from "@/lib/format";
import { redactValue } from "@/lib/redact";
import type { Category, CompactMessage } from "@/lib/types";
import Link from "next/link";

const EDGE: Record<Category, string> = {
  legitimate: "border-l-[var(--cat-legitimate-bd)]",
  promotional: "border-l-[var(--cat-promotional-bd)]",
  spam: "border-l-[var(--cat-spam-bd)]",
  phishing: "border-l-[var(--cat-phishing-bd)]",
  uncertain: "border-l-[var(--cat-uncertain-bd)]",
  other: "border-l-[var(--cat-other-bd)]",
};

export function LiveRow({
  row,
  selected = false,
}: {
  row: CompactMessage;
  selected?: boolean;
}) {
  const { redact } = useChrome();
  return (
    <Link
      href={`/messages/${row.message_id}`}
      aria-selected={selected}
      className={cn(
        "grid grid-cols-1 gap-2 border border-[var(--line)] border-l-4 bg-[var(--paper-2)] px-3 py-2.5 hover:bg-[var(--row-hover)] sm:grid-cols-[7.5rem_5.5rem_5.5rem_5rem_5.5rem_8rem_1fr] sm:items-center",
        EDGE[row.category] ?? EDGE.other,
        selected && "row-active",
      )}
    >
      <CategoryPill category={row.category} />
      <span className="font-mono text-xs tabular-nums">
        {formatProb(row.spam_probability, "spam")}
      </span>
      <span className="font-mono text-xs tabular-nums">
        {formatProb(row.reply_probability, "reply")}
      </span>
      <span className="font-mono text-xs tabular-nums">{formatMs(row.total_ms)}</span>
      <span className="font-mono text-xs tabular-nums">{formatCostUsd(row.cost_usd)}</span>
      <span className="truncate font-mono text-xs text-[var(--muted)]">
        {redactValue(row.sender_domain, redact) || "—"}
      </span>
      <span className="truncate text-sm">
        {redactValue(row.subject, redact) || "(no subject)"}
      </span>
    </Link>
  );
}
