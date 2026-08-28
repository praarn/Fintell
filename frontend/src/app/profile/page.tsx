"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import {
  getActivity,
  listAccounts,
  listSessions,
  listStatements,
  listTransactions,
  revokeSession,
} from "@/lib/endpoints";
import type { ActiveSession, AuditEntry } from "@/lib/types";
import { useRequireAuth } from "@/lib/use-require-auth";

const ACTION_LABELS: Record<string, string> = {
  "auth.login": "Signed in",
  "auth.login_failed": "Failed sign-in attempt",
  "auth.refresh_reuse_detected": "Refresh-token reuse detected — sessions revoked",
  "auth.session_revoked": "Session revoked",
  "statement.upload": "Statement uploaded",
  "statement.delete": "Statement deleted",
  "statement.download": "Statement file downloaded",
  "transactions.export": "Transactions exported",
};

function formatWhen(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function formatDay(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

export default function ProfilePage() {
  const { user, isLoading: authLoading } = useRequireAuth();
  const { logout } = useAuth();
  const router = useRouter();

  const [counts, setCounts] = useState<{ accounts: number; statements: number; transactions: number }>(
    { accounts: 0, statements: 0, transactions: 0 },
  );
  const [sessions, setSessions] = useState<ActiveSession[]>([]);
  const [activity, setActivity] = useState<AuditEntry[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const [accounts, statements, tx, s, a] = await Promise.all([
      listAccounts(),
      listStatements(),
      listTransactions({ page: 1, page_size: 1 }),
      listSessions(),
      getActivity(50),
    ]);
    setCounts({
      accounts: accounts.length,
      statements: statements.length,
      transactions: tx.total,
    });
    setSessions(s);
    setActivity(a);
  }, []);

  useEffect(() => {
    if (!user) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    refresh().finally(() => setIsLoading(false));
  }, [user, refresh]);

  async function handleRevoke(session: ActiveSession) {
    setError(null);
    try {
      await revokeSession(session.family_id);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail) : "Could not revoke that session");
    }
  }

  async function handleLogout() {
    await logout();
    router.replace("/login");
  }

  if (authLoading || !user) return null;

  return (
    <div className="page max-w-3xl">
      <div className="page-head">
        <div>
          <p className="eyebrow">Account</p>
          <h1 className="page-title mt-1">Profile</h1>
          <p className="page-lead">
            Your identity, a summary of the data you&apos;ve uploaded, and the security controls for
            your account.
          </p>
        </div>
        <button onClick={handleLogout} className="btn btn-ghost w-full sm:w-auto">
          Log out
        </button>
      </div>

      {error && (
        <p className="mb-4 rounded-lg bg-negative-soft px-3 py-2 text-sm text-negative">{error}</p>
      )}

      <section className="card card-pad flex flex-col gap-4 sm:flex-row sm:items-center">
        <span
          className="grid h-14 w-14 shrink-0 place-items-center rounded-xl text-xl font-bold text-white"
          style={{ backgroundColor: "var(--brand)" }}
          aria-hidden
        >
          {user.email.slice(0, 1).toUpperCase()}
        </span>
        <div className="min-w-0">
          <p className="truncate text-base font-semibold">{user.email}</p>
          <p className="mt-0.5 text-sm text-muted">Member since {formatDay(user.created_at)}</p>
          <p className="mt-1 font-mono text-xs text-muted">ID {user.id}</p>
        </div>
      </section>

      <section className="mt-6">
        <h2 className="text-sm font-semibold text-secondary">Your data</h2>
        <div className="mt-3 grid gap-3 sm:grid-cols-3">
          <div className="kpi">
            <p className="kpi-label">Accounts</p>
            <p className="kpi-value">{isLoading ? "—" : counts.accounts}</p>
          </div>
          <div className="kpi">
            <p className="kpi-label">Statements</p>
            <p className="kpi-value">{isLoading ? "—" : counts.statements}</p>
          </div>
          <div className="kpi">
            <p className="kpi-label">Transactions</p>
            <p className="kpi-value">{isLoading ? "—" : counts.transactions.toLocaleString()}</p>
          </div>
        </div>
      </section>

      <section className="mt-8">
        <h2 className="text-sm font-semibold text-secondary">Active sessions</h2>
        <p className="mt-1 text-xs text-muted">
          Each device that has logged in holds its own refresh-token chain. Revoking one signs that
          device out immediately; reuse of a rotated-out token revokes the whole chain automatically.
        </p>

        {isLoading ? (
          <p className="mt-3 text-sm text-muted">Loading…</p>
        ) : (
          <ul className="mt-3 space-y-2">
            {sessions.map((s) => (
              <li
                key={s.family_id}
                className="card card-pad flex items-start justify-between gap-4 text-sm"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-medium">
                      {s.user_agent ? s.user_agent.split(" ")[0] : "Unknown client"}
                    </span>
                    {s.is_current && (
                      <span className="chip bg-positive-soft text-positive">this device</span>
                    )}
                  </div>
                  <p className="mt-0.5 text-xs text-muted">
                    Started {formatWhen(s.created_at)}
                    {s.ip_at_creation ? ` · ${s.ip_at_creation}` : ""} · expires{" "}
                    {formatWhen(s.expires_at)}
                  </p>
                </div>
                {!s.is_current && (
                  <button onClick={() => handleRevoke(s)} className="btn btn-ghost btn-sm shrink-0">
                    Revoke
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="mt-10">
        <h2 className="text-sm font-semibold text-secondary">Recent account activity</h2>
        <p className="mt-1 text-xs text-muted">
          The security audit trail for your account — sign-ins, statement uploads and deletions, file
          downloads, session revocations.
        </p>

        {isLoading ? (
          <p className="mt-3 text-sm text-muted">Loading…</p>
        ) : activity.length === 0 ? (
          <p className="mt-3 text-sm text-muted">Nothing recorded yet.</p>
        ) : (
          <ul className="card mt-3 divide-y divide-border text-sm">
            {activity.map((entry) => (
              <li key={entry.id} className="flex items-baseline justify-between gap-4 px-4 py-2.5">
                <span>{ACTION_LABELS[entry.action] ?? entry.action}</span>
                <span className="shrink-0 text-xs text-muted">{formatWhen(entry.created_at)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
