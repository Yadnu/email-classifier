import type { DecisionStep } from "@/lib/types";

export function DecisionTrail({ steps }: { steps: DecisionStep[] }) {
  return (
    <ol className="space-y-2">
      {steps.map((step) => (
        <li
          key={step.id}
          className="flex gap-3 border border-[var(--line)] px-3 py-2"
        >
          <span className="font-mono text-xs uppercase tracking-widest text-[var(--muted)]">
            {step.matched ? "fired" : "skip"}
          </span>
          <span className="text-sm">{step.label}</span>
        </li>
      ))}
    </ol>
  );
}
