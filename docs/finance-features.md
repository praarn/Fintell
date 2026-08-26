# Personal Finance Statement Intelligence — Feature Spec

## What makes this project unique
Budgeting apps either force manual categorization or plug into Plaid/bank-API aggregators that do the
hard parsing work for you invisibly. This project does the opposite on purpose: it takes **arbitrary,
unstructured bank statement exports** (PDF or CSV, any bank, any layout) and builds its own tiered
parsing/categorization pipeline — deterministic first, LLM only as an expensive last resort. The real
IP is the **cost-and-confidence-aware routing logic**, not the LLM call. That's a genuinely defensible
engineering story, and it's also the part every fintech-adjacent interviewer will poke at.

Tech stack fixed per your requirements: Next.js 15/16 + TypeScript + Tailwind, FastAPI + Pydantic,
PostgreSQL (+ pgvector only if/where genuinely needed — see RAG section below, where the honest
answer is "don't use embeddings, use text-to-SQL"), Docker Compose, GitHub Actions, Pytest +
TestClient, JWT access/refresh with rotation. No Kubernetes, no Jenkins.

---

## 1. Statement Ingestion (Tier 1 — deterministic parsing)

- [ ] Upload endpoint accepting PDF or CSV bank statements, arbitrary bank of origin
- [ ] File-type + structure sniffing: detect clean CSV vs PDF-with-table vs PDF-without-clean-table
      before choosing a parse strategy
- [ ] CSV path: header-row detection (banks don't agree on column names/order — build a
      column-role classifier using simple heuristics: dtype sniffing, header keyword matching against
      a maintained synonym list like `{date, txn date, value date} → date`)
- [ ] PDF-with-table path: `pdfplumber` table extraction, then the same column-role classifier applied
      to the extracted table headers
- [ ] PDF-without-clean-table path: line-by-line regex parsing tuned to common statement line
      patterns (date + description + amount + optional running balance), with a per-bank "profile"
      that's *learned*, not hardcoded — see 1.1 below
- [ ] Store `bank_hint` (user-provided or inferred from statement header text/logo OCR) and
      `parse_status` (`parsed_clean` / `parsed_with_warnings` / `failed_needs_manual`)
- [ ] Never silently drop a row that doesn't parse — log it to a `parse_failures` table with the raw
      line text, so failure patterns are visible and debuggable, not invisible

### 1.1 Adaptive per-bank profiles (this is the "no hardcoded templates" story)
- [ ] After a statement from a previously-unseen bank is successfully parsed once (even if it required
      more manual correction the first time), persist a lightweight "profile" — column order, date
      format, amount sign convention (some banks show debits as negative, others as a separate
      column) — keyed by a bank fingerprint (header text similarity, not just bank name string)
- [ ] Next statement from the same bank tries its saved profile first, falls back to full detection if
      the profile doesn't match cleanly — this means the system **gets better per-bank over time**
      without you ever writing `if bank == "HDFC": ...` style code
- [ ] Expose a simple metric: number of distinct bank profiles learned, and % of statements parsed via
      an existing profile vs full cold-detection — a genuinely good number to quote in an interview

---

## 2. Merchant Normalization & Categorization (Tier 2 — rules + fuzzy matching)

- [ ] Raw merchant string cleanup pipeline: strip transaction reference codes, POS terminal IDs, city
      suffixes, card-network boilerplate (`POS`, `NEFT`, `UPI-`, trailing digit strings) via regex
      before any matching happens — most of the "AI-sounding" merchant normalization problem is
      actually solved by boring string cleanup, and being explicit about that in your README is a
      good honesty signal
- [ ] Maintained `merchant_lookup` table (raw pattern → normalized name → category), seeded with a
      reasonably sized starter set of common merchants (transit, food delivery, utilities, subscriptions,
      etc.)
- [ ] Fuzzy matching via `rapidfuzz` against the lookup table for near-misses (typos, minor variants)
      with a similarity threshold; log the matched score so you can tune the threshold later against
      real data
- [ ] Confidence score per categorization attempt combining: exact match / fuzzy match score /
      no match
