"use client";

import { NoulGauge } from "@/components/NoulGauge";
import { ProbabilityBar } from "@/components/ProbabilityBar";
import { ScoreAxis } from "@/components/ScoreAxis";
import type { QuestionCard } from "@/lib/types";

const DEFAULT_NOUL_THRESHOLDS: Record<string, number> = {
  is_spam: 0.75,
  needs_reply: 0.7,
  credential_request: 0.8,
  brand_impersonation: 0.8,
};

export function QuestionCards({ questions }: { questions: QuestionCard[] }) {
  return (
    <div className="grid gap-4">
      {questions.map((q) => (
        <article
          key={q.name}
          className="border border-[var(--line)] bg-[var(--paper-2)] p-4"
        >
          <header className="mb-2 flex items-baseline justify-between gap-3">
            <h3 className="font-display text-lg">{q.name}</h3>
            <span className="font-mono text-[11px] uppercase tracking-widest text-[var(--muted)]">
              {q.type}
            </span>
          </header>
          {q.instructions ? (
            <p className="mb-3 text-sm leading-relaxed text-[var(--muted)]">
              {q.instructions}
            </p>
          ) : null}
          {q.type === "Choice" ? (
            <ProbabilityBar
              probabilities={q.answer?.probabilities ?? {}}
              winner={q.answer?.choice}
              confidence={q.answer?.confidence}
            />
          ) : null}
          {q.type === "Noul" ? (
            <NoulGauge
              value={q.answer?.noul ?? 0}
              threshold={DEFAULT_NOUL_THRESHOLDS[q.name]}
              label="noul"
            />
          ) : null}
          {q.type === "Score" && Array.isArray(q.criteria) ? (
            <ScoreAxis
              value={q.answer?.score ?? 0}
              criteria={q.criteria}
            />
          ) : null}
        </article>
      ))}
    </div>
  );
}
