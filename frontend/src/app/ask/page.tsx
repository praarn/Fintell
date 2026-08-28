"use client";

import { useCallback, useEffect, useState } from "react";

import { RankedBarChart } from "@/components/charts/ranked-bar-chart";
import { SpendTrendChart } from "@/components/charts/spend-trend-chart";
import { ApiError } from "@/lib/api";
import { askQuestion, getAskHistory } from "@/lib/endpoints";
import type { AskChart, AskResponse, AskScalar, QueryHistoryItem } from "@/lib/types";
import { useRequireAuth } from "@/lib/use-require-auth";

const EXAMPLES = [
  "How much did I spend last month?",
  "Where did my money go in March?",
  "Who are my top merchants this year?",
  "Did I spend more on dining this month than last?",
  "Show my spending trend for the last 6 months",
  "What were my biggest transactions in December?",
];

function formatCell(value: AskScalar): string {
  if (value === null) return "—";
  if (typeof value === "number") {
    return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  return String(value);
}

function ChartView({ chart }: { chart: AskChart }) {
  const data = chart.labels.map((label, i) => ({
    label: label.replace(/_/g, " "),
    value: chart.values[i] ?? 0,
  }));

  if (chart.kind === "line") {
    return (
      <SpendTrendChart
        points={chart.labels.map((label, i) => ({
          month: label,
          total_spend: String(chart.values[i] ?? 0),
        }))}
      />
    );
  }
  return <RankedBarChart title="Result" data={data} />;
}

function AnswerCard({ answer }: { answer: AskResponse }) {
  if (!answer.answered) {
    return (
      <div className="card card-pad border-l-4 !border-l-warning bg-warning-soft/40 text-sm text-secondary">
        {answer.summary}
      </div>
    );
  }

  return (
    <div className="card card-pad space-y-4">
      <p className="text-base">{answer.summary}</p>

      {answer.rows.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs font-medium tracking-wide text-muted uppercase">
                {answer.columns.map((col) => (
                  <th key={col} className="py-2 pr-4">
                    {col.replace(/_/g, " ")}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {answer.rows.map((row, i) => (
                <tr key={i} className="border-b border-border/60 last:border-0">
                  {row.map((cell, j) => (
                    <td key={j} className="py-2 pr-4 tabular-nums">
                      {formatCell(cell)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {answer.chart && <ChartView chart={answer.chart} />}

      <p className="text-xs text-muted">
        Matched <span className="font-mono text-secondary">{answer.matched_template}</span>
        {answer.confidence !== null && ` · ${Math.round(answer.confidence * 100)}% confidence`}
      </p>
    </div>
  );
}

export default function AskPage() {
  const { user, isLoading: authLoading } = useRequireAuth();
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<AskResponse | null>(null);
  const [history, setHistory] = useState<QueryHistoryItem[]>([]);
  const [isAsking, setIsAsking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshHistory = useCallback(() => {
    getAskHistory(10).then(setHistory).catch(() => {});
  }, []);

  useEffect(() => {
    if (!user) return;
    refreshHistory();
  }, [user, refreshHistory]);

  const submit = useCallback(
    async (q: string) => {
      const trimmed = q.trim();
      if (!trimmed || isAsking) return;
      setIsAsking(true);
      setError(null);
      try {
        const result = await askQuestion(trimmed);
        setAnswer(result);
        refreshHistory();
      } catch (err) {
        setError(err instanceof ApiError ? String(err.detail) : "Something went wrong");
      } finally {
        setIsAsking(false);
      }
    },
    [isAsking, refreshHistory],
  );

  if (authLoading || !user) return null;

  return (
    <div className="page max-w-3xl">
      <div className="page-head">
        <div>
          <p className="eyebrow">Intelligence</p>
          <h1 className="page-title mt-1">Ask your finances</h1>
          <p className="page-lead">
            Ask in plain language. Questions are mapped to a fixed set of reviewed queries against
            your own transactions — the model never writes SQL, and it says so honestly when nothing
            fits. Every answer shows the underlying numbers so you can check it.
          </p>
        </div>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit(question);
        }}
        className="mt-6 flex gap-2"
      >
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="How much did I spend on groceries last month?"
          maxLength={500}
          className="input flex-1"
        />
        <button
          type="submit"
          disabled={isAsking || !question.trim()}
          className="btn btn-primary shrink-0"
        >
          {isAsking ? "Asking…" : "Ask"}
        </button>
      </form>

      <div className="mt-3 flex flex-wrap gap-2">
        {EXAMPLES.map((ex) => (
          <button
            key={ex}
            onClick={() => {
              setQuestion(ex);
              submit(ex);
            }}
            disabled={isAsking}
            className="chip border border-border bg-surface text-secondary hover:border-brand hover:text-brand disabled:opacity-50"
          >
            {ex}
          </button>
        ))}
      </div>

      {error && (
        <p className="mt-4 rounded-lg bg-negative-soft px-3 py-2 text-sm text-negative">{error}</p>
      )}

      {answer && (
        <div className="mt-6">
          <AnswerCard answer={answer} />
        </div>
      )}

      {history.length > 0 && (
        <div className="mt-10">
          <h2 className="text-sm font-semibold text-secondary">Recent questions</h2>
          <ul className="mt-2 space-y-1">
            {history.map((item) => (
              <li key={item.id}>
                <button
                  onClick={() => {
                    setQuestion(item.question_text);
                    submit(item.question_text);
                  }}
                  disabled={isAsking}
                  className="flex w-full items-baseline justify-between gap-4 rounded-lg px-2 py-1.5 text-left text-sm hover:bg-surface-2 disabled:opacity-50"
                >
                  <span className="truncate">{item.question_text}</span>
                  <span className="shrink-0 text-xs text-muted">
                    {item.declined ? "declined" : (item.matched_template ?? "")}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
