import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.merchant_lookup import MerchantLookup
from app.models.transaction import Transaction
from app.services.categorization.constants import (
    CATEGORIES,
    MATCH_TYPE_USER_CORRECTION,
    METHOD_MANUAL_USER_CORRECTION,
)
from app.services.categorization.matcher import MerchantMatcher
from app.services.categorization.merchant_cleaner import clean_merchant_string

settings = get_settings()


class InvalidCategoryError(Exception):
    pass


class TransactionNotFoundError(Exception):
    pass


async def _load_matcher(db: AsyncSession) -> MerchantMatcher:
    rows = list((await db.scalars(select(MerchantLookup))).all())
    return MerchantMatcher(rows, settings.categorization_confidence_threshold)


async def categorize_statement_transactions(
    db: AsyncSession, statement_id: uuid.UUID
) -> dict[str, int]:
    """Tier 2: runs immediately after Tier 1 parsing, for every transaction
    on this statement. Transactions the matcher can't confidently resolve
    are left uncategorized (categorization_method stays None) — that's
    exactly the set Tier 3 (Phase 4) will pick up.
    """
    matcher = await _load_matcher(db)
    transactions = list(
        (
            await db.scalars(select(Transaction).where(Transaction.statement_id == statement_id))
        ).all()
    )

    counts = {"rule_exact": 0, "rule_fuzzy": 0, "unresolved": 0}
    for txn in transactions:
        cleaned = clean_merchant_string(txn.raw_merchant)
        outcome = matcher.match(cleaned)
        if outcome is None:
            txn.normalized_merchant = cleaned or txn.raw_merchant
            counts["unresolved"] += 1
            continue

        txn.normalized_merchant = outcome.normalized_name
        txn.category = outcome.category
        txn.categorization_method = outcome.method
        txn.confidence = outcome.confidence
        counts[outcome.method] += 1

    await db.commit()
    return counts


async def recategorize_transaction(
    db: AsyncSession, user_id: uuid.UUID, transaction_id: uuid.UUID, new_category: str
) -> Transaction:
    """A manual correction both fixes this transaction and feeds back into
    merchant_lookup (global, like bank profiles) so future transactions
    from the same cleaned merchant string resolve at Tier 2 directly —
    closing the loop, same mechanism the Phase 4 LLM-promotion job uses.
    """
    if new_category not in CATEGORIES:
        raise InvalidCategoryError(new_category)

    transaction = await db.scalar(
        select(Transaction).where(Transaction.id == transaction_id, Transaction.user_id == user_id)
    )
    if transaction is None:
        raise TransactionNotFoundError(str(transaction_id))

    transaction.category = new_category
    transaction.categorization_method = METHOD_MANUAL_USER_CORRECTION
    transaction.confidence = 1.0

    cleaned = clean_merchant_string(transaction.raw_merchant)
    if cleaned:
        transaction.normalized_merchant = transaction.normalized_merchant or cleaned
        existing = await db.scalar(
            select(MerchantLookup).where(MerchantLookup.raw_pattern == cleaned)
        )
        if existing is not None:
            existing.category = new_category
            existing.match_type = MATCH_TYPE_USER_CORRECTION
        else:
            db.add(
                MerchantLookup(
                    raw_pattern=cleaned,
                    normalized_name=transaction.normalized_merchant,
                    category=new_category,
                    match_type=MATCH_TYPE_USER_CORRECTION,
                )
            )

    await db.commit()
    await db.refresh(transaction)
    return transaction


async def compute_categorization_stats(db: AsyncSession) -> dict:
    method_rows = (
        await db.execute(
            select(Transaction.categorization_method, func.count()).group_by(
                Transaction.categorization_method
            )
        )
    ).all()
    by_method: dict[str, int] = {}
    unresolved = 0
    for method, count in method_rows:
        if method is None:
            unresolved = count
        else:
            by_method[method] = count

    total = sum(by_method.values()) + unresolved
    resolved_without_llm = sum(count for method, count in by_method.items() if method != "llm")
    pct_resolved_without_llm = (resolved_without_llm / total * 100.0) if total else 0.0

    return {
        "total_transactions": total,
        "by_categorization_method": {**by_method, "unresolved": unresolved},
        "pct_resolved_without_llm": round(pct_resolved_without_llm, 1),
    }
