"use client";

import { useState } from "react";

import { ApiError } from "@/lib/api";
import { splitTransaction, unsplitTransaction } from "@/lib/endpoints";
import { CATEGORIES, type Transaction } from "@/lib/types";

interface Row {
  category: string;
  amount: string;
}

export function SplitTransactionModal({
  transaction,
  onClose,
  onSaved,
}: {
  transaction: Transaction;
  onClose: () => void;
  onSaved: (updated: Transaction) => void;
}) {
  const [rows, setRows] = useState<Row[]>([
    { category: CATEGORIES[0], amount: "" },
    { category: CATEGORIES[1], amount: "" },
  ]);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const total = rows.reduce((sum, r) => sum + (parseFloat(r.amount) || 0), 0);
  const target = parseFloat(transaction.amount);
  const remaining = Math.round((target - total) * 100) / 100;

  function updateRow(index: number, patch: Partial<Row>) {
    setRows((prev) => prev.map((r, i) => (i === index ? { ...r, ...patch } : r)));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (Math.abs(remaining) > 0.001) {
      setError(`Splits must sum to ${transaction.amount} (off by ${remaining.toFixed(2)})`);
      return;
    }
    setIsSubmitting(true);
    try {
      const updated = await splitTransaction(
        transaction.id,
        rows.map((r) => ({ category: r.category, amount: r.amount })),
      );
      onSaved(updated);
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail) : "Could not save split");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleUnsplit() {
    setIsSubmitting(true);
    try {
      const updated = await unsplitTransaction(transaction.id);
      onSaved(updated);
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail) : "Could not remove split");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-md space-y-4 rounded-xl bg-white p-6 dark:bg-zinc-950"
      >
        <div>
          <h2 className="text-lg font-semibold">Split transaction</h2>
          <p className="text-sm text-zinc-500">
            {transaction.raw_merchant} · {transaction.amount}
          </p>
        </div>

        <div className="space-y-2">
          {rows.map((row, i) => (
            <div key={i} className="flex items-center gap-2">
              <select
                value={row.category}
                onChange={(e) => updateRow(i, { category: e.target.value })}
                className="flex-1 rounded-md border border-black/[.12] px-2 py-1.5 text-sm dark:border-white/[.2] dark:bg-black"
              >
                {CATEGORIES.map((c) => (
                  <option key={c} value={c}>
                    {c.replace("_", " ")}
                  </option>
                ))}
              </select>
              <input
                value={row.amount}
                onChange={(e) => updateRow(i, { amount: e.target.value })}
                placeholder="0.00"
                className="w-28 rounded-md border border-black/[.12] px-2 py-1.5 text-sm dark:border-white/[.2] dark:bg-black"
              />
              {rows.length > 2 && (
                <button
                  type="button"
                  onClick={() => setRows((prev) => prev.filter((_, idx) => idx !== i))}
                  className="text-xs text-zinc-500 hover:text-red-600"
                >
                  Remove
                </button>
              )}
            </div>
          ))}
        </div>

        <button
          type="button"
          onClick={() => setRows((prev) => [...prev, { category: CATEGORIES[0], amount: "" }])}
          className="text-sm text-zinc-500 hover:text-black dark:hover:text-white"
        >
          + Add category
        </button>

        <p className="text-xs text-zinc-500">
          Remaining to allocate: <span className="font-medium">{remaining.toFixed(2)}</span>
        </p>

        {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}

        <div className="flex items-center justify-between pt-2">
          <button
            type="button"
            onClick={handleUnsplit}
            disabled={isSubmitting || !transaction.is_split}
            className="text-sm text-zinc-500 hover:text-red-600 disabled:opacity-40"
          >
            Remove split
          </button>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-full border border-black/[.12] px-4 py-2 text-sm dark:border-white/[.2]"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="rounded-full bg-black px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-white dark:text-black"
            >
              Save split
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}
