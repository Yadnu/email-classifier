"use client";

import { formatProb } from "@/lib/format";
import { cn } from "@/lib/utils";

const ORDER = ["spam", "phishing", "promotional", "legitimate", "other"];
const COLORS: Record<string, string> = {
  spam: "var(--cat-spam-bd)",
  phishing: "var(--cat-phishing-bd)",
  promotional: "var(--cat-promotional-bd)",
  legitimate: "var(--cat-legitimate-bd)",
  other: "var(--cat-other-bd)",
};

export function ProbabilityBar({
  probabilities,
  winner,
  confidence,
}: {
  probabilities: Record<string, number>;
  winner?: string;
  confidence?: number;
}) {
  const keys = [
    ...ORDER.filter((k) => k in probabilities),
    ...Object.keys(probabilities).filter((k) => !ORDER.includes(k)),
  ];
  const total = keys.reduce((s, k) => s + (probabilities[k] ?? 0), 0) || 1;

  return (
    <div className="space-y-2" data-testid="probability-bar">
      <div className="flex h-4 w-full overflow-hidden border border-[var(--line)]">
        {keys.map((key) => {
          const p = probabilities[key] ?? 0;
          const width = (p / total) * 100;
          if (width <= 0) return null;
          return (
            <div
              key={key}
              data-option={key}
              data-probability={p}
              title={`${key}: ${formatProb(p, "probability")}`}
              className={cn("h-full", winner === key && "ring-1 ring-inset ring-[var(--ink)]")}
              style={{ width: `${width}%`, background: COLORS[key] ?? "var(--muted)" }}
            />
          );
        })}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-[11px]">
        {keys.map((key) => (
          <span key={key} className={cn(winner === key && "font-semibold")}>
            {key} {formatProb(probabilities[key] ?? 0, "probability")}
          </span>
        ))}
      </div>
      {confidence !== undefined ? (
        <p className="text-xs text-[var(--muted)]" data-confidence={confidence}>
          Winning option uses {formatProb(winner ? probabilities[winner] ?? 0 : 0, "probability")}.
          Choice confidence is a separate number: {formatProb(confidence, "confidence")}.
        </p>
      ) : null}
    </div>
  );
}
