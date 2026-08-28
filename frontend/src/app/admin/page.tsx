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
    <div className="card card-pad card-hover relative overflow-hidden">
      <span
        className="absolute inset-y-0 left-0 w-[3px]"
        style={{ backgroundColor: "var(--brand)" }}
        aria-hidden
      />
      <p className="text-xs font-medium text-muted uppercase tracking-wide">{label}</p>
      <p className="stat-value mt-2 text-2xl font-semibold">{value}</p>
      {sub && <p className="mt-1 text-xs text-muted">{sub}</p>}
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
    <div className="page max-w-4xl">
      <div className="page-head">
        <div>
          <p className="eyebrow">Intelligence</p>
          <h1 className="page-title mt-1">Metrics &amp; cost</h1>
          <p className="page-lead">
            System-wide numbers, computed live. These are the &ldquo;does the cost-aware design
            actually work&rdquo; measurements — how much of categorization stays deterministic, how
            often a learned bank profile is reused, what the LLM has actually cost, and how many
            natural-language questions the template layer can answer honestly.
          </p>
        </div>
      </div>

      {isLoading || !metrics ? (
        <p className="text-sm text-muted">Loading…</p>
      ) : (
        <div className="space-y-8">
          <div>
            <h2 className="mb-3 text-sm font-semibold text-secondary">Categorization</h2>
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
            <h2 className="mb-3 text-sm font-semibold text-secondary">Parsing</h2>
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
            <h2 className="mb-3 text-sm font-semibold text-secondary">
              Categorization method breakdown
            </h2>
            <ul className="card divide-y divide-border text-sm">
              {Object.entries(metrics.categorization_by_method)
                .sort((a, b) => b[1] - a[1])
                .map(([method, count]) => (
                  <li key={method} className="flex justify-between px-4 py-2.5">
                    <span className="capitalize">{method.replace(/_/g, " ")}</span>
                    <span className="tabular-nums text-muted">{count}</span>
                  </li>
                ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}
