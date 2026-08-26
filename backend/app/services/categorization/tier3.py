import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.llm_batch_call import LLMBatchCall
from app.models.llm_decision_log import LLMDecisionLog
from app.models.merchant_lookup import MerchantLookup
from app.models.transaction import Transaction
from app.services.categorization.constants import METHOD_LLM
from app.services.categorization.llm_client import categorize_merchants_batch
from app.services.categorization.merchant_cleaner import clean_merchant_string
from app.services.categorization.promotion import run_promotion_job

settings = get_settings()


async def categorize_statement_transactions_via_llm(
    db: AsyncSession, statement_id: uuid.UUID
) -> dict:
    """Tier 3: batched LLM fallback for whatever Tier 1/2 left unresolved on
    this statement. Never one call per transaction — transactions sharing a
    cleaned merchant string are grouped and cost exactly one categorization
    decision, batched up to `llm_max_batch_size` distinct merchants per API
    call. Gracefully no-ops (no crash, nothing left half-applied) if no LLM
    key is configured or a batch call fails.
    """
    if not settings.llm_api_key:
        return {"llm_called": False, "reason": "no_api_key_configured", "categorized": 0}

    unresolved = list(
        (
            await db.scalars(
                select(Transaction).where(
                    Transaction.statement_id == statement_id,
                    Transaction.categorization_method.is_(None),
                )
            )
        ).all()
    )

    by_cleaned: dict[str, list[Transaction]] = {}
    for txn in unresolved:
        cleaned = clean_merchant_string(txn.raw_merchant)
        if cleaned:
            by_cleaned.setdefault(cleaned, []).append(txn)

    distinct_merchants = list(by_cleaned.keys())
    if not distinct_merchants:
        return {"llm_called": False, "reason": "nothing_unresolved", "categorized": 0}

    categorized_count = 0
    for start in range(0, len(distinct_merchants), settings.llm_max_batch_size):
        chunk = distinct_merchants[start : start + settings.llm_max_batch_size]
        try:
            result = await categorize_merchants_batch(chunk)
        except Exception:
            continue  # this chunk stays unresolved; not fatal to the upload

        estimated_cost = (
            result.prompt_tokens / 1000 * settings.llm_cost_per_1k_prompt_tokens
            + result.completion_tokens / 1000 * settings.llm_cost_per_1k_completion_tokens
        )
        batch_call = LLMBatchCall(
            model_used=result.model_used,
            merchant_count=len(chunk),
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            estimated_cost_usd=estimated_cost,
        )
        db.add(batch_call)
        await db.flush()

        for item in result.categorizations:
            # The model is asked to echo the merchant string back; re-clean
            # it defensively in case it altered casing/whitespace.
            key = (
                item.merchant
                if item.merchant in by_cleaned
                else clean_merchant_string(item.merchant)
            )
            transactions = by_cleaned.get(key)
            if not transactions:
                continue

            for txn in transactions:
                txn.category = item.category
                txn.categorization_method = METHOD_LLM
                txn.confidence = item.confidence
            categorized_count += len(transactions)

            db.add(
                LLMDecisionLog(
                    raw_merchant=transactions[0].raw_merchant,
                    cleaned_merchant=key,
                    llm_category=item.category,
                    confidence=item.confidence,
                    model_used=result.model_used,
                    batch_id=batch_call.id,
                )
            )

    await db.commit()
    await run_promotion_job(db)
    return {"llm_called": True, "categorized": categorized_count}


async def compute_llm_stats(db: AsyncSession) -> dict:
    totals = (
        await db.execute(
            select(
                func.count(LLMBatchCall.id),
                func.coalesce(func.sum(LLMBatchCall.merchant_count), 0),
                func.coalesce(func.sum(LLMBatchCall.prompt_tokens), 0),
                func.coalesce(func.sum(LLMBatchCall.completion_tokens), 0),
                func.coalesce(func.sum(LLMBatchCall.estimated_cost_usd), 0.0),
            )
        )
    ).one()
    total_calls, total_merchants, prompt_tokens, completion_tokens, total_cost = totals

    promoted_count = await db.scalar(
        select(func.count())
        .select_from(MerchantLookup)
        .where(MerchantLookup.promoted_from_llm.is_(True))
    )

    return {
        "total_batch_calls": total_calls,
        "total_merchants_categorized": total_merchants,
        "total_prompt_tokens": prompt_tokens,
        "total_completion_tokens": completion_tokens,
        "total_estimated_cost_usd": round(float(total_cost), 6),
        "promoted_merchant_count": promoted_count or 0,
    }
