"use client";

import { MessageTable } from "@/components/MessageTable";
import { swrFetcher } from "@/lib/api";
import type { CompactMessage } from "@/lib/types";
import { useMemo, useState } from "react";
import useSWR from "swr";

type ListResponse = { items: CompactMessage[]; next_cursor: string | null };

export function MessageListClient() {
  const [category, setCategory] = useState("");
  const [minConf, setMinConf] = useState("");
  const [search, setSearch] = useState("");

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
            inspect
          </p>
          <h1 className="font-display text-4xl tracking-tight">Classifications</h1>
          <p className="mt-1 max-w-xl text-sm text-[var(--muted)]">
            Every row is one stored Jev call. Open a message to see why it was
            labeled, how long each stage took, and what it cost.
          </p>
        </div>
        <form
          className="flex flex-wrap gap-2 font-mono text-xs"
          onSubmit={(e) => e.preventDefault()}
        >
          <input
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

      {error ? (
        <div className="border border-[var(--phishing-bd)] p-6 text-sm">
          Cannot reach the API at 127.0.0.1:8000. Start it with{" "}
          <code className="font-mono">uv run email-classifier serve</code>.
        </div>
      ) : null}

      {isLoading ? (
        <div className="h-64 animate-pulse border border-[var(--line)] bg-[var(--paper-2)]" />
      ) : null}

      {data && data.items.length === 0 ? (
        <div className="border border-dashed border-[var(--line)] p-10 text-sm leading-relaxed">
          No classifications yet. Run{" "}
          <code className="font-mono">uv run python scripts/seed_classifications.py</code>{" "}
          or <code className="font-mono">uv run email-classifier classify &lt;id&gt;</code>{" "}
          after ingest.
        </div>
      ) : null}

      {data && data.items.length > 0 ? <MessageTable rows={data.items} /> : null}
    </div>
  );
}
