"use client";

import { useChrome } from "@/components/ChromeProvider";
import { formatUpdateStatus } from "@/lib/chrome";
import Link from "next/link";

export function AppNav() {
  const { theme, redact, setRedact, cycle, updating, updateMailbox, lastUpdate, updateError } =
    useChrome();
  return (
    <header className="border-b border-[var(--line)] bg-[var(--paper)]/90 backdrop-blur">
      <div className="mx-auto flex max-w-6xl flex-wrap items-end justify-between gap-3 px-4 py-4 sm:px-8">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.28em] text-[var(--muted)]">
            personal gmail · jev-1.13.0
          </p>
          <Link href="/" className="font-display text-2xl tracking-tight">
            Classifier ledger
          </Link>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <nav className="flex gap-4 font-mono text-[11px] uppercase tracking-[0.18em]">
            <Link href="/" className="hover:underline">
              Live wire
            </Link>
            <Link href="/messages" className="hover:underline">
              Ledger
            </Link>
            <Link href="/metrics" className="hover:underline">
              Metrics
            </Link>
            <Link href="/thresholds" className="hover:underline">
              Thresholds
            </Link>
          </nav>
          <div className="flex gap-1 font-mono text-[10px] uppercase tracking-widest">
            <button
              type="button"
              className="border border-[var(--ink)] bg-[var(--ink)] px-2 py-1 text-[var(--paper)] hover:opacity-90 disabled:opacity-50"
              onClick={() => void updateMailbox()}
              disabled={updating}
              data-testid="update-mailbox"
            >
              {updating ? "updating…" : "update"}
            </button>
            <button
              type="button"
              className="border border-[var(--line)] px-2 py-1 hover:bg-[var(--paper-2)]"
              onClick={cycle}
              aria-label={`Theme ${theme}`}
            >
              {theme === "system" ? "sys" : theme}
            </button>
            <button
              type="button"
              className="border border-[var(--line)] px-2 py-1 hover:bg-[var(--paper-2)]"
              aria-pressed={redact}
              onClick={() => setRedact(!redact)}
            >
              {redact ? "redact on" : "redact"}
            </button>
          </div>
        </div>
      </div>
      <p className="mx-auto max-w-6xl px-4 pb-3 font-mono text-[10px] text-[var(--muted)] sm:px-8">
        j/k move · enter open · esc back · / search
        {lastUpdate ? ` · ${formatUpdateStatus(lastUpdate)}` : ""}
        {updateError ? ` · ${updateError}` : ""}
      </p>
    </header>
  );
}