- [ ] Only transactions below the confidence threshold escalate to Tier 3 — this threshold should be a
      configurable setting, and you should be able to show what % of transactions your system routes
      to each tier

---

## 3. LLM Fallback (Tier 3 — used sparingly, on purpose)

- [ ] Batched LLM categorization calls (never one API call per transaction — batch N uncategorized
      merchants per request to control cost) with categories constrained to a fixed enum via
      structured output, so the LLM can't invent free-text categories that break downstream analytics
- [ ] Every LLM decision logged in full: input (raw + cleaned merchant string), output category,
      confidence, model used, timestamp — this log **is** your growing labeled dataset
- [ ] Periodic batch job that mines the LLM decision log: any merchant string appearing ≥N times
      with a consistent LLM-assigned category gets automatically promoted into the permanent
      `merchant_lookup` table — this is the actual mechanism behind the "94% resolved without an LLM
      call after N months" claim; make sure it's a real, running promotion job, not just a talking point
- [ ] Cost tracking: running count of LLM calls made and estimated token cost, surfaced on a small
      admin/stats page — concrete evidence of the "cost-efficient" claim

### 3.1 categorization_method auditability
- [ ] Every transaction stores exactly how it was categorized: `rule_exact`, `rule_fuzzy`, `llm`,
      `manual_user_correction` — surfaced in the UI (a small badge/icon per transaction) so users (and
      you, in a demo) can see the system's reasoning path, not just its output
- [ ] When a user manually recategorizes a transaction, that correction both fixes the transaction and
      feeds back into the merchant lookup table (same promotion mechanism as 3.), closing the loop

---

## 4. Transactions & Spending Views

- [ ] Unified transaction table across all uploaded statements (merged across banks/accounts, dated
      and sorted)
- [ ] Category breakdown views: monthly spend by category, trend over time, top merchants
- [ ] Multi-account support: user can upload statements from several accounts/banks, see either
      per-account or consolidated views
- [ ] Manual transaction split (one raw transaction, multiple categories — e.g., a big-box store
      purchase split between groceries and household items)
- [ ] Recurring transaction detection (subscriptions, rent, EMIs) via simple periodicity detection on
      normalized merchant + amount pattern — flagged distinctly in the UI

---

## 5. Anomaly Detection (sklearn)

- [ ] Per-user `IsolationForest` on a feature vector per transaction: amount (normalized per category),
      category frequency, day-of-week/time-of-month pattern, merchant novelty (has this user
      transacted with this merchant before)
