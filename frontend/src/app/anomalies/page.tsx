"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiError } from "@/lib/api";
import {
  dismissAnomaly,
  getAnomalyStats,
  listAnomalies,
  runAnomalyDetection,
} from "@/lib/endpoints";
import type { AnomalyFlag, AnomalySeverity, AnomalyStats } from "@/lib/types";
import { useRequireAuth } from "@/lib/use-require-auth";

const SEVERITY_STYLES: Record<AnomalySeverity, string> = {
  high: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300",
  medium: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300",
  low: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400",
};

function formatMoney(value: string): string {
  const n = Math.abs(parseFloat(value));
  return `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export default function AnomaliesPage() {
  const { user, isLoading: authLoading } = useRequireAuth();
  const [flags, setFlags] = useState<AnomalyFlag[]>([]);
  const [stats, setStats] = useState<AnomalyStats | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRunning, setIsRunning] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const [feed, s] = await Promise.all([listAnomalies(), getAnomalyStats()]);
    setFlags(feed);
    setStats(s);
  }, []);

  useEffect(() => {
    if (!user) return;
    // Load-once with a loading flag; the rule prefers derived state, but
    // that's a bigger restructure (React Query/Suspense) than this needs.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    refresh().finally(() => setIsLoading(false));
  }, [user, refresh]);

  async function handleRun() {
    setIsRunning(true);
    setNotice(null);
    try {
      const run = await runAnomalyDetection();
      if (!run.model_trained) {
        setNotice(
          `Not enough spending history yet to model — need more transactions ` +
            `(${run.transactions_considered} so far).`,
        );
      } else {
        setNotice(
          `Model refit on ${run.transactions_considered} transactions · ` +
            `${run.new_flag_count} new, ${run.cleared_flag_count} cleared.`,
        );
      }
      await refresh();
    } catch (err) {
      setNotice(err instanceof ApiError ? String(err.detail) : "Detection failed");
    } finally {
      setIsRunning(false);
    }
  }

  async function handleDismiss(flag: AnomalyFlag) {
    setFlags((prev) => prev.filter((f) => f.id !== flag.id));
    try {
      await dismissAnomaly(flag.id);
      const s = await getAnomalyStats();
      setStats(s);
    } catch {
      // put it back if the call failed
      setFlags((prev) => [...prev, flag].sort((a, b) => a.score - b.score));
    }
  }

  if (authLoading || !user) return null;

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <div className="mb-2 flex items-center justify-between">
        <h1 className="text-xl font-semibold">Anomalies</h1>
        <button
          onClick={handleRun}
          disabled={isRunning}
          className="rounded-full border border-black/[.12] px-3 py-1.5 text-sm hover:bg-black/[.04] disabled:opacity-50 dark:border-white/[.2] dark:hover:bg-white/[.08]"
        >
          {isRunning ? "Running…" : "Re-run detection"}
        </button>
      </div>

      <p className="mb-6 text-sm text-zinc-500">
        A per-account{" "}
        <span className="font-medium text-zinc-700 dark:text-zinc-300">IsolationForest</span> over
        your own spending. Each flag lists the feature(s) that drove it — an unusual amount for the
        category, a first-seen merchant, off-pattern timing. Dismissing a flag tells the model that
        pattern is normal for you.
      </p>

      {notice && (
        <p className="mb-4 rounded-lg bg-black/[.04] px-3 py-2 text-sm text-zinc-600 dark:bg-white/[.06] dark:text-zinc-300">
          {notice}
        </p>
      )}

      {stats && stats.total_flags > 0 && (
        <div className="mb-6 flex flex-wrap gap-4 text-sm text-zinc-500">
          <span>{stats.active_flags} active</span>
          <span>{stats.dismissed_flags} dismissed</span>
          <span>{Math.round(stats.dismissal_rate * 100)}% dismissal rate</span>
        </div>
      )}

      {isLoading ? (
        <p className="text-sm text-zinc-500">Loading…</p>
      ) : flags.length === 0 ? (
        <p className="text-sm text-zinc-500">
          Nothing flagged. Upload more statements or re-run detection as your history grows.
        </p>
      ) : (
        <ul className="space-y-3">
          {flags.map((flag) => (
            <li
              key={flag.id}
              className="rounded-xl border border-black/[.08] p-4 dark:border-white/[.145]"
            >
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2">
                    <span
                      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${SEVERITY_STYLES[flag.severity]}`}
                    >
                      {flag.severity}
                    </span>
                    <span className="font-medium">
                      {flag.transaction.normalized_merchant ?? flag.transaction.raw_merchant}
                    </span>
                    <span className="text-sm text-zinc-500">
                      {flag.transaction.category ?? "uncategorized"}
                    </span>
                  </div>
                  <p className="mt-0.5 text-sm text-zinc-500">
                    {flag.transaction.date} · {formatMoney(flag.transaction.amount)}
                  </p>
                </div>
                <button
                  onClick={() => handleDismiss(flag)}
                  className="shrink-0 rounded-full border border-black/[.12] px-3 py-1 text-xs hover:bg-black/[.04] dark:border-white/[.2] dark:hover:bg-white/[.08]"
                >
                  Dismiss
                </button>
              </div>

              <ul className="mt-3 space-y-1 border-t border-black/[.05] pt-3 text-sm dark:border-white/[.06]">
                {flag.driving_features.map((d, i) => (
                  <li key={i} className="flex items-baseline gap-2">
                    <span className="text-zinc-400" aria-hidden>
                      •
                    </span>
                    <span>{d.explanation}</span>
                    {d.z_score !== null && (
                      <span className="text-xs text-zinc-400">({d.z_score}σ)</span>
                    )}
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
