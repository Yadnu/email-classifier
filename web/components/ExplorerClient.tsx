"use client";

import { CategoryPill } from "@/components/CategoryPill";
import { useChrome } from "@/components/ChromeProvider";
import { StatChip } from "@/components/metrics/ChartFrame";
import { ApiDown, EmptyState, PageSkeleton } from "@/components/States";
import { apiPost, swrFetcher } from "@/lib/api";
import { decide, wouldReply, type Thresholds } from "@/lib/decide";
import { formatProb } from "@/lib/format";
import { redactValue } from "@/lib/redact";
import { binaryScores } from "@/lib/scores";
import type { CompactMessage } from "@/lib/types";
import Link from "next/link";
import { useMemo, useState } from "react";
import useSWR, { mutate } from "swr";

type ExplorerResponse = { items: CompactMessage[]; thresholds: Thresholds };

const SLIDERS: { key: keyof Thresholds; label: string; hint: string }[] = [
  {
    key: "uncertain_floor",
    label: "uncertain floor",
    hint: "Below this category confidence, the verdict is uncertain and no Gmail label is applied.",
  },
  {
    key: "spam_is_spam",
    label: "is_spam noul",
    hint: "Spam if this noul is strictly above the line, even when the category is not spam.",
  },
  {
    key: "spam_category_confidence",
    label: "spam/phishing category bar",
    hint: "Spam if Jev picked spam or phishing and confidence is strictly above this bar.",
  },
  {
    key: "phishing_category_confidence",
    label: "phishing category bar",
    hint: "Phishing (and spam) if Jev picked phishing above this higher bar.",
  },
  {
    key: "phishing_credential_request",
    label: "credential_request noul",
    hint: "Paired with brand impersonation. Both must be strictly above their lines.",
  },
  {
    key: "phishing_brand_impersonation",
    label: "brand_impersonation noul",
    hint: "Paired with credential request to force a phishing verdict.",
  },
  {
    key: "promotional_action",
    label: "promotional auto-label",
    hint: "Promotional mail below this confidence is classified but not auto-labeled.",
  },
  {
    key: "needs_reply_label",
    label: "needs_reply noul",
    hint: "Jev-Needs-Reply is applied when this noul is at or above the line.",
  },
];

