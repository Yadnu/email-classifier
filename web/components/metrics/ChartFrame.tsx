import type { ReactNode } from "react";

export function ChartFrame({
  title,
  caption,
  children,
}: {
  title: string;
  caption: string;
  children: ReactNode;
}) {
  return (
    <section className="border border-[var(--line)] bg-[var(--paper-2)] p-4">
      <h2 className="font-display text-2xl tracking-tight">{title}</h2>
      <p className="mb-4 mt-1 max-w-3xl text-sm leading-relaxed text-[var(--muted)]">{caption}</p>
      <div className="h-64 w-full">{children}</div>
    </section>
  );
}

export function StatChip({ label, value }: { label: string; value: string }) {
  return (
    <div className="border border-[var(--line)] px-3 py-2">
      <dt className="font-mono text-[10px] uppercase tracking-widest text-[var(--muted)]">{label}</dt>
      <dd className="mt-1 font-mono text-lg tabular-nums">{value}</dd>
    </div>
  );
}
