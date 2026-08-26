"use client";

import { useCallback, useEffect, useState } from "react";

import { CategorizationBadge } from "@/components/categorization-badge";
import { SplitTransactionModal } from "@/components/split-transaction-modal";
import {
  getRecurringTransactions,
  listAccounts,
  listTransactions,
  recategorizeTransaction,
} from "@/lib/endpoints";
import { CATEGORIES, type Account, type Transaction } from "@/lib/types";
import { useRequireAuth } from "@/lib/use-require-auth";

const PAGE_SIZE = 25;

export default function TransactionsPage() {
  const { user, isLoading: authLoading } = useRequireAuth();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [accountId, setAccountId] = useState("");
  const [category, setCategory] = useState("");
  const [search, setSearch] = useState("");
  const [recurringIds, setRecurringIds] = useState<Set<string>>(new Set());
  const [splitTarget, setSplitTarget] = useState<Transaction | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const refresh = useCallback(async () => {
    if (!user) return;
    setIsLoading(true);
    const result = await listTransactions({
      account_id: accountId || undefined,
      category: category || undefined,
      search: search || undefined,
      page,
      page_size: PAGE_SIZE,
    });
    setTransactions(result.items);
    setTotal(result.total);
    setIsLoading(false);
  }, [user, accountId, category, search, page]);

  useEffect(() => {
    if (!user) return;
    listAccounts().then(setAccounts);
    getRecurringTransactions().then((groups) => {
      const ids = new Set<string>();
      for (const g of groups) for (const id of g.transaction_ids) ids.add(id);
      setRecurringIds(ids);
    });
  }, [user]);

  useEffect(() => {
    // Fetch-on-filter-change with a loading flag — the rule wants derived
    // state instead, but that's a much bigger restructure (React Query/
    // Suspense) than this page needs.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    refresh();
  }, [refresh]);

  async function handleRecategorize(transaction: Transaction, newCategory: string) {
    const updated = await recategorizeTransaction(transaction.id, newCategory);
    setTransactions((prev) => prev.map((t) => (t.id === updated.id ? updated : t)));
  }

  if (authLoading || !user) return null;

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="mx-auto max-w-5xl px-6 py-10">
      <h1 className="mb-6 text-xl font-semibold">Transactions</h1>

      <div className="mb-4 flex flex-wrap gap-3">
        <select
          value={accountId}
          onChange={(e) => {
            setPage(1);
            setAccountId(e.target.value);
          }}
          className="rounded-md border border-black/[.12] px-3 py-1.5 text-sm dark:border-white/[.2] dark:bg-black"
        >
          <option value="">All accounts</option>
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.display_name}
            </option>
          ))}
        </select>
        <select
          value={category}
          onChange={(e) => {
            setPage(1);
            setCategory(e.target.value);
          }}
          className="rounded-md border border-black/[.12] px-3 py-1.5 text-sm dark:border-white/[.2] dark:bg-black"
        >
          <option value="">All categories</option>
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {c.replace("_", " ")}
            </option>
          ))}
        </select>
        <input
          value={search}
          onChange={(e) => {
            setPage(1);
            setSearch(e.target.value);
          }}
          placeholder="Search merchant…"
          className="rounded-md border border-black/[.12] px-3 py-1.5 text-sm dark:border-white/[.2] dark:bg-black"
        />
      </div>

      <div className="overflow-x-auto rounded-xl border border-black/[.08] dark:border-white/[.145]">
        <table className="w-full text-sm">
          <thead className="border-b border-black/[.08] text-left text-xs text-zinc-500 dark:border-white/[.1]">
            <tr>
              <th className="px-4 py-2">Date</th>
              <th className="px-4 py-2">Merchant</th>
              <th className="px-4 py-2">Category</th>
              <th className="px-4 py-2">Categorized via</th>
              <th className="px-4 py-2 text-right">Amount</th>
              <th className="px-4 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-zinc-500">
                  Loading…
                </td>
              </tr>
            ) : transactions.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-zinc-500">
                  No transactions match these filters.
                </td>
              </tr>
            ) : (
              transactions.map((t) => (
                <tr
                  key={t.id}
                  className="border-b border-black/[.05] last:border-0 dark:border-white/[.06]"
                >
                  <td className="px-4 py-2 whitespace-nowrap">{t.date}</td>
                  <td className="px-4 py-2">
                    <div className="flex items-center gap-2">
                      <span>{t.normalized_merchant ?? t.raw_merchant}</span>
                      {t.is_split && (
                        <span className="rounded-full bg-fuchsia-100 px-2 py-0.5 text-xs text-fuchsia-800 dark:bg-fuchsia-900/40 dark:text-fuchsia-300">
                          Split
                        </span>
                      )}
                      {recurringIds.has(t.id) && (
                        <span className="rounded-full bg-teal-100 px-2 py-0.5 text-xs text-teal-800 dark:bg-teal-900/40 dark:text-teal-300">
                          Recurring
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-2">
                    {t.is_split ? (
                      <span className="text-zinc-500">split across categories</span>
                    ) : (
                      <select
                        value={t.category ?? ""}
                        onChange={(e) => handleRecategorize(t, e.target.value)}
                        className="rounded-md border border-black/[.12] bg-transparent px-2 py-1 text-xs dark:border-white/[.2]"
                      >
                        <option value="" disabled>
                          Uncategorized
                        </option>
                        {CATEGORIES.map((c) => (
                          <option key={c} value={c}>
                            {c.replace("_", " ")}
                          </option>
                        ))}
                      </select>
                    )}
                  </td>
                  <td className="px-4 py-2">
                    <CategorizationBadge method={t.categorization_method} />
                  </td>
                  <td className="px-4 py-2 text-right whitespace-nowrap">{t.amount}</td>
                  <td className="px-4 py-2 text-right">
                    <button
                      onClick={() => setSplitTarget(t)}
                      className="text-xs text-zinc-500 hover:text-black dark:hover:text-white"
                    >
                      Split
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="mt-4 flex items-center justify-between text-sm text-zinc-500">
        <span>
          {total} transaction{total === 1 ? "" : "s"}
        </span>
        <div className="flex items-center gap-3">
          <button
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
            className="disabled:opacity-40"
          >
            Previous
          </button>
          <span>
            Page {page} of {totalPages}
          </span>
          <button
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
            className="disabled:opacity-40"
          >
            Next
          </button>
        </div>
      </div>

      {splitTarget && (
        <SplitTransactionModal
          transaction={splitTarget}
          onClose={() => setSplitTarget(null)}
          onSaved={(updated) => {
            setTransactions((prev) => prev.map((t) => (t.id === updated.id ? updated : t)));
            setSplitTarget(null);
          }}
        />
      )}
    </div>
  );
}