export function ExplorerClient() {
  const { redact } = useChrome();
  const { data, error, isLoading } = useSWR<ExplorerResponse>("/api/explorer?limit=500", swrFetcher);
  const [draft, setDraft] = useState<Thresholds | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const saved = data?.thresholds ?? null;
  const thresholds = draft ?? saved;

  const rows = data?.items ?? [];
  const replay = useMemo(() => {
    if (!thresholds || !saved) return [];
    return rows.map((row) => {
      const next = decide(row, thresholds);
      const prev = decide(row, saved);
      return {
        row,
        next,
        prev,
        replyNow: wouldReply(row.reply_probability, thresholds),
        replyWas: wouldReply(row.reply_probability, saved),
      };
    });
  }, [rows, thresholds, saved]);

  const scores = useMemo(() => {
    const yTrue = replay.map((r) => r.row.gmail_spam);
    const yPred = replay.map((r) => r.next.spam);
    return binaryScores(yTrue, yPred);
  }, [replay]);

  const flips = replay.filter(
    (r) =>
      r.next.spam !== r.row.spam ||
      r.next.category !== r.row.category ||
      r.replyNow !== r.replyWas,
  );

  const setKey = (key: keyof Thresholds, value: number) => {
    if (!thresholds) return;
    setDraft({ ...thresholds, [key]: value });
  };

  const save = async () => {
    if (!thresholds) return;
    const ok = window.confirm(
      "Write these thresholds to config.yaml? New classify calls will use them. Stored rows are not rewritten.",
    );
    if (!ok) return;
    setBusy(true);
    setNotice(null);
    try {
      await apiPost("/api/thresholds", { thresholds, confirm: true });
      setDraft(null);
      setNotice("Saved to config.yaml.");
      await mutate("/api/explorer?limit=500");
      await mutate("/api/thresholds");
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "save failed");
    } finally {
      setBusy(false);
    }
  };

  if (error) {
    return <ApiDown />;
  }
  if (isLoading || !thresholds) {
    return <PageSkeleton />;
  }
  if (rows.length === 0) {
    return (
      <EmptyState>
        No stored classifications. Press update to classify real Gmail.
      </EmptyState>
    );
  }

  const dirty = draft !== null;

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-[var(--muted)]">
            what-if
          </p>
          <h1 className="font-display text-4xl tracking-tight">Threshold explorer</h1>
          <p className="mt-1 max-w-2xl text-sm text-[var(--muted)]">
            Sliders re-run the Python decision rules in the browser on stored Jev
            answers. No new model calls. Precision uses Gmail&apos;s SPAM label as
            the reference, not a human gold set.
          </p>
        </div>
        <div className="flex gap-2 font-mono text-xs">
          <button
            type="button"
            className="border border-[var(--line)] px-3 py-1.5 uppercase tracking-widest disabled:opacity-40"
            disabled={!dirty}
            onClick={() => setDraft(null)}
          >
            revert
          </button>
          <button
            type="button"
            className="border border-[var(--ink)] bg-[var(--ink)] px-3 py-1.5 uppercase tracking-widest text-[var(--paper)] disabled:opacity-40"
            disabled={busy || !dirty}
            onClick={() => void save()}
          >
            {busy ? "saving…" : "save to config.yaml"}
          </button>
        </div>
      </header>

      {notice ? <p className="text-sm">{notice}</p> : null}

      <dl className="grid grid-cols-2 gap-2 sm:grid-cols-5">
        <StatChip label="precision" value={formatProb(scores.precision, "prec.")} />
        <StatChip label="recall" value={formatProb(scores.recall, "rec.")} />
        <StatChip label="F1" value={formatProb(scores.f1, "F1")} />
        <StatChip label="false positives" value={String(scores.fp)} />
        <StatChip label="rows that flip" value={`${flips.length} / ${rows.length}`} />
      </dl>

      <div className="grid gap-4 lg:grid-cols-2">
        {SLIDERS.map((s) => (
          <label key={s.key} className="border border-[var(--line)] bg-[var(--paper-2)] p-4">
            <div className="flex items-baseline justify-between gap-3">
              <span className="font-display text-lg">{s.label}</span>
              <span className="font-mono text-sm tabular-nums">
                {thresholds[s.key].toFixed(2)}
                {saved && Math.abs(saved[s.key] - thresholds[s.key]) > 0.001 ? (
                  <span className="text-[var(--muted)]"> (saved {saved[s.key].toFixed(2)})</span>
                ) : null}
              </span>
            </div>
            <p className="mt-1 text-xs leading-relaxed text-[var(--muted)]">{s.hint}</p>
            <input
              type="range"
              min={0}
              max={1}
              step={0.01}
              value={thresholds[s.key]}
              onChange={(e) => setKey(s.key, Number(e.target.value))}
              className="mt-3 w-full accent-[var(--ink)]"
              aria-label={s.label}
            />
          </label>
        ))}
      </div>

      <section>
        <h2 className="font-display text-2xl">Messages that change</h2>
        <p className="mb-4 text-sm text-[var(--muted)]">
          A flip is a different spam bit, category, or needs-reply label versus the
          stored verdict / current saved reply bar.
        </p>
        {flips.length === 0 ? (
          <p className="border border-dashed border-[var(--line)] p-6 text-sm">
            No rows flip at these thresholds.
          </p>
        ) : (
          <div className="space-y-1">
            {flips.map(({ row, next }) => (
              <Link
                key={`${row.message_id}:${row.id}`}
                href={`/messages/${row.message_id}`}
                className="grid gap-2 border border-[var(--line)] px-3 py-2 hover:bg-[var(--row-hover)] sm:grid-cols-[8rem_auto_auto_1fr]"
              >
                <span className="flex gap-2">
                  <CategoryPill category={row.category} />
                  <span className="text-[var(--muted)]">→</span>
                  <CategoryPill category={next.category} />
                </span>
                <span className="font-mono text-xs">
                  spam {row.spam ? "yes" : "no"} → {next.spam ? "yes" : "no"}
                </span>
                <span className="font-mono text-xs text-[var(--muted)]">{next.decision_path}</span>
                <span className="truncate text-sm">{redactValue(row.subject, redact) || redactValue(row.sender_domain, redact)}</span>
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
