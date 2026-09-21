"use client";

import { useChrome } from "@/components/ChromeProvider";
import { ApiDown, EmptyState, FeedSkeleton } from "@/components/States";
import { LiveRow } from "@/components/LiveRow";
import { SparklineStrip } from "@/components/SparklineStrip";
import { useListHotkeys } from "@/hooks/useListHotkeys";
import { API_BASE, swrFetcher } from "@/lib/api";
import { prependUnique } from "@/lib/live";
import { sparklineHour } from "@/lib/sparkline";
import type { CompactMessage } from "@/lib/types";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import useSWR, { mutate } from "swr";

type ListResponse = { items: CompactMessage[]; next_cursor: string | null };
type Conn = "connecting" | "live" | "offline";

export function LiveFeedClient() {
  const { refreshEpoch } = useChrome();
  const { data, error, isLoading } = useSWR<ListResponse>("/api/messages?limit=80", swrFetcher);
  const [live, setLive] = useState<CompactMessage[]>([]);
  const [paused, setPaused] = useState(false);
  const [held, setHeld] = useState(0);
  const [conn, setConn] = useState<Conn>("connecting");
  const [selected, setSelected] = useState(0);
  const pausedRef = useRef(paused);
  const bufferRef = useRef<CompactMessage[]>([]);

  useEffect(() => {
    pausedRef.current = paused;
  }, [paused]);

  useEffect(() => {
    if (!data?.items) return;
    if (refreshEpoch > 0) {
      setLive(data.items);
      return;
    }
    setLive((prev) => (prev.length ? prev : data.items));
  }, [data, refreshEpoch]);

  const onEvent = useCallback((row: CompactMessage) => {
    if (pausedRef.current) {
      bufferRef.current = prependUnique(bufferRef.current, [row], 200);
      setHeld(bufferRef.current.length);
      return;
    }
    setLive((prev) => prependUnique(prev, [row]));
    void mutate("/api/messages?limit=80");
  }, []);

  useEffect(() => {
    const es = new EventSource(`${API_BASE}/api/live`);
    es.onopen = () => setConn("live");
    es.onerror = () => setConn("offline");
    es.onmessage = (ev) => {
      try {
        onEvent(JSON.parse(ev.data) as CompactMessage);
      } catch {
        /* ignore malformed frames */
      }
    };
    return () => es.close();
  }, [onEvent]);

  const unpause = () => {
    const drained = bufferRef.current.splice(0, bufferRef.current.length);
    if (drained.length) setLive((prev) => prependUnique(prev, drained));
    setHeld(0);
    setPaused(false);
  };

  const points = useMemo(
    () => sparklineHour(live, Date.now()),
    [live],
  );

  useListHotkeys({
    count: live.length,
    selected,
    setSelected,
    ids: live.map((r) => r.message_id),
  });

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-[var(--muted)]">
            wire
          </p>
          <h1 className="font-display text-4xl tracking-tight">Live classifications</h1>
          <p className="mt-1 max-w-xl text-sm text-[var(--muted)]">
            Newest first. Pause the wire before opening a row so it does not jump
            under the cursor.
          </p>
        </div>
        <div className="flex items-center gap-3 font-mono text-xs">
          <span
            className={conn === "live" ? "live-dot" : "text-[var(--muted)]"}
            data-testid="live-status"
            data-status={conn}
          >
            {conn === "live" ? "receiving" : conn === "offline" ? "stream down" : "connecting"}
          </span>
          <button
            type="button"
            className="border border-[var(--line)] px-3 py-1.5 uppercase tracking-widest hover:bg-[var(--paper-2)]"
            onClick={() => (paused ? unpause() : setPaused(true))}
            aria-pressed={paused}
          >
            {paused ? `resume (${held} held)` : "pause"}
          </button>
        </div>
      </header>

      <p className="text-sm text-[var(--muted)]">
        Last 60 minutes: classifications per minute, p95 of total time, and cost
        in that window (the hourly rate while the wire is this busy).
      </p>
      <SparklineStrip points={points} />

      {error ? <ApiDown /> : null}

      {isLoading && live.length === 0 ? <FeedSkeleton /> : null}

      {!isLoading && live.length === 0 ? (
        <EmptyState>
          The wire is quiet. Press <span className="font-mono">update</span> in
          the header to sync Gmail and classify a batch of real mail.
        </EmptyState>
      ) : null}

      {live.length > 0 ? (
        <div className="space-y-1" data-testid="live-feed">
          {live.map((row, i) => (
            <LiveRow key={`${row.message_id}:${row.id}`} row={row} selected={i === selected} />
          ))}
        </div>
      ) : null}
    </div>
  );
}
