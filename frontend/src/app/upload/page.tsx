"use client";

import { useEffect, useState } from "react";

import { ApiError } from "@/lib/api";
import { listAccounts, uploadStatement } from "@/lib/endpoints";
import type { Account, Statement } from "@/lib/types";
import { useRequireAuth } from "@/lib/use-require-auth";

export default function UploadPage() {
  const { user, isLoading: authLoading } = useRequireAuth();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [accountId, setAccountId] = useState<string>("");
  const [bankHint, setBankHint] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Statement | null>(null);

  useEffect(() => {
    if (!user) return;
    listAccounts().then(setAccounts);
  }, [user]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setError(null);
    setResult(null);
    setIsSubmitting(true);
    try {
      const statement = await uploadStatement(
        file,
        accountId || undefined,
        !accountId ? bankHint || undefined : undefined,
      );
      setResult(statement);
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail) : "Upload failed");
    } finally {
      setIsSubmitting(false);
    }
  }

  if (authLoading || !user) return null;

  return (
    <div className="mx-auto max-w-2xl px-6 py-10">
      <h1 className="mb-6 text-xl font-semibold">Upload a statement</h1>

      <form
        onSubmit={handleSubmit}
        className="space-y-4 rounded-xl border border-black/[.08] p-6 dark:border-white/[.145]"
      >
        <div className="space-y-1">
          <label className="text-sm text-zinc-600 dark:text-zinc-400">
            Statement file (.csv or .pdf)
          </label>
          <input
            type="file"
            accept=".csv,.pdf"
            required
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="block w-full text-sm"
          />
        </div>

        <div className="space-y-1">
          <label className="text-sm text-zinc-600 dark:text-zinc-400">Account</label>
          <select
            value={accountId}
            onChange={(e) => setAccountId(e.target.value)}
            className="w-full rounded-md border border-black/[.12] px-3 py-2 text-sm dark:border-white/[.2] dark:bg-black"
          >
            <option value="">No account — use a bank hint instead</option>
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.display_name}
              </option>
            ))}
          </select>
        </div>

        {!accountId && (
          <div className="space-y-1">
            <label className="text-sm text-zinc-600 dark:text-zinc-400">
              Bank hint (creates a lightweight account automatically)
            </label>
            <input
              value={bankHint}
              onChange={(e) => setBankHint(e.target.value)}
              placeholder="e.g. Chase Checking"
              className="w-full rounded-md border border-black/[.12] px-3 py-2 text-sm dark:border-white/[.2] dark:bg-black"
            />
          </div>
        )}

        {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}

        <button
          type="submit"
          disabled={isSubmitting || !file}
          className="rounded-full bg-black px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-white dark:text-black"
        >
          {isSubmitting ? "Uploading & parsing…" : "Upload"}
        </button>
      </form>

      {result && (
        <div className="mt-6 rounded-xl border border-black/[.08] p-4 text-sm dark:border-white/[.145]">
          <p className="font-medium">{result.original_filename}</p>
          <dl className="mt-2 grid grid-cols-2 gap-1 text-zinc-600 dark:text-zinc-400">
            <dt>Status</dt>
            <dd>{result.parse_status}</dd>
            <dt>Structure</dt>
            <dd>{result.detected_structure ?? "—"}</dd>
            <dt>Parsed via</dt>
            <dd>{result.parse_method ?? "—"}</dd>
            <dt>Rows parsed</dt>
            <dd>
              {result.row_count_parsed} / {result.row_count_total}
            </dd>
            {result.error_message && (
              <>
                <dt>Note</dt>
                <dd>{result.error_message}</dd>
              </>
            )}
          </dl>
        </div>
      )}
    </div>
  );
}
