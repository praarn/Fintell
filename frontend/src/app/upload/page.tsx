"use client";

import { useEffect, useState } from "react";

import { ApiError } from "@/lib/api";
import { API_BASE_URL } from "@/lib/config";
import {
  deleteStatement,
  getStatementDownloadUrl,
  listAccounts,
  listStatements,
  uploadStatement,
} from "@/lib/endpoints";
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
  const [statements, setStatements] = useState<Statement[]>([]);

  useEffect(() => {
    if (!user) return;
    listAccounts().then(setAccounts);
    listStatements().then(setStatements);
  }, [user]);

  async function refreshStatements() {
    setStatements(await listStatements());
  }

  async function handleDownload(statement: Statement) {
    setError(null);
    try {
      const { url } = await getStatementDownloadUrl(statement.id);
      window.open(`${API_BASE_URL}${url}`, "_blank", "noopener");
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail) : "Could not create a download link");
    }
  }

  async function handleDelete(statement: Statement) {
    if (!window.confirm(`Delete ${statement.original_filename} and its transactions?`)) return;
    setError(null);
    try {
      await deleteStatement(statement.id);
      await refreshStatements();
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail) : "Delete failed");
    }
  }

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
      await refreshStatements();
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail) : "Upload failed");
    } finally {
      setIsSubmitting(false);
    }
  }

  if (authLoading || !user) return null;

  return (
    <div className="page max-w-2xl">
      <h1 className="page-title">Upload a statement</h1>
      <p className="page-lead">
        CSV or PDF, any column order or date format, negative-for-debit or split debit/credit columns,
        even a scanned image. The layout is fingerprinted and reused next time.
      </p>

      <form onSubmit={handleSubmit} className="card card-pad mt-6 space-y-4">
        <div className="space-y-1.5">
          <label className="text-sm font-medium text-secondary">Statement file (.csv or .pdf)</label>
          <input
            type="file"
            accept=".csv,.pdf"
            required
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="block w-full text-sm text-secondary file:mr-3 file:rounded-lg file:border-0 file:bg-brand-soft file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-brand hover:file:bg-brand-soft/70"
          />
        </div>

        <div className="space-y-1.5">
          <label className="text-sm font-medium text-secondary">Account</label>
          <select
            value={accountId}
            onChange={(e) => setAccountId(e.target.value)}
            className="select"
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
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-secondary">
              Bank hint (creates a lightweight account automatically)
            </label>
            <input
              value={bankHint}
              onChange={(e) => setBankHint(e.target.value)}
              placeholder="e.g. Chase Checking"
              className="input"
            />
          </div>
        )}

        {error && (
          <p className="rounded-lg bg-negative-soft px-3 py-2 text-sm text-negative">{error}</p>
        )}

        <button type="submit" disabled={isSubmitting || !file} className="btn btn-primary">
          {isSubmitting ? "Uploading & parsing…" : "Upload"}
        </button>
      </form>

      {result && (
        <div className="card card-pad mt-6 text-sm">
          <p className="font-medium">{result.original_filename}</p>
          <dl className="mt-2 grid grid-cols-2 gap-1 text-muted">
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

      {statements.length > 0 && (
        <section className="mt-10">
          <h2 className="mb-3 text-sm font-semibold text-secondary">Your statements</h2>
          <ul className="card divide-y divide-border">
            {statements.map((s) => (
              <li key={s.id} className="flex items-center justify-between gap-4 px-4 py-3">
                <div className="min-w-0">
                  <p className="truncate font-medium">{s.original_filename}</p>
                  <p className="text-xs text-muted">
                    {new Date(s.uploaded_at).toLocaleDateString()} · {s.parse_status} ·{" "}
                    {s.row_count_parsed}/{s.row_count_total} rows
                  </p>
                </div>
                <div className="flex shrink-0 gap-2">
                  <button onClick={() => handleDownload(s)} className="btn btn-ghost btn-sm">
                    Download
                  </button>
                  <button onClick={() => handleDelete(s)} className="btn btn-danger btn-sm">
                    Delete
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
