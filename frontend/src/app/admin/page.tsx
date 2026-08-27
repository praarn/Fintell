"use client";

import { useEffect, useState } from "react";

import { getResumeMetrics } from "@/lib/endpoints";
import type { ResumeMetrics } from "@/lib/types";
import { useRequireAuth } from "@/lib/use-require-auth";

function Stat({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div className="rounded-xl border border-black/[.08] p-5 dark:border-white/[.145]">
      <p className="text-xs text-zinc-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
      {sub && <p className="mt-1 text-xs text-zinc-400">{sub}</p>}
    </div>
  );
}

export default function AdminPage() {
  const { user, isLoading: authLoading } = useRequireAuth();
  const [metrics, setMetrics] = useState<ResumeMetrics | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (!user) return;
    getResumeMetrics()
      .then(setMetrics)
      .finally(() => setIsLoading(false));
  }, [user]);

  if (authLoading || !user) return null;

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <h1 className="text-xl font-semibold">Metrics &amp; cost</h1>
      <p className="mt-2 text-sm text-zinc-500">
        System-wide numbers, computed live. These are the &ldquo;does the cost-aware design actually
        work&rdquo; measurements — how much of categorization stays deterministic, how often a learned
        bank profile is reused, what the LLM has actually cost, and how many natural-language
        questions the template layer can answer honestly.
      </p>

      {isLoading || !metrics ? (
        <p className="mt-6 text-sm text-zinc-500">Loading…</p>
      ) : (
        <div className="mt-6 space-y-8">
          <div>
            <h2 className="mb-3 text-sm font-medium">Categorization</h2>
            <div className="grid gap-4 sm:grid-cols-3">
              <Stat
                label="Resolved without the LLM"
                value={`${metrics.pct_categorized_deterministically}%`}
                sub={`${metrics.transactions_categorized} of ${metrics.transactions_total} transactions categorized`}
              />
              <Stat
                label="Escalated to the LLM (Tier 3)"
                value={`${metrics.pct_categorized_via_llm}%`}
                sub={`${metrics.llm_merchants_categorized} merchants over ${metrics.llm_batch_calls} batched calls`}
              />
              <Stat
                label="Estimated LLM spend"
                value={`$${metrics.llm_estimated_cost_usd.toFixed(4)}`}
                sub="provider-agnostic token pricing"
              />
            </div>
          </div>

          <div>
            <h2 className="mb-3 text-sm font-medium">Parsing</h2>
            <div className="grid gap-4 sm:grid-cols-3">
              <Stat
                label="Statements via a learned profile"
                value={`${metrics.pct_statements_via_learned_profile}%`}
                sub={`${metrics.total_statements_processed} statements processed`}
              />
              <Stat
                label="Distinct bank profiles learned"
                value={`${metrics.distinct_bank_profiles}`}
              />
              <Stat
                label="Text-to-SQL match rate"
                value={`${metrics.text_to_sql_match_rate}%`}
                sub={`${metrics.text_to_sql_answered} of ${metrics.text_to_sql_questions} questions answered by a template`}
              />
            </div>
          </div>

          <div>
            <h2 className="mb-3 text-sm font-medium">Categorization method breakdown</h2>
            <ul className="divide-y divide-black/[.06] text-sm dark:divide-white/[.08]">
              {Object.entries(metrics.categorization_by_method)
                .sort((a, b) => b[1] - a[1])
                .map(([method, count]) => (
                  <li key={method} className="flex justify-between py-2">
                    <span>{method.replace(/_/g, " ")}</span>
                    <span className="tabular-nums text-zinc-500">{count}</span>
                  </li>
                ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}
