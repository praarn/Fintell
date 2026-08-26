"use client";

import { useEffect, useState } from "react";

import { ApiError } from "@/lib/api";
import { createAccount, listAccounts } from "@/lib/endpoints";
import type { Account, AccountType } from "@/lib/types";
import { useRequireAuth } from "@/lib/use-require-auth";

const ACCOUNT_TYPES: AccountType[] = ["checking", "savings", "credit_card", "other"];

export default function AccountsPage() {
  const { user, isLoading: authLoading } = useRequireAuth();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [displayName, setDisplayName] = useState("");
  const [bankName, setBankName] = useState("");
  const [accountType, setAccountType] = useState<AccountType>("checking");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (!user) return;
    listAccounts()
      .then(setAccounts)
      .finally(() => setIsLoading(false));
  }, [user]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      const account = await createAccount(displayName, bankName || null, accountType);
      setAccounts((prev) => [...prev, account]);
      setDisplayName("");
      setBankName("");
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail) : "Could not create account");
    } finally {
      setIsSubmitting(false);
    }
  }

  if (authLoading || !user) return null;

  return (
    <div className="mx-auto max-w-2xl px-6 py-10">
      <h1 className="mb-6 text-xl font-semibold">Accounts</h1>

      <form
        onSubmit={handleCreate}
        className="mb-8 flex flex-wrap items-end gap-3 rounded-xl border border-black/[.08] p-4 dark:border-white/[.145]"
      >
        <div className="flex flex-col gap-1">
          <label className="text-xs text-zinc-500">Name</label>
          <input
            required
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            placeholder="Chase Checking"
            className="rounded-md border border-black/[.12] px-3 py-1.5 text-sm dark:border-white/[.2] dark:bg-black"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-zinc-500">Bank (optional)</label>
          <input
            value={bankName}
            onChange={(e) => setBankName(e.target.value)}
            placeholder="Chase"
            className="rounded-md border border-black/[.12] px-3 py-1.5 text-sm dark:border-white/[.2] dark:bg-black"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-zinc-500">Type</label>
          <select
            value={accountType}
            onChange={(e) => setAccountType(e.target.value as AccountType)}
            className="rounded-md border border-black/[.12] px-3 py-1.5 text-sm dark:border-white/[.2] dark:bg-black"
          >
            {ACCOUNT_TYPES.map((t) => (
              <option key={t} value={t}>
                {t.replace("_", " ")}
              </option>
            ))}
          </select>
        </div>
        <button
          type="submit"
          disabled={isSubmitting}
          className="rounded-full bg-black px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-white dark:text-black"
        >
          Add account
        </button>
        {error && <p className="w-full text-sm text-red-600 dark:text-red-400">{error}</p>}
      </form>

      {isLoading ? (
        <p className="text-sm text-zinc-500">Loading…</p>
      ) : accounts.length === 0 ? (
        <p className="text-sm text-zinc-500">
          No accounts yet — create one above, or just upload a statement and one will be created
          automatically from the bank hint you give it.
        </p>
      ) : (
        <ul className="divide-y divide-black/[.08] rounded-xl border border-black/[.08] dark:divide-white/[.1] dark:border-white/[.145]">
          {accounts.map((a) => (
            <li key={a.id} className="flex items-center justify-between px-4 py-3">
              <div>
                <p className="text-sm font-medium">{a.display_name}</p>
                <p className="text-xs text-zinc-500">
                  {a.bank_name ?? "—"} · {a.account_type.replace("_", " ")}
                </p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
