"use client";

import Link from "next/link";

import { useAuth } from "@/lib/auth-context";

const STEPS = [
  {
    title: "Create an account or use the demo",
    body: (
      <>
        Register with an email and password, or sign in with the demo account{" "}
        <span className="font-mono text-secondary">demo@fintell.app</span> /{" "}
        <span className="font-mono text-secondary">demo-password-123</span>, which comes preloaded
        with six months of synthetic multi-bank history. All demo data is generated — no real
        financial data.
      </>
    ),
  },
  {
    title: "Upload a statement",
    body: (
      <>
        Go to <NavRef href="/upload" label="Upload" /> and pick any file — CSV, TSV or plain text, a
        PDF (real or scanned), or a photo of a paper statement. Column order, date format and
        debit/credit conventions are detected automatically. Optionally attach it to an account or
        type a bank hint. Anything the parser genuinely can&apos;t read is logged for manual review
        rather than rejected.
      </>
    ),
  },
  {
    title: "Review and correct transactions",
    body: (
      <>
        <NavRef href="/transactions" label="Transactions" /> lists every parsed row with the tier
        that categorized it (exact rule, fuzzy match, or LLM). Change a category inline, or use{" "}
        <span className="font-medium text-secondary">Split</span> to divide one charge across
        categories. Corrections are remembered and improve future categorization.
      </>
    ),
  },
  {
    title: "Explore your spending",
    body: (
      <>
        <NavRef href="/dashboard" label="Dashboard" /> gives a month-to-date snapshot;{" "}
        <NavRef href="/spending" label="Spending" /> breaks outflows down by category, by merchant
        and over time. Income and transfers are excluded from spend figures.
      </>
    ),
  },
  {
    title: "Ask questions in plain language",
    body: (
      <>
        <NavRef href="/ask" label="Ask your finances" /> answers questions like &ldquo;How much did I
        spend on groceries last month?&rdquo;. Each question is mapped to a fixed, reviewed query —
        the model never writes SQL — and every answer shows the underlying numbers. If nothing fits,
        it says so instead of guessing.
      </>
    ),
  },
  {
    title: "Check flagged anomalies",
    body: (
      <>
        <NavRef href="/anomalies" label="Anomalies" /> surfaces unusual charges with the reason they
        were flagged (an off-pattern amount, a first-seen merchant, odd timing). Dismiss a flag to
        tell the model that pattern is normal for you.
      </>
    ),
  },
];

const FEATURES = [
  {
    name: "Tiered categorization",
    text: "A merchant is matched against exact then fuzzy rules first; only what's left goes to an LLM, in one batched call. Repeated LLM answers get promoted to permanent rules, so it's asked less over time.",
  },
  {
    name: "Learned bank layouts",
    text: "The first statement of a given shape goes through full detection; its column mapping is saved as a fingerprinted profile and reused for every later statement with the same structure.",
  },
  {
    name: "Explainable anomalies",
    text: "A per-account model over your own spending. Every flag carries the feature(s) that drove it in plain text, and dismissals feed back as suppressed signatures.",
  },
  {
    name: "Text-to-SQL, not a chatbot",
    text: "Questions select one of a small set of parameterized, reviewed queries. No SQL is generated, nothing crosses between users, and every question is logged.",
  },
  {
    name: "Auditable by design",
    text: "How each transaction was categorized, which layout parsed each statement, why an anomaly fired, and every sign-in / upload / download is recorded and viewable.",
  },
  {
    name: "Private storage",
    text: "Uploaded files live on the app's own disk and are never served from a static URL — downloads go through a short-lived signed link scoped to you.",
  },
];

const FAQ = [
  {
    q: "What file types can I upload?",
    a: "Any. CSV / TSV / text tables, PDFs (including scanned), and images all work. Formats the parser can't turn into transactions are stored and marked for manual review, never dropped silently.",
  },
  {
    q: "Why did my upload come back as “failed / needs manual”?",
    a: "The file parsed but no transaction rows with dates were found — often it's a summary or cover page rather than the transaction ledger. Upload the full statement (the pages with the dated line items).",
  },
  {
    q: "Does the LLM see my transactions?",
    a: "Only unresolved merchant strings are sent, and only for categorization or to pick a query template — never raw statement files, and never for free-form SQL. With no API key configured those features degrade gracefully instead of erroring.",
  },
  {
    q: "How do I manage my sessions?",
    a: "Profile lists every device that has signed in and lets you revoke any of them. Refresh tokens rotate on each use; reusing an old one revokes the whole session automatically.",
  },
  {
    q: "Can I start over?",
    a: "Delete a statement from the Upload page to remove it and its transactions. Anomaly models and spending views recompute from whatever remains.",
  },
];

function NavRef({ href, label }: { href: string; label: string }) {
  return (
    <Link href={href} className="link">
      {label}
    </Link>
  );
}

export default function GuidePage() {
  const { user } = useAuth();

  return (
    <div className="page max-w-3xl">
      <div className="page-head">
        <div>
          <p className="eyebrow">Help</p>
          <h1 className="page-title mt-1">How to use Fintell</h1>
          <p className="page-lead">
            Fintell turns a bank statement — in whatever shape your bank exports it — into
            categorized transactions, spending views, anomaly flags and a natural-language question
            box. Here&apos;s the full path from sign-up to insight.
          </p>
        </div>
        {!user && (
          <Link href="/login" className="btn btn-primary w-full sm:w-auto">
            Sign in
          </Link>
        )}
      </div>

      <section>
        <h2 className="text-sm font-semibold text-secondary">Quick start</h2>
        <ol className="mt-3 space-y-3">
          {STEPS.map((step, i) => (
            <li key={step.title} className="card card-pad flex gap-4">
              <span
                className="grid h-7 w-7 shrink-0 place-items-center rounded-md text-sm font-bold text-white"
                style={{ backgroundColor: "var(--brand)" }}
                aria-hidden
              >
                {i + 1}
              </span>
              <div>
                <p className="font-semibold">{step.title}</p>
                <p className="mt-1 text-sm leading-relaxed text-secondary">{step.body}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section className="mt-10">
        <h2 className="text-sm font-semibold text-secondary">How it works</h2>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          {FEATURES.map((f) => (
            <div key={f.name} className="card card-pad">
              <p className="font-semibold">{f.name}</p>
              <p className="mt-1 text-sm leading-relaxed text-secondary">{f.text}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="mt-10">
        <h2 className="text-sm font-semibold text-secondary">FAQ</h2>
        <dl className="mt-3 divide-y divide-border rounded-xl border border-border">
          {FAQ.map((item) => (
            <div key={item.q} className="p-4">
              <dt className="font-medium">{item.q}</dt>
              <dd className="mt-1 text-sm leading-relaxed text-secondary">{item.a}</dd>
            </div>
          ))}
        </dl>
      </section>

      <p className="mt-10 text-sm text-muted">
        {user ? (
          <>
            Ready to go — head to <NavRef href="/upload" label="Upload" /> or the{" "}
            <NavRef href="/dashboard" label="Dashboard" />.
          </>
        ) : (
          <>
            <NavRef href="/login" label="Sign in" /> or{" "}
            <NavRef href="/register" label="create an account" /> to get started.
          </>
        )}
      </p>
    </div>
  );
}
