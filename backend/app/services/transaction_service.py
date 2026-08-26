import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import Transaction
from app.models.transaction_split import TransactionSplit
from app.services.categorization.constants import CATEGORIES

UNCATEGORIZED_LABEL = "uncategorized"


class TransactionNotFoundError(Exception):
    pass


class InvalidSplitError(Exception):
    pass


@dataclass
class PagedTransactions:
    items: list[Transaction]
    total: int
    split_transaction_ids: set[uuid.UUID]


def _base_filters(
    user_id: uuid.UUID,
    account_id: uuid.UUID | None,
    category: str | None,
    start_date: date | None,
    end_date: date | None,
    search: str | None,
) -> list:
    filters = [Transaction.user_id == user_id]
    if account_id is not None:
        filters.append(Transaction.account_id == account_id)
    if category is not None:
        filters.append(Transaction.category == category)
    if start_date is not None:
        filters.append(Transaction.date >= start_date)
    if end_date is not None:
        filters.append(Transaction.date <= end_date)
    if search:
        filters.append(Transaction.raw_merchant.ilike(f"%{search}%"))
    return filters


async def list_all_transactions(
    db: AsyncSession,
    user_id: uuid.UUID,
    account_id: uuid.UUID | None = None,
    category: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> PagedTransactions:
    """The unified, cross-statement transaction table — merged across every
    account/bank the user has uploaded, sorted newest first.
    """
    filters = _base_filters(user_id, account_id, category, start_date, end_date, search)

    total = await db.scalar(select(func.count()).select_from(Transaction).where(*filters))

    rows = list(
        (
            await db.scalars(
                select(Transaction)
                .where(*filters)
                .order_by(Transaction.date.desc(), Transaction.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
    )

    split_ids = await get_split_transaction_ids(db, [t.id for t in rows])
    return PagedTransactions(items=rows, total=total or 0, split_transaction_ids=split_ids)


async def get_split_transaction_ids(
    db: AsyncSession, transaction_ids: list[uuid.UUID]
) -> set[uuid.UUID]:
    if not transaction_ids:
        return set()
    return set(
        (
            await db.scalars(
                select(TransactionSplit.transaction_id)
                .where(TransactionSplit.transaction_id.in_(transaction_ids))
                .distinct()
            )
        ).all()
    )


async def get_owned_transaction(
    db: AsyncSession, user_id: uuid.UUID, transaction_id: uuid.UUID
) -> Transaction:
    transaction = await db.scalar(
        select(Transaction).where(Transaction.id == transaction_id, Transaction.user_id == user_id)
    )
    if transaction is None:
        raise TransactionNotFoundError(str(transaction_id))
    return transaction


async def split_transaction(
    db: AsyncSession,
    user_id: uuid.UUID,
    transaction_id: uuid.UUID,
    splits: list[tuple[str, Decimal]],
) -> Transaction:
    """Splits one transaction across multiple categories. The split amounts
    must sum exactly to the parent's amount (same sign convention) — spend
    views then use the split rows for this transaction instead of its own
    category.
    """
    transaction = await get_owned_transaction(db, user_id, transaction_id)

    if len(splits) < 2:
        raise InvalidSplitError("a split needs at least two category allocations")
    for category, _amount in splits:
        if category not in CATEGORIES:
            raise InvalidSplitError(f"invalid category: {category}")

    total = sum((amount for _category, amount in splits), Decimal("0"))
    if total != transaction.amount:
        raise InvalidSplitError(
            f"split amounts sum to {total}, which does not match the transaction amount "
            f"{transaction.amount}"
        )

    await db.execute(
        TransactionSplit.__table__.delete().where(TransactionSplit.transaction_id == transaction_id)
    )
    for category, amount in splits:
        db.add(TransactionSplit(transaction_id=transaction_id, category=category, amount=amount))

    transaction.category = None
    transaction.categorization_method = None
    transaction.confidence = None

    await db.commit()
    await db.refresh(transaction)
    return transaction


async def unsplit_transaction(
    db: AsyncSession, user_id: uuid.UUID, transaction_id: uuid.UUID
) -> Transaction:
    transaction = await get_owned_transaction(db, user_id, transaction_id)
    await db.execute(
        TransactionSplit.__table__.delete().where(TransactionSplit.transaction_id == transaction_id)
    )
    await db.commit()
    await db.refresh(transaction)
    return transaction


async def get_transaction_splits(
    db: AsyncSession, transaction_id: uuid.UUID
) -> list[TransactionSplit]:
    return list(
        (
            await db.scalars(
                select(TransactionSplit).where(TransactionSplit.transaction_id == transaction_id)
            )
        ).all()
    )


def _split_subquery():
    return select(TransactionSplit.transaction_id).distinct()


async def get_spending_by_category(
    db: AsyncSession,
    user_id: uuid.UUID,
    start_date: date | None = None,
    end_date: date | None = None,
    account_id: uuid.UUID | None = None,
) -> dict[str, Decimal]:
    """Spend (outflows only — positive inflows aren't "spending") by
    category, correctly attributing split transactions to each of their
    allocated categories instead of the parent's own (cleared) category.
    """
    base = _base_filters(user_id, account_id, None, start_date, end_date, None)

    non_split_rows = (
        await db.execute(
            select(Transaction.category, func.sum(Transaction.amount))
            .where(*base, Transaction.amount < 0, Transaction.id.not_in(_split_subquery()))
            .group_by(Transaction.category)
        )
    ).all()

    split_rows = (
        await db.execute(
            select(TransactionSplit.category, func.sum(TransactionSplit.amount))
            .join(Transaction, Transaction.id == TransactionSplit.transaction_id)
            .where(*base, TransactionSplit.amount < 0)
            .group_by(TransactionSplit.category)
        )
    ).all()

    totals: dict[str, Decimal] = {}
    for category, total in non_split_rows:
        key = category or UNCATEGORIZED_LABEL
        totals[key] = totals.get(key, Decimal("0")) + abs(total or Decimal("0"))
    for category, total in split_rows:
        totals[category] = totals.get(category, Decimal("0")) + abs(total or Decimal("0"))

    return totals


def _month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


async def get_spending_trend(
    db: AsyncSession,
    user_id: uuid.UUID,
    months: int = 6,
    account_id: uuid.UUID | None = None,
) -> list[dict]:
    """Total monthly spend over the trailing `months` months, zero-filled
    for months with no spend so a chart doesn't show gaps.
    """
    today = date.today()
    start = today.replace(day=1) - relativedelta(months=months - 1)
    base = _base_filters(user_id, account_id, None, start, None, None)

    month_expr = func.date_trunc("month", Transaction.date)

    non_split_rows = (
        await db.execute(
            select(month_expr, func.sum(Transaction.amount))
            .where(*base, Transaction.amount < 0, Transaction.id.not_in(_split_subquery()))
            .group_by(month_expr)
        )
    ).all()

    split_rows = (
        await db.execute(
            select(month_expr, func.sum(TransactionSplit.amount))
            .join(Transaction, Transaction.id == TransactionSplit.transaction_id)
            .where(*base, TransactionSplit.amount < 0)
            .group_by(month_expr)
        )
    ).all()

    totals: dict[str, Decimal] = {}
    for month_start, total in [*non_split_rows, *split_rows]:
        key = _month_key(month_start.date() if hasattr(month_start, "date") else month_start)
        totals[key] = totals.get(key, Decimal("0")) + abs(total or Decimal("0"))

    result = []
    cursor = start
    for _ in range(months):
        key = _month_key(cursor)
        result.append({"month": key, "total_spend": totals.get(key, Decimal("0"))})
        cursor = cursor + relativedelta(months=1)
    return result


async def get_top_merchants(
    db: AsyncSession,
    user_id: uuid.UUID,
    start_date: date | None = None,
    end_date: date | None = None,
    account_id: uuid.UUID | None = None,
    limit: int = 10,
) -> list[dict]:
    """Ranked by total spend per merchant — uses each transaction's own
    (full) amount regardless of category splits, since splitting allocates
    category, not merchant identity.
    """
    base = _base_filters(user_id, account_id, None, start_date, end_date, None)

    rows = (
        await db.execute(
            select(
                Transaction.normalized_merchant,
                func.sum(Transaction.amount),
                func.count(),
            )
            .where(*base, Transaction.amount < 0, Transaction.normalized_merchant.is_not(None))
            .group_by(Transaction.normalized_merchant)
            .order_by(func.sum(Transaction.amount))
            .limit(limit)
        )
    ).all()

    return [
        {"merchant": merchant, "total_spend": abs(total), "transaction_count": count}
        for merchant, total, count in rows
    ]
