"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { CategorizationBadge } from "@/components/categorization-badge";
import { RankedBarChart } from "@/components/charts/ranked-bar-chart";
import { SpendTrendChart } from "@/components/charts/spend-trend-chart";
import {
  getAnomalyStats,
  getResumeMetrics,
  getSpendingByCategory,
  getSpendingTrend,
  listTransactions,
} from "@/lib/endpoints";
import type {
  AnomalyStats,
  ResumeMetrics,
  SpendingByCategory,
  SpendingTrendPoint,
  Transaction,
} from "@/lib/types";
import { useRequireAuth } from "@/lib/use-require-auth";

function money(n: number, opts: Intl.NumberFormatOptions = {}): string {
  return `$${n.toLocaleString(undefined, { maximumFractionDigits: 0, ...opts })}`;
}

function monthLabel(month: string): string {
  const [y, m] = month.split("-");
  return new Date(Number(y), Number(m) - 1, 1).toLocaleDateString(undefined, {
    month: "long",
    year: "numeric",
  });
}

function Kpi({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string;
  sub?: React.ReactNode;
  accent?: "positive" | "negative" | "warning";
}) {
  const accentClass =
    accent === "positive"
      ? "text-positive"
      : accent === "negative"
        ? "text-negative"
        : accent === "warning"
          ? "text-warning"
          : "";
  return (
    <div className="kpi">
      <p className="kpi-label">{label}</p>
      <p className={`kpi-value ${accentClass}`}>{value}</p>
      {sub !== undefined && <p className="kpi-sub">{sub}</p>}
    </div>
  );
}

export default function DashboardPage() {
  const { user, isLoading: authLoading } = useRequireAuth();
  const [byCategory, setByCategory] = useState<SpendingByCategory | null>(null);
  const [trend, setTrend] = useState<SpendingTrendPoint[]>([]);
  const [recent, setRecent] = useState<Transaction[]>([]);
  const [anomalies, setAnomalies] = useState<AnomalyStats | null>(null);
  const [metrics, setMetrics] = useState<ResumeMetrics | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (!user) return;
    Promise.all([
      getSpendingByCategory({}),
      getSpendingTrend(12),
      listTransactions({ page: 1, page_size: 6 }),
      getAnomalyStats().catch(() => null),
      getResumeMetrics().catch(() => null),
    ]).then(([cat, tr, tx, anom, met]) => {
      setByCategory(cat);
      setTrend(tr);
      setRecent(tx.items);
      setAnomalies(anom);
      setMetrics(met);
      setIsLoading(false);
    });
  }, [user]);

  if (authLoading || !user) return null;

  const values = trend.map((p) => parseFloat(p.total_spend));
  const lastMonth = trend.at(-1);
  const prevMonth = trend.at(-2);
  const lastVal = lastMonth ? parseFloat(lastMonth.total_spend) : 0;
  const prevVal = prevMonth ? parseFloat(prevMonth.total_spend) : 0;
  const deltaPct = prevVal > 0 ? ((lastVal - prevVal) / prevVal) * 100 : null;
  const avg = values.length ? values.reduce((a, b) => a + b, 0) / values.length : 0;

  const categoryBars = byCategory
    ? Object.entries(byCategory.by_category)
        .map(([label, v]) => ({ label: label.replace(/_/g, " "), value: parseFloat(v) }))
        .sort((a, b) => b.value - a.value)
    : [];
  const topCategory = categoryBars[0];

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <p className="eyebrow">Overview</p>
          <h1 className="page-title mt-1">
            {lastMonth ? monthLabel(lastMonth.month) : "Dashboard"}
          </h1>
          <p className="page-lead">
            A snapshot across every account you&apos;ve uploaded. Spend figures are outflows only —
            income and transfers are excluded.
          </p>
        </div>
        <Link href="/upload" className="btn btn-primary">
          Upload a statement
        </Link>
      </div>

      {isLoading ? (
        <p className="text-sm text-muted">Loading…</p>
      ) : (
        <div className="space-y-6">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Kpi
              label="Spent last month"
              value={money(lastVal, { maximumFractionDigits: 2 })}
              sub={
                deltaPct === null ? (
                  "no prior month to compare"
                ) : (
                  <span className={deltaPct > 0 ? "text-negative" : "text-positive"}>
                    {deltaPct > 0 ? "▲" : "▼"} {Math.abs(deltaPct).toFixed(1)}% vs previous month
                  </span>
                )
              }
            />
            <Kpi
              label="Monthly average"
              value={money(avg, { maximumFractionDigits: 2 })}
              sub={`over ${values.length} month${values.length === 1 ? "" : "s"}`}
            />
            <Kpi
              label="Largest category"
              value={topCategory ? topCategory.label : "—"}
              sub={topCategory ? money(topCategory.value) + " all-time" : undefined}
            />
            <Kpi
              label="Open anomalies"
              value={anomalies ? String(anomalies.active_flags) : "0"}
              accent={anomalies && anomalies.active_flags > 0 ? "warning" : undefined}
              sub={
                anomalies && anomalies.active_flags > 0 ? (
                  <Link href="/anomalies" className="link">
                    review flags
                  </Link>
                ) : (
                  "nothing flagged"
                )
              }
            />
          </div>

          <div className="grid gap-6 lg:grid-cols-5">
            <div className="lg:col-span-3">
              <SpendTrendChart points={trend} />
            </div>
            <div className="lg:col-span-2">
              <RankedBarChart title="Spend by category" data={categoryBars.slice(0, 7)} />
            </div>
          </div>

          <div className="card">
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <h2 className="text-sm font-semibold">Recent transactions</h2>
              <Link href="/transactions" className="link text-sm">
                View all
              </Link>
            </div>
            <div className="overflow-x-auto">
              <table className="table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Merchant</th>
                    <th>Category</th>
                    <th>Via</th>
                    <th className="text-right">Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {recent.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="py-8 text-center text-muted">
                        No transactions yet.{" "}
                        <Link href="/upload" className="link">
                          Upload a statement
                        </Link>
                        .
                      </td>
                    </tr>
                  ) : (
                    recent.map((t) => {
                      const amt = parseFloat(t.amount);
                      return (
                        <tr key={t.id}>
                          <td className="whitespace-nowrap text-muted tnum">{t.date}</td>
                          <td className="font-medium">{t.normalized_merchant ?? t.raw_merchant}</td>
                          <td className="text-secondary">{t.category ?? "—"}</td>
                          <td>
                            <CategorizationBadge method={t.categorization_method} />
                          </td>
                          <td className={`num ${amt >= 0 ? "text-positive" : ""}`}>
                            {amt >= 0 ? "+" : ""}
                            {amt.toLocaleString(undefined, {
                              minimumFractionDigits: 2,
                              maximumFractionDigits: 2,
                            })}
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {metrics && (
            <div className="grid gap-3 sm:grid-cols-3">
              <Kpi
                label="Categorized without an LLM"
                value={`${metrics.pct_categorized_deterministically}%`}
                sub={`${metrics.transactions_categorized} of ${metrics.transactions_total} rows`}
                accent="positive"
              />
              <Kpi
                label="Statements via a learned profile"
                value={`${metrics.pct_statements_via_learned_profile}%`}
                sub={`${metrics.total_statements_processed} processed · ${metrics.distinct_bank_profiles} layouts`}
              />
              <Kpi
                label="Estimated LLM spend"
                value={`$${metrics.llm_estimated_cost_usd.toFixed(2)}`}
                sub={`${metrics.llm_batch_calls} batched call${metrics.llm_batch_calls === 1 ? "" : "s"}`}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
