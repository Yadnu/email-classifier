"use client";

import { DecisionTrail } from "@/components/DecisionTrail";
import { QuestionCards } from "@/components/QuestionCards";
import { StateJson } from "@/components/StateJson";
import { VerdictHeader } from "@/components/VerdictHeader";
import { Waterfall } from "@/components/Waterfall";
import { ApiDown, DetailSkeleton } from "@/components/States";
import { useListHotkeys } from "@/hooks/useListHotkeys";
import { swrFetcher } from "@/lib/api";
import { formatCostUsd, formatTokens } from "@/lib/format";
import type { MessageDetail } from "@/lib/types";
import Link from "next/link";
import useSWR from "swr";

export function MessageDetailClient({ id }: { id: string }) {
  const { data, error, isLoading } = useSWR<MessageDetail>(
    `/api/messages/${id}`,
    swrFetcher,
  );

  useListHotkeys({
    count: 0,
    selected: 0,
    setSelected: () => {},
    ids: [],
  });

  if (error) {
    return (
      <div className="p-8">
        <ApiDown />
        <Link href="/messages" className="mt-4 inline-block text-sm underline">
          Back to ledger
        </Link>
      </div>
    );
  }
  if (isLoading || !data) {
    return <DetailSkeleton />;
  }

  const obs = data.result.observability;

  return (
    <article className="mx-auto max-w-6xl space-y-12 px-4 py-8 sm:px-8">
      <div className="flex gap-4 font-mono text-[11px] uppercase tracking-widest text-[var(--muted)]">
        <Link href="/">← live wire</Link>
        <Link href="/messages">ledger</Link>
      </div>
      <VerdictHeader detail={data} />

      <section>
        <h2 className="mb-1 font-display text-2xl">Waterfall</h2>
        <p className="mb-4 text-sm text-[var(--muted)]">
          Time in each stage. Jev is usually most of the bar.
        </p>
        <Waterfall root={data.spans} />
      </section>

      <section className="grid gap-6 lg:grid-cols-2">
        <div>
          <h2 className="mb-1 font-display text-2xl">State sent to Jev</h2>
          <p className="mb-4 text-sm text-[var(--muted)]">
            Exact JSON payload. Body lives only under body_excerpt.
          </p>
          <StateJson
            state={data.state}
            chars={data.state_size_chars}
            truncated={data.body_truncated}
          />
        </div>
        <div>
          <h2 className="mb-1 font-display text-2xl">Questions</h2>
          <p className="mb-4 text-sm text-[var(--muted)]">
            One system_one call. Probability is not the same as confidence.
          </p>
          <QuestionCards questions={data.questions} />
          <p className="mt-4 font-mono text-xs text-[var(--muted)]">
            {formatTokens(obs.input_tokens)} input tokens
            {obs.input_tokens_estimated ? " (estimated)" : ""} ·{" "}
            {formatCostUsd(obs.cost_usd)} · output tokens are free
          </p>
        </div>
      </section>

      <section>
        <h2 className="mb-1 font-display text-2xl">Decision trail</h2>
        <p className="mb-4 text-sm text-[var(--muted)]">
          Thresholds evaluated in order in Python, not in Jev.
        </p>
        <DecisionTrail steps={data.decision_trail} />
      </section>
    </article>
  );
}
