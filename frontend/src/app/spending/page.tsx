"use client";

import { useEffect, useState } from "react";

import { RankedBarChart } from "@/components/charts/ranked-bar-chart";
import { SpendTrendChart } from "@/components/charts/spend-trend-chart";
import {
  getSpendingByCategory,
  getSpendingTrend,
  getTopMerchants,
  listAccounts,
} from "@/lib/endpoints";
import type { Account, SpendingByCategory, SpendingTrendPoint, TopMerchant } from "@/lib/types";
import { useRequireAuth } from "@/lib/use-require-auth";

function formatMoney(value: number): string {
  return `$${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

export default function SpendingPage() {
  const { user, isLoading: authLoading } = useRequireAuth();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [accountId, setAccountId] = useState("");
  const [byCategory, setByCategory] = useState<SpendingByCategory | null>(null);
  const [trend, setTrend] = useState<SpendingTrendPoint[]>([]);
  const [topMerchants, setTopMerchants] = useState<TopMerchant[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (!user) return;
    listAccounts().then(setAccounts);
  }, [user]);

  useEffect(() => {
    if (!user) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setIsLoading(true);
    Promise.all([
      getSpendingByCategory({ account_id: accountId || undefined }),
      getSpendingTrend(6, accountId || undefined),
      getTopMerchants({ account_id: accountId || undefined, limit: 8 }),
    ]).then(([category, trendData, merchants]) => {
      setByCategory(category);
      setTrend(trendData);
      setTopMerchants(merchants);
      setIsLoading(false);
    });
  }, [user, accountId]);

  if (authLoading || !user) return null;

  const categoryBars = byCategory
    ? Object.entries(byCategory.by_category)
        .map(([label, value]) => ({ label: label.replace("_", " "), value: parseFloat(value) }))
        .sort((a, b) => b.value - a.value)
    : [];

  const merchantBars = topMerchants.map((m) => ({
    label: m.merchant,
    value: parseFloat(m.total_spend),
  }));

  const topCategory = categoryBars[0];
  const monthsCount = trend.length;
  const avgPerMonth =
    monthsCount > 0
      ? trend.reduce((s, p) => s + parseFloat(p.total_spend), 0) / monthsCount
      : 0;

  return (
    <div className="page max-w-5xl">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="page-title">Spending</h1>
          <p className="page-lead">
            Outflows only, reported as positive magnitudes. Income and transfers are excluded.
          </p>
        </div>
        <select
          value={accountId}
          onChange={(e) => setAccountId(e.target.value)}
          className="select w-auto"
        >
          <option value="">All accounts</option>
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.display_name}
            </option>
          ))}
        </select>
      </div>

      {isLoading ? (
        <p className="mt-8 text-sm text-muted">Loading…</p>
      ) : (
        <div className="mt-6 space-y-6">
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="card card-pad card-hover">
              <p className="text-xs font-medium text-muted uppercase tracking-wide">
                Total spend (all time)
              </p>
              <p className="stat-value mt-2 text-3xl font-semibold">
                {byCategory ? formatMoney(parseFloat(byCategory.total_spend)) : "$0"}
              </p>
            </div>
            <div className="card card-pad card-hover">
              <p className="text-xs font-medium text-muted uppercase tracking-wide">
                Avg / month (last {monthsCount})
              </p>
              <p className="stat-value mt-2 text-3xl font-semibold">{formatMoney(avgPerMonth)}</p>
            </div>
            <div className="card card-pad card-hover">
              <p className="text-xs font-medium text-muted uppercase tracking-wide">
                Largest category
              </p>
              <p className="stat-value mt-2 text-3xl font-semibold capitalize">
                {topCategory ? topCategory.label : "—"}
              </p>
              {topCategory && (
                <p className="mt-1 text-xs text-muted">{formatMoney(topCategory.value)}</p>
              )}
            </div>
          </div>

          <SpendTrendChart points={trend} />

          <div className="grid gap-6 md:grid-cols-2">
            <RankedBarChart title="Spend by category" data={categoryBars} />
            <RankedBarChart title="Top merchants" data={merchantBars} />
          </div>
        </div>
      )}
    </div>
  );
}
