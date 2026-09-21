"use client";

import { DecisionTrail } from "@/components/DecisionTrail";
import { QuestionCards } from "@/components/QuestionCards";
import { StateJson } from "@/components/StateJson";
import { VerdictHeader } from "@/components/VerdictHeader";
import { Waterfall } from "@/components/Waterfall";
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

  if (error) {
    return (
      <p className="p-8 text-sm">
        Could not load this message. Is the API running?{" "}
        <Link href="/" className="underline">
          Back to list
        </Link>
      </p>
    );
  }
  if (isLoading || !data) {
    return <div className="m-8 h-[80vh] animate-pulse bg-[var(--paper-2)]" />;
  }

  const obs = data.result.observability;

  return (
    <article className="mx-auto max-w-6xl space-y-12 px-4 py-8 sm:px-8">
      <Link href="/" className="font-mono text-[11px] uppercase tracking-widest text-[var(--muted)]">
        ← all classifications
      </Link>
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
