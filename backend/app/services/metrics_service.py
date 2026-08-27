"""The handful of numbers worth putting on a resume, computed live from
whatever's in the database. Mirrors the "metrics worth capturing" list in
docs/finance-features.md.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.query_template_log import QueryTemplateLog
from app.models.transaction import Transaction
from app.services.categorization.constants import METHOD_LLM
from app.services.categorization.tier3 import compute_llm_stats
from app.services.statement_service import compute_stats

_DETERMINISTIC_METHODS = ("rule_exact", "rule_fuzzy", "manual_user_correction")


async def compute_resume_metrics(db: AsyncSession) -> dict:
    method_rows = (
        await db.execute(
            select(Transaction.categorization_method, func.count()).group_by(
                Transaction.categorization_method
            )
        )
    ).all()
    by_method = {(m or "unresolved"): c for m, c in method_rows}
    total_txns = sum(by_method.values())
    categorized = total_txns - by_method.get("unresolved", 0)
    deterministic = sum(by_method.get(m, 0) for m in _DETERMINISTIC_METHODS)
    llm = by_method.get(METHOD_LLM, 0)

    pct_deterministic = (deterministic / categorized * 100.0) if categorized else 0.0
    pct_llm = (llm / categorized * 100.0) if categorized else 0.0

    template_total = await db.scalar(select(func.count()).select_from(QueryTemplateLog)) or 0
    template_answered = (
        await db.scalar(
            select(func.count()).where(QueryTemplateLog.matched_template.is_not(None))
        )
        or 0
    )
    match_rate = (template_answered / template_total * 100.0) if template_total else 0.0

    parse_stats = await compute_stats(db)
    llm_stats = await compute_llm_stats(db)

    return {
        "transactions_total": total_txns,
        "transactions_categorized": categorized,
        "categorization_by_method": by_method,
        "pct_categorized_deterministically": round(pct_deterministic, 1),
        "pct_categorized_via_llm": round(pct_llm, 1),
        "pct_statements_via_learned_profile": parse_stats["pct_profile_reuse"],
        "distinct_bank_profiles": parse_stats["distinct_bank_profiles"],
        "total_statements_processed": parse_stats["total_statements_processed"],
        "llm_batch_calls": llm_stats["total_batch_calls"],
        "llm_merchants_categorized": llm_stats["total_merchants_categorized"],
        "llm_estimated_cost_usd": round(llm_stats["total_estimated_cost_usd"], 4),
        "text_to_sql_questions": template_total,
        "text_to_sql_answered": template_answered,
        "text_to_sql_match_rate": round(match_rate, 1),
    }