- [ ] Explainability layer: don't just flag "anomalous" — surface *which feature(s) drove the flag*
      (e.g., "amount is 4.2x your typical spend in this category" vs "first time transacting with this
      merchant") — explainable anomaly detection is a much stronger interview story than a bare flag
- [ ] Retrain/refresh cadence: model refits periodically as new transactions arrive (per-user, so a
      user's "normal" evolves with their actual spending)
- [ ] Anomaly feed in the UI, dismissible per-item (dismissals should also feed back into future model
      behavior, at least as a simple heuristic weight adjustment)

---

## 6. "Ask Your Finances" — Text-to-SQL, Not RAG

- [ ] Be explicit in the architecture (and say this in an interview) that transaction-question-answering
      is a **structured data problem**, not a semantic retrieval problem — embeddings over numeric
      rows lose precision that a real query doesn't
- [ ] LLM generates a constrained, parameterized query against a **fixed, reviewed query template
      set** scoped to the `transactions` table (not raw SQL string concatenation) — e.g., the LLM picks
      a template (`sum_by_category_and_period`, `top_n_merchants`, `compare_periods`) and fills
      typed parameters, which you validate with Pydantic before execution
- [ ] Never let the LLM construct arbitrary SQL directly against the database — this is a security
      boundary worth stating explicitly in the README (prevents injection, prevents cross-user data
      leakage, keeps the query surface auditable)
- [ ] Every query scoped by `user_id` at the query-builder level (not just trusted from LLM output) —
      defense in depth
- [ ] Natural language question → resolved template + parameters → executed query → natural
      language answer with the underlying numbers shown transparently (a small table or chart, not
      just prose), so the user can verify the answer themselves
- [ ] Fallback: if no template matches the question with confidence, say so honestly rather than
      guessing — same "defensible over impressive" principle as your other projects

---

## 7. Auth & Security (this data is sensitive — treat it that way)

- [ ] JWT access (short-lived) + refresh token, refresh tokens **rotated on every use** (old one
      invalidated immediately, reuse-detection — if a rotated-out refresh token is presented again,
      treat it as a possible theft and revoke the entire session family)
- [ ] Per-session device/user-agent/IP-at-creation stored; user-facing "active sessions" page to view
      and revoke individual sessions
- [ ] Uploaded statement files stored encrypted at rest (or at minimum, access-controlled with signed,
      expiring URLs — don't serve raw statement files from a public static path)
- [ ] Rate limiting on upload and auth endpoints
- [ ] Full audit log of sensitive actions: statement upload, deletion, export, session revocation

---

## 8. Testing (Pytest + FastAPI TestClient)

- [ ] Parser tests: a fixture set of at least 5–8 statements in deliberately different formats
      (different column orders, different date formats, one with negative-for-debit convention, one
      with separate debit/credit columns, at least one scanned-image PDF requiring OCR) — this
      fixture set is the centerpiece of your test suite, same principle as the water quality project
- [ ] Merchant normalization tests: known raw strings → expected normalized name + category,
      covering exact match, fuzzy match, and no-match-escalates-to-LLM paths (mock the LLM call)
- [ ] Categorization promotion job tests: seed a fake LLM decision log with a repeated merchant,
      assert it gets promoted into `merchant_lookup` after the threshold
- [ ] Anomaly detection tests: synthetic per-user transaction history with an injected anomalous
      transaction, assert it's flagged with the correct explaining feature
- [ ] Text-to-SQL tests: a set of natural-language questions mapped to expected template + params
      (mock the LLM's template-selection call), assert the executed query returns correct results
      against a seeded transaction fixture, and assert user-scoping can't be bypassed
- [ ] Auth tests: login, refresh rotation, reuse-detection triggering session revocation, session
      list/revoke endpoints

---

## 9. Infra & CI/CD

- [ ] `docker-compose.yml`: `postgres`, `backend`, `frontend` (no pgvector needed here unless you
      want it for something else — this project's "RAG" is intentionally not embedding-based)
- [ ] `pydantic-settings` for config, secrets never hardcoded
- [ ] GitHub Actions: lint → pytest (with Postgres service container, running the full parser fixture
      suite) → frontend build/typecheck → `docker compose build` sanity check
- [ ] Alembic migrations
- [ ] Seed script with a handful of synthetic-but-realistic multi-bank statement fixtures so a fresh
      clone is demoable immediately (never use anyone's real financial data, obviously — generate
      believable synthetic statements)

---

## 10. Metrics worth capturing for your resume / interview talking points

- [ ] % of transactions resolved at Tier 1/2 vs escalated to Tier 3 (LLM), tracked over time as the
      merchant lookup table grows — this is your headline number
- [ ] % of statements parsed via an existing learned bank profile vs cold-detection
- [ ] LLM call volume and estimated cost, before/after the promotion job has been running for a while
- [ ] Anomaly detection precision/recall against a synthetic injected-anomaly test set
- [ ] Text-to-SQL template-match rate (% of natural-language questions resolved by a template vs
      honestly declined)

---

## Suggested build order

1. Auth (rotation + reuse-detection is worth building carefully here, it's a real security feature) +
   Docker + CI skeleton
2. Tier 1 parsing pipeline + parse-failure logging + adaptive bank profiles (the core story — get this
   right before anything else)
3. Tier 2 merchant normalization + fuzzy matching + categorization_method auditability
4. Tier 3 LLM fallback + decision logging + promotion job (this is what makes the "94% without LLM"
   claim real — don't skip the promotion job, it's the actual mechanism, not just the metric)
5. Transaction views, multi-account support, recurring detection
6. Anomaly detection with explainability
7. Text-to-SQL "ask your finances" feature
8. Polish: seed data, session management UI, cost-tracking dashboard, README with your honest
   scoping notes and real measured metrics
