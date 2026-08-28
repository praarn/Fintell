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
    <div className="page max-w-2xl">
      <h1 className="page-title">Accounts</h1>
      <p className="page-lead">
        A statement can be attached to an account, or you can just give a bank hint on upload and one
        is created for you.
      </p>

      <form onSubmit={handleCreate} className="card card-pad mt-6 mb-8 flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium text-muted">Name</label>
          <input
            required
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            placeholder="Chase Checking"
            className="input w-auto"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium text-muted">Bank (optional)</label>
          <input
            value={bankName}
            onChange={(e) => setBankName(e.target.value)}
            placeholder="Chase"
            className="input w-auto"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium text-muted">Type</label>
          <select
            value={accountType}
            onChange={(e) => setAccountType(e.target.value as AccountType)}
            className="select w-auto"
          >
            {ACCOUNT_TYPES.map((t) => (
              <option key={t} value={t}>
                {t.replace("_", " ")}
              </option>
            ))}
          </select>
        </div>
        <button type="submit" disabled={isSubmitting} className="btn btn-primary">
          Add account
        </button>
        {error && <p className="w-full text-sm text-negative">{error}</p>}
      </form>

      {isLoading ? (
        <p className="text-sm text-muted">Loading…</p>
      ) : accounts.length === 0 ? (
        <p className="text-sm text-muted">
          No accounts yet — create one above, or just upload a statement and one will be created
          automatically from the bank hint you give it.
        </p>
      ) : (
        <ul className="card divide-y divide-border">
          {accounts.map((a) => (
            <li key={a.id} className="flex items-center gap-3 px-4 py-3">
              <span
                className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-brand-soft text-sm font-semibold text-brand"
                aria-hidden
              >
                {a.display_name.slice(0, 1).toUpperCase()}
              </span>
              <div>
                <p className="text-sm font-medium">{a.display_name}</p>
                <p className="text-xs text-muted">
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
