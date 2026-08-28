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

function AmountCell({ value }: { value: string }) {
  const n = parseFloat(value);
  const negative = n < 0;
  return (
    <span
      className={`stat-value font-medium ${negative ? "text-content" : "text-positive"}`}
      title={negative ? "Outflow" : "Inflow"}
    >
      {negative ? "" : "+"}
      {n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
    </span>
  );
}

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
    <div className="page">
      <div className="page-head">
        <div>
          <p className="eyebrow">Overview</p>
          <h1 className="page-title mt-1">Transactions</h1>
          <p className="page-lead">
            Every parsed row, with the tier that categorized it. Re-categorize inline or split a
            charge across categories.
          </p>
        </div>
      </div>

      <div className="card card-pad mb-4 flex flex-wrap gap-3">
        <select
          value={accountId}
          onChange={(e) => {
            setPage(1);
            setAccountId(e.target.value);
          }}
          className="select w-auto"
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
          className="select w-auto"
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
          className="input w-auto flex-1 min-w-[12rem]"
        />
      </div>

      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs font-medium tracking-wide text-muted uppercase">
              <th className="px-4 py-3">Date</th>
              <th className="px-4 py-3">Merchant</th>
              <th className="px-4 py-3">Category</th>
              <th className="px-4 py-3">Categorized via</th>
              <th className="px-4 py-3 text-right">Amount</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={6} className="px-4 py-10 text-center text-muted">
                  Loading…
                </td>
              </tr>
            ) : transactions.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-10 text-center text-muted">
                  No transactions match these filters.
                </td>
              </tr>
            ) : (
              transactions.map((t) => (
                <tr
                  key={t.id}
                  className="border-b border-border/60 transition-colors last:border-0 hover:bg-surface-2"
                >
                  <td className="px-4 py-2.5 whitespace-nowrap text-muted tabular-nums">{t.date}</td>
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{t.normalized_merchant ?? t.raw_merchant}</span>
                      {t.is_split && (
                        <span className="chip bg-brand-soft text-brand">Split</span>
                      )}
                      {recurringIds.has(t.id) && (
                        <span className="chip bg-positive-soft text-positive">Recurring</span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-2.5">
                    {t.is_split ? (
                      <span className="text-muted">split across categories</span>
                    ) : (
                      <select
                        value={t.category ?? ""}
                        onChange={(e) => handleRecategorize(t, e.target.value)}
                        className="select w-auto !py-1 text-xs"
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
                  <td className="px-4 py-2.5">
                    <CategorizationBadge method={t.categorization_method} />
                  </td>
                  <td className="px-4 py-2.5 text-right whitespace-nowrap">
                    <AmountCell value={t.amount} />
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <button
                      onClick={() => setSplitTarget(t)}
                      className="text-xs font-medium text-muted hover:text-brand"
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

      <div className="mt-4 flex items-center justify-between text-sm text-muted">
        <span>
          {total} transaction{total === 1 ? "" : "s"}
        </span>
        <div className="flex items-center gap-2">
          <button
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
            className="btn btn-ghost btn-sm"
          >
            Previous
          </button>
          <span className="tabular-nums">
            Page {page} of {totalPages}
          </span>
          <button
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
            className="btn btn-ghost btn-sm"
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
