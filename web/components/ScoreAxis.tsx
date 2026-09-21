"use client";

export function ScoreAxis({
  value,
  criteria,
}: {
  value: number;
  criteria: string[];
}) {
  const max = Math.max(criteria.length - 1, 1);
  const clamped = Math.min(max, Math.max(0, value));
  const fractional = clamped % 1 !== 0;

  return (
    <div className="space-y-3" data-testid="score-axis" data-value={clamped} data-fractional={fractional ? "true" : "false"}>
      <div className="relative h-8">
        <div className="absolute top-3 left-0 right-0 h-px bg-[var(--line)]" />
        {criteria.map((label, i) => (
          <div
            key={label}
            className="absolute top-0 -translate-x-1/2"
            style={{ left: `${(i / max) * 100}%` }}
          >
            <div className="mx-auto h-2 w-px bg-[var(--ink)]" />
            <div className="mt-2 max-w-[7rem] text-center font-mono text-[10px] leading-tight text-[var(--muted)]">
              {i} {label}
            </div>
          </div>
        ))}
        <div
          className="absolute top-1 h-4 w-4 -translate-x-1/2 rounded-full border-2 border-[var(--ink)] bg-[var(--paper)]"
          style={{ left: `${(clamped / max) * 100}%` }}
          title={`score ${clamped} of ${max}`}
        />
      </div>
      <p className="font-mono text-xs">
        Score {clamped.toFixed(2)} on a 0–{max} axis
        {fractional ? " (between criteria levels)" : ""}.
      </p>
    </div>
  );
}
