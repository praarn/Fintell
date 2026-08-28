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
  high: "bg-negative-soft text-negative",
  medium: "bg-warning-soft text-warning",
  low: "bg-surface-3 text-muted",
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
    <div className="page max-w-3xl">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="page-title">Anomalies</h1>
          <p className="page-lead">
            A per-account{" "}
            <span className="font-medium text-secondary">IsolationForest</span> over your own
            spending. Each flag lists the feature(s) that drove it — an unusual amount for the
            category, a first-seen merchant, off-pattern timing. Dismissing a flag tells the model
            that pattern is normal for you.
          </p>
        </div>
        <button onClick={handleRun} disabled={isRunning} className="btn btn-ghost btn-sm shrink-0">
          {isRunning ? "Running…" : "Re-run detection"}
        </button>
      </div>

      {notice && (
        <p className="mt-4 rounded-lg surface-muted px-3 py-2 text-sm text-secondary">{notice}</p>
      )}

      {stats && stats.total_flags > 0 && (
        <div className="mt-5 flex flex-wrap gap-2">
          <span className="chip surface-muted text-secondary">{stats.active_flags} active</span>
          <span className="chip surface-muted text-secondary">
            {stats.dismissed_flags} dismissed
          </span>
          <span className="chip surface-muted text-secondary">
            {Math.round(stats.dismissal_rate * 100)}% dismissal rate
          </span>
        </div>
      )}

      {isLoading ? (
        <p className="mt-8 text-sm text-muted">Loading…</p>
      ) : flags.length === 0 ? (
        <p className="mt-8 text-sm text-muted">
          Nothing flagged. Upload more statements or re-run detection as your history grows.
        </p>
      ) : (
        <ul className="mt-6 space-y-3">
          {flags.map((flag) => (
            <li key={flag.id} className="card card-pad card-hover">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={`chip ${SEVERITY_STYLES[flag.severity]}`}>{flag.severity}</span>
                    <span className="font-medium">
                      {flag.transaction.normalized_merchant ?? flag.transaction.raw_merchant}
                    </span>
                    <span className="text-sm text-muted">
                      {flag.transaction.category ?? "uncategorized"}
                    </span>
                  </div>
                  <p className="mt-1 text-sm text-muted tabular-nums">
                    {flag.transaction.date} · {formatMoney(flag.transaction.amount)}
                  </p>
                </div>
                <button
                  onClick={() => handleDismiss(flag)}
                  className="btn btn-ghost btn-sm shrink-0"
                >
                  Dismiss
                </button>
              </div>

              <ul className="mt-3 space-y-1 border-t border-border pt-3 text-sm">
                {flag.driving_features.map((d, i) => (
                  <li key={i} className="flex items-baseline gap-2">
                    <span className="text-brand" aria-hidden>
                      •
                    </span>
                    <span>{d.explanation}</span>
                    {d.z_score !== null && (
                      <span className="text-xs text-muted">({d.z_score}σ)</span>
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
