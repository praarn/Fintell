# Master Prompt — Personal Finance Statement Intelligence

> Copy everything below into Claude Code (or Claude with computer/file tools) as your project brief.
> It's written to be handed over in one shot, then worked through phase by phase — tell Claude
> "start with Phase 1" rather than asking for everything at once in a single response.

---

You are helping me build a full-stack, portfolio-grade project called **Personal Finance Statement
Intelligence**. Read this entire brief before writing any code. Build it phase by phase, in the order
given at the end — do not skip ahead or generate the whole app in one pass. After each phase, stop,
summarize what was built, list any assumptions you made, and wait for me to confirm before
continuing.

## What this project is

Bank statements (PDF or CSV) come in wildly inconsistent formats across banks, with no shared
schema. The core engineering problem is: **parse arbitrary statement formats without hardcoding a
template per bank**, categorize transactions **cost-efficiently** (deterministic rules first, LLM only
as an expensive last resort, with a feedback loop that shrinks LLM usage over time), and answer
natural-language questions about a user's own transactions via **safe, constrained text-to-SQL** —
not embeddings-based RAG, which is the wrong tool for structured numeric data and you should be
explicit about that reasoning in the code and docs. Treat the tiered parsing/categorization pipeline
and its cost-tracking as the main deliverable; the chat feature is secondary.

## Hard constraints — do not deviate from these

**Tech stack (exactly this, nothing else):**
- Frontend: Next.js 15/16, TypeScript, Tailwind CSS
- Backend: Python, FastAPI, Pydantic (v2)
- Database: PostgreSQL only — no separate vector DB (this project does not need embeddings; see the
  text-to-SQL section below), no Redis, no Elasticsearch
- AI/Data: Python, Pandas, NumPy, scikit-learn, `rapidfuzz` for fuzzy string matching, an LLM API
  (assume an OpenAI-compatible or Anthropic API accessible via an environment variable — never
  hardcode a key)
- Auth: JWT access tokens (short-lived) + refresh tokens, **rotated on every use**, with reuse-detection
  (a presented, already-rotated-out refresh token triggers revocation of the entire session family)
- Infra: Docker + Docker Compose only — **no Kubernetes, no Jenkins, no Helm, no Terraform**
- CI: GitHub Actions only
- Testing: Pytest + FastAPI TestClient

**Non-negotiable engineering principles:**
1. Parsing is tiered and the tiers are explicit in code: Tier 1 (deterministic regex/column parsing),
   Tier 2 (rules + fuzzy-match categorization), Tier 3 (LLM fallback, batched, only for
   low-confidence cases). Never call the LLM per-transaction when a batch call would do; never call
   it at all for a transaction Tier 1/2 already resolved with high confidence.
2. The LLM must never construct or execute arbitrary SQL. For the "ask your finances" feature, the
   LLM selects from a fixed, reviewed set of parameterized query templates and fills typed parameters,
   which are validated with Pydantic before execution. All queries are scoped by `user_id` at the
   query-builder level regardless of what the LLM outputs — defense in depth, not just trust.
3. Every transaction stores exactly how it was categorized (`rule_exact` / `rule_fuzzy` / `llm` /
   `manual_user_correction`) — this field is not optional, it's the auditability story.
4. Build the LLM-decision-log-to-merchant-lookup **promotion job** for real — it's the actual
   mechanism that reduces LLM calls over time, not just a metric you report. Don't fake the "94%
   resolved without an LLM call" claim; make it a real, computable number from real logged decisions.
5. No transaction line is ever silently dropped if it fails to parse — log it to a `parse_failures`
   table with the raw text, always inspectable.
6. Be honest in code comments and the README about what's a genuine ML model versus a heuristic or
   rule-based system. Don't oversell an `IsolationForest` as more than it is; do explain its features
   clearly since explainability is the actual value here.
7. Write tests as you build each feature, not as an afterthought. Every phase below ends with its own
   test suite, and the parser fixture set (multiple deliberately inconsistent bank statement formats)
   is the centerpiece of the whole test suite — treat it with real care.
8. Never use real financial data anywhere in this repo, including seed/fixture data — generate
   believable synthetic statements instead.

## Full feature list

Use the feature spec below as the definitive scope. Ask me before adding anything not listed here.

[Paste the full contents of `finance-features.md` here before sending this prompt — sections 1
through 10, covering: statement ingestion and adaptive bank profiles, merchant normalization and
categorization tiers, LLM fallback and the promotion job, transaction/spending views, anomaly
detection with explainability, text-to-SQL "ask your finances," auth and security, testing, infra/CI,
and resume-worthy metrics.]

## Data model expectations (adjust as needed, but keep this shape)

