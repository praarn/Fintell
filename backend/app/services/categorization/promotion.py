from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.llm_decision_log import LLMDecisionLog
from app.models.merchant_lookup import MerchantLookup
from app.services.categorization.constants import MATCH_TYPE_LLM_PROMOTION

settings = get_settings()


async def run_promotion_job(db: AsyncSession, min_occurrences: int | None = None) -> dict:
    """Mines llm_decision_log for merchants that have appeared at least
    `min_occurrences` times with a fully consistent LLM-assigned category,
    and promotes them into merchant_lookup. This is the actual mechanism
    behind "resolved without an LLM call" improving over time — not just a
    number, a real, running job (triggerable via POST /admin/promotion-job/
    run, and also run inline after every Tier 3 batch).
    """
    threshold = min_occurrences or settings.llm_promotion_min_occurrences

    groups = (
        await db.execute(
            select(
                LLMDecisionLog.cleaned_merchant,
                func.count(func.distinct(LLMDecisionLog.llm_category)).label("distinct_categories"),
            )
            .where(LLMDecisionLog.promoted.is_(False))
            .group_by(LLMDecisionLog.cleaned_merchant)
            .having(func.count() >= threshold)
        )
    ).all()

    promoted_merchants: list[str] = []
    for cleaned_merchant, distinct_categories in groups:
        if distinct_categories != 1:
            continue  # inconsistent LLM assignments for this merchant — don't promote

        decisions = list(
            (
                await db.scalars(
                    select(LLMDecisionLog).where(
                        LLMDecisionLog.cleaned_merchant == cleaned_merchant,
                        LLMDecisionLog.promoted.is_(False),
                    )
                )
            ).all()
        )
        category = decisions[0].llm_category
        representative_name = decisions[0].raw_merchant

        existing = await db.scalar(
            select(MerchantLookup).where(MerchantLookup.raw_pattern == cleaned_merchant)
        )
        if existing is not None:
            existing.category = category
            existing.match_type = MATCH_TYPE_LLM_PROMOTION
            existing.promoted_from_llm = True
        else:
            db.add(
                MerchantLookup(
                    raw_pattern=cleaned_merchant,
                    normalized_name=representative_name,
                    category=category,
                    match_type=MATCH_TYPE_LLM_PROMOTION,
                    promoted_from_llm=True,
                )
            )

        for decision in decisions:
            decision.promoted = True
        promoted_merchants.append(cleaned_merchant)

    await db.commit()
    return {"promoted_count": len(promoted_merchants), "promoted_merchants": promoted_merchants}
