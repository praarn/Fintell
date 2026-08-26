import statistics
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import Transaction

MIN_OCCURRENCES = 3
AMOUNT_TOLERANCE_PCT = Decimal("0.1")
AMOUNT_TOLERANCE_FLOOR = Decimal("5.00")

# (label, typical gap in days) — checked in order, first tolerance match wins.
FREQUENCY_BUCKETS = [
    ("weekly", 7),
    ("biweekly", 14),
    ("monthly", 30),
    ("quarterly", 90),
    ("yearly", 365),
]
FREQUENCY_TOLERANCE_PCT = 0.25
GAP_REGULARITY_TOLERANCE_PCT = 0.25
GAP_REGULARITY_FLOOR_DAYS = 3


@dataclass
class RecurringGroup:
    normalized_merchant: str
    typical_amount: Decimal
    frequency_label: str
    occurrences: int
    last_date: date
    next_expected_date: date
    transaction_ids: list[uuid.UUID]


def _cluster_by_amount(transactions: list[Transaction]) -> list[list[Transaction]]:
    """Greedy 1D clustering: sort by amount, start a new cluster whenever
    the gap to the previous amount exceeds tolerance. Handles both
    fixed-price subscriptions and slightly-varying bills (utilities).
    """
    ordered = sorted(transactions, key=lambda t: t.amount)
    clusters: list[list[Transaction]] = []
    for txn in ordered:
        if clusters:
            reference = clusters[-1][-1].amount
            tolerance = max(AMOUNT_TOLERANCE_FLOOR, abs(reference) * AMOUNT_TOLERANCE_PCT)
            if abs(txn.amount - reference) <= tolerance:
                clusters[-1].append(txn)
                continue
        clusters.append([txn])
    return clusters


def _classify_frequency(mean_gap_days: float) -> str | None:
    for label, target in FREQUENCY_BUCKETS:
        if abs(mean_gap_days - target) <= target * FREQUENCY_TOLERANCE_PCT:
            return label
    return None


def _analyze_cluster(merchant: str, cluster: list[Transaction]) -> RecurringGroup | None:
    if len(cluster) < MIN_OCCURRENCES:
        return None

    ordered = sorted(cluster, key=lambda t: t.date)
    gaps = [(ordered[i].date - ordered[i - 1].date).days for i in range(1, len(ordered))]
    if not gaps or any(g <= 0 for g in gaps):
        return None

    mean_gap = statistics.mean(gaps)
    stdev_gap = statistics.pstdev(gaps) if len(gaps) > 1 else 0.0
    tolerance = max(GAP_REGULARITY_FLOOR_DAYS, mean_gap * GAP_REGULARITY_TOLERANCE_PCT)
    if stdev_gap > tolerance:
        return None

    frequency_label = _classify_frequency(mean_gap)
    if frequency_label is None:
        return None

    typical_amount = sum((t.amount for t in ordered), Decimal("0")) / len(ordered)
    last_date = ordered[-1].date

    return RecurringGroup(
        normalized_merchant=merchant,
        typical_amount=typical_amount,
        frequency_label=frequency_label,
        occurrences=len(ordered),
        last_date=last_date,
        next_expected_date=last_date + timedelta(days=round(mean_gap)),
        transaction_ids=[t.id for t in ordered],
    )


async def detect_recurring_transactions(
    db: AsyncSession, user_id: uuid.UUID, account_id: uuid.UUID | None = None
) -> list[RecurringGroup]:
    """Simple, explainable periodicity heuristic on normalized merchant +
    amount pattern — not a real ML model: cluster same-merchant
    transactions by similar amount, then flag clusters whose gaps between
    occurrences are regular enough to call periodic.
    """
    filters = [Transaction.user_id == user_id, Transaction.normalized_merchant.is_not(None)]
    if account_id is not None:
        filters.append(Transaction.account_id == account_id)

    transactions = list((await db.scalars(select(Transaction).where(*filters))).all())

    by_merchant: dict[str, list[Transaction]] = {}
    for txn in transactions:
        by_merchant.setdefault(txn.normalized_merchant, []).append(txn)

    groups: list[RecurringGroup] = []
    for merchant, txns in by_merchant.items():
        for cluster in _cluster_by_amount(txns):
            group = _analyze_cluster(merchant, cluster)
            if group is not None:
                groups.append(group)

    groups.sort(key=lambda g: g.next_expected_date)
    return groups