```
users(id, email, hashed_password, created_at)
refresh_tokens(id, user_id, token_hash, family_id, revoked, expires_at, created_at,
               user_agent, ip_at_creation)
statements(id, user_id, bank_hint, bank_profile_id, uploaded_at, file_path, parse_status)
bank_profiles(id, fingerprint, column_map_json, date_format, amount_sign_convention,
              learned_at, times_used)
parse_failures(id, statement_id, raw_line_text, reason, created_at)
transactions(id, statement_id, user_id, raw_merchant, normalized_merchant, category, amount,
             date, categorization_method, confidence, created_at)
merchant_lookup(id, raw_pattern, normalized_name, category, match_type, created_at, promoted_from_llm)
llm_decision_log(id, raw_merchant, cleaned_merchant, llm_category, confidence, model_used,
                  batch_id, created_at, promoted boolean)
anomaly_flags(id, transaction_id, user_id, severity, driving_features_json, dismissed, created_at)
query_template_log(id, user_id, question_text, matched_template, params_json, result_summary,
                    created_at)
audit_log(id, actor_id, action, target_table, target_id, created_at)
```

## Build phases — work through these in order, one at a time

**Phase 0 — Foundation**
Scaffold the repo structure, Docker Compose (postgres, backend, frontend — no vector extension
needed here), FastAPI app skeleton with health check, Next.js skeleton with Tailwind configured,
`pydantic-settings` config, Alembic set up, GitHub Actions workflow running lint + pytest against a
real Postgres service container + frontend build. Get CI green on an empty-but-real skeleton before
building features.

**Phase 1 — Auth**
JWT access/refresh implementation with rotation on every use, reuse-detection revoking the entire
session family, per-session device/IP metadata, user-facing active-sessions list/revoke endpoint,
full test coverage of login/refresh/reuse-detection/revocation flows.

**Phase 2 — Tier 1 parsing pipeline (the core deliverable)**
CSV and PDF ingestion, file-structure sniffing, column-role classification (header synonym matching +
dtype sniffing), `pdfplumber` table extraction for PDFs, regex line-parsing fallback for PDFs without
clean tables, adaptive bank-profile learning and reuse (fingerprint-based, not name-based), parse
failure logging. Build a fixture set of at least 5-8 deliberately different statement formats
(different column orders, date formats, debit sign conventions, at least one requiring OCR) before
writing tests, and use that same fixture set as the primary test suite for this phase. Report the
learned-profile-reuse rate as a real computed metric.

**Phase 3 — Tier 2 categorization**
Merchant string cleanup (regex-based boilerplate stripping), `merchant_lookup` table with exact and
`rapidfuzz` fuzzy matching, confidence scoring, `categorization_method` tracking end to end including
UI badges showing how each transaction was categorized.

**Phase 4 — Tier 3 LLM fallback + promotion job**
Batched LLM categorization for low-confidence transactions with a fixed category enum via structured
output, full decision logging, and — critically — a real scheduled/triggerable promotion job that
mines the decision log and promotes repeated high-consistency merchants into `merchant_lookup`. Test
this job explicitly: seed a fake decision log, assert promotion happens at the right threshold, assert
subsequent identical transactions resolve at Tier 2 without hitting the LLM.

**Phase 5 — Transaction & spending views**
Unified cross-statement transaction table, category breakdowns and trends, multi-account support,
manual transaction splitting, recurring-transaction detection via periodicity heuristics.

**Phase 6 — Anomaly detection**
Per-user `IsolationForest` on amount/category/frequency/novelty features, explainability layer
surfacing which feature(s) drove a flag, periodic per-user refit, dismissible UI feed with dismissal
feedback. Test against synthetic transaction histories with a known injected anomaly.

**Phase 7 — Text-to-SQL "ask your finances"**
Fixed, reviewed set of parameterized query templates, LLM template-selection + typed parameter
filling validated by Pydantic, mandatory `user_id` scoping at the query-builder level regardless of
LLM output, honest decline behavior when no template matches confidently, results shown transparently
(numbers/small chart, not just prose). Mock the LLM's template-selection call in tests and assert
correct results against seeded fixtures, plus a test proving user-scoping can't be bypassed even with
an adversarial LLM output.

**Phase 8 — Security hardening & polish**
Encrypted-at-rest or signed-URL access for uploaded statement files, rate limiting on upload/auth
endpoints, full audit logging of sensitive actions, seed script with synthetic multi-bank statement
fixtures for instant demo-readiness, cost-tracking/stats admin page, README documenting architecture
decisions (especially the "text-to-SQL not RAG" reasoning) and real measured metrics from the
"resume-worthy metrics" section of the feature spec.

## What I want from you at each phase

- Working code, not pseudocode — actual files, actual tests that run.
- A short rationale for any non-obvious design decision (e.g., why fingerprint-based bank profiles
  instead of name-based, why text-to-SQL templates instead of raw LLM-generated SQL).
- A list of what you assumed or simplified, so I can correct course early.
- Don't move to the next phase until I say go.

Start with Phase 0.
