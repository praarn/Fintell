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

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-xl font-semibold">Spending</h1>
        <select
          value={accountId}
          onChange={(e) => setAccountId(e.target.value)}
          className="rounded-md border border-black/[.12] px-3 py-1.5 text-sm dark:border-white/[.2] dark:bg-black"
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
        <p className="text-sm text-zinc-500">Loading…</p>
      ) : (
        <div className="space-y-6">
          <div className="rounded-xl border border-black/[.08] p-6 dark:border-white/[.145]">
            <p className="text-xs text-zinc-500">Total spend (all time)</p>
            <p className="text-3xl font-semibold">
              {byCategory ? formatMoney(parseFloat(byCategory.total_spend)) : "$0"}
            </p>
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
