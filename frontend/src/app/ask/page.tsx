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
      <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-900/40 dark:bg-amber-950/30 dark:text-amber-200">
        {answer.summary}
      </div>
    );
  }

  return (
    <div className="space-y-4 rounded-xl border border-black/[.08] p-5 dark:border-white/[.145]">
      <p className="text-base">{answer.summary}</p>

      {answer.rows.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-black/[.08] text-left text-zinc-500 dark:border-white/[.145]">
                {answer.columns.map((col) => (
                  <th key={col} className="py-1.5 pr-4 font-medium">
                    {col.replace(/_/g, " ")}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {answer.rows.map((row, i) => (
                <tr
                  key={i}
                  className="border-b border-black/[.04] last:border-0 dark:border-white/[.06]"
                >
                  {row.map((cell, j) => (
                    <td key={j} className="py-1.5 pr-4 tabular-nums">
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

      <p className="text-xs text-zinc-400">
        Matched <span className="font-mono">{answer.matched_template}</span>
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
    <div className="mx-auto max-w-3xl px-6 py-10">
      <h1 className="text-xl font-semibold">Ask your finances</h1>
      <p className="mt-2 text-sm text-zinc-500">
        Ask in plain language. Questions are mapped to a fixed set of reviewed queries against your
        own transactions — the model never writes SQL, and it says so honestly when nothing fits.
        Every answer shows the underlying numbers so you can check it.
      </p>

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
          className="flex-1 rounded-lg border border-black/[.12] px-3 py-2 text-sm outline-none focus:border-black/[.3] dark:border-white/[.2] dark:bg-black dark:focus:border-white/[.4]"
        />
        <button
          type="submit"
          disabled={isAsking || !question.trim()}
          className="rounded-lg border border-black/[.12] px-4 py-2 text-sm hover:bg-black/[.04] disabled:opacity-50 dark:border-white/[.2] dark:hover:bg-white/[.08]"
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
            className="rounded-full border border-black/[.08] px-3 py-1 text-xs text-zinc-600 hover:bg-black/[.04] disabled:opacity-50 dark:border-white/[.145] dark:text-zinc-300 dark:hover:bg-white/[.08]"
          >
            {ex}
          </button>
        ))}
      </div>

      {error && (
        <p className="mt-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/30 dark:text-red-300">
          {error}
        </p>
      )}

      {answer && (
        <div className="mt-6">
          <AnswerCard answer={answer} />
        </div>
      )}

      {history.length > 0 && (
        <div className="mt-10">
          <h2 className="text-sm font-medium text-zinc-500">Recent questions</h2>
          <ul className="mt-2 space-y-1">
            {history.map((item) => (
              <li key={item.id}>
                <button
                  onClick={() => {
                    setQuestion(item.question_text);
                    submit(item.question_text);
                  }}
                  disabled={isAsking}
                  className="flex w-full items-baseline justify-between gap-4 rounded-md px-2 py-1.5 text-left text-sm hover:bg-black/[.04] disabled:opacity-50 dark:hover:bg-white/[.06]"
                >
                  <span className="truncate">{item.question_text}</span>
                  <span className="shrink-0 text-xs text-zinc-400">
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
