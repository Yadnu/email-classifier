"use client";

export function StateJson({
  state,
  chars,
  truncated,
}: {
  state: Record<string, unknown>;
  chars: number;
  truncated: boolean;
}) {
  return (
    <div className="border border-[var(--line)] bg-[var(--paper-2)] p-4">
      <div className="mb-3 flex flex-wrap items-center gap-3 font-mono text-[11px] uppercase tracking-widest">
        <span>state json</span>
        <span className="text-[var(--muted)]">{chars.toLocaleString()} chars</span>
        {truncated ? (
          <span className="border border-[var(--spam-bd)] px-2 py-0.5 text-[var(--spam-fg)]">
            body truncated
          </span>
        ) : null}
      </div>
      <div className="space-y-1">
        {Object.entries(state).map(([key, value]) => (
          <details key={key} className="border-b border-[var(--line)] py-1">
            <summary className="cursor-pointer font-mono text-xs">{key}</summary>
            <pre className="mt-1 overflow-x-auto whitespace-pre-wrap text-xs leading-relaxed">
              {typeof value === "string" ? value : JSON.stringify(value, null, 2)}
            </pre>
          </details>
        ))}
      </div>
    </div>
  );
}
