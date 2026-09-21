"use client";

import { MessageTable } from "@/components/MessageTable";
import { ApiDown, EmptyState, TableSkeleton } from "@/components/States";
import { swrFetcher } from "@/lib/api";
import type { CompactMessage } from "@/lib/types";
import { useMemo, useRef, useState } from "react";
import useSWR from "swr";

type ListResponse = { items: CompactMessage[]; next_cursor: string | null };

export function MessageListClient() {
  const [category, setCategory] = useState("");
  const [minConf, setMinConf] = useState("");
  const [search, setSearch] = useState("");
  const searchRef = useRef<HTMLInputElement>(null);

  const qs = useMemo(() => {
    const p = new URLSearchParams();
    if (category) p.set("category", category);
    if (minConf) p.set("min_confidence", minConf);
    if (search) p.set("search", search);
    const s = p.toString();
    return `/api/messages${s ? `?${s}` : ""}`;
  }, [category, minConf, search]);

  const { data, error, isLoading } = useSWR<ListResponse>(qs, swrFetcher);

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-[var(--muted)]">
            ledger
          </p>
          <h1 className="font-display text-4xl tracking-tight">Classifications</h1>
          <p className="mt-1 max-w-xl text-sm text-[var(--muted)]">
            Every stored Jev call on real Gmail. Press update to ingest and
            classify a batch; this table is the archive.
          </p>
        </div>
        <form
          className="flex flex-wrap gap-2 font-mono text-xs"
          onSubmit={(e) => e.preventDefault()}
        >
          <input
            ref={searchRef}
            className="border border-[var(--line)] bg-[var(--paper)] px-2 py-1.5"
            placeholder="search subject or domain"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            aria-label="Search"
          />
          <select
            className="border border-[var(--line)] bg-[var(--paper)] px-2 py-1.5"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            aria-label="Category"
          >
            <option value="">all categories</option>
            {["spam", "phishing", "promotional", "legitimate", "uncertain", "other"].map(
              (c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ),
            )}
          </select>
          <input
            className="w-28 border border-[var(--line)] bg-[var(--paper)] px-2 py-1.5"
            placeholder="min conf."
            value={minConf}
            onChange={(e) => setMinConf(e.target.value)}
            aria-label="Minimum confidence"
          />
        </form>
      </header>

      {error ? <ApiDown /> : null}
      {isLoading ? <TableSkeleton /> : null}
      {data && data.items.length === 0 ? (
        <EmptyState>
          No classifications yet. Press{" "}
          <span className="font-mono">update</span> to pull Gmail and classify
          real mail.
        </EmptyState>
      ) : null}
      {data && data.items.length > 0 ? (
        <MessageTable rows={data.items} searchRef={searchRef} />
      ) : null}
    </div>
  );
}
