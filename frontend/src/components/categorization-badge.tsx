import type { CategorizationMethod } from "@/lib/types";

const METHOD_STYLES: Record<string, { label: string; className: string }> = {
  rule_exact: {
    label: "Exact match",
    className: "bg-positive-soft text-positive",
  },
  rule_fuzzy: {
    label: "Fuzzy match",
    className: "bg-brand-soft text-brand",
  },
  llm: {
    label: "LLM",
    className: "bg-warning-soft text-warning",
  },
  manual_user_correction: {
    label: "Manual",
    className: "bg-surface-3 text-secondary",
  },
};

export function CategorizationBadge({ method }: { method: CategorizationMethod }) {
  const style = method
    ? METHOD_STYLES[method]
    : { label: "Unresolved", className: "bg-surface-3 text-muted" };

  return (
    <span title={`Categorized via: ${style.label}`} className={`chip ${style.className}`}>
      {style.label}
    </span>
  );
}
