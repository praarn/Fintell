import type { CategorizationMethod } from "@/lib/types";

const METHOD_STYLES: Record<string, { label: string; className: string }> = {
  rule_exact: {
    label: "Exact match",
    className: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300",
  },
  rule_fuzzy: {
    label: "Fuzzy match",
    className: "bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-300",
  },
  llm: {
    label: "LLM",
    className: "bg-violet-100 text-violet-800 dark:bg-violet-900/40 dark:text-violet-300",
  },
  manual_user_correction: {
    label: "Manual",
    className: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300",
  },
};

export function CategorizationBadge({ method }: { method: CategorizationMethod }) {
  const style = method
    ? METHOD_STYLES[method]
    : {
        label: "Unresolved",
        className: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400",
      };

  return (
    <span
      title={`Categorized via: ${style.label}`}
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${style.className}`}
    >
      {style.label}
    </span>
  );
}
