import type { ReactNode } from "react";

export function EmptyState({ children }: { children: ReactNode }) {
  return (
    <div className="border border-dashed border-[var(--line)] p-10 text-sm leading-relaxed">
      {children}
    </div>
  );
}

export function ApiDown() {
  return (
    <div className="border border-[var(--phishing-bd)] p-6 text-sm">
      Cannot reach the API at 127.0.0.1:8000. Start it with{" "}
      <code className="font-mono">uv run email-classifier serve</code>.
    </div>
  );
}

export function FeedSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div className="space-y-2" aria-hidden>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-14 animate-pulse border border-[var(--line)] bg-[var(--paper-2)]" />
      ))}
    </div>
  );
}

export function TableSkeleton() {
  return (
    <div className="overflow-hidden border border-[var(--line)]" aria-hidden>
      <div className="h-9 bg-[var(--paper-2)]" />
      {Array.from({ length: 8 }).map((_, i) => (
        <div key={i} className="h-10 animate-pulse border-t border-[var(--line)] bg-[var(--paper)]" />
      ))}
    </div>
  );
}

export function DetailSkeleton() {
  return (
    <div className="mx-auto max-w-6xl space-y-8 px-4 py-8 sm:px-8" aria-hidden>
      <div className="h-8 w-40 animate-pulse bg-[var(--paper-2)]" />
      <div className="h-24 animate-pulse bg-[var(--paper-2)]" />
      <div className="h-40 animate-pulse bg-[var(--paper-2)]" />
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="h-64 animate-pulse bg-[var(--paper-2)]" />
        <div className="h-64 animate-pulse bg-[var(--paper-2)]" />
      </div>
    </div>
  );
}

export function PageSkeleton() {
  return <div className="h-[70vh] animate-pulse border border-[var(--line)] bg-[var(--paper-2)]" aria-hidden />;
}
