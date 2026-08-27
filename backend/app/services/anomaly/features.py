"""Feature engineering for per-user spending-anomaly detection.

Every feature is oriented so that **higher = more unusual**. That single
convention is what lets the explainability layer (see `detector.explain`)
treat "which features are far above this user's normal" as "which features
drove the flag", without per-feature special-casing of direction.

None of this is a learned representation — it's deliberately boring,
inspectable arithmetic over the user's own history. The IsolationForest on
top is the only ML component, and its job is just to find the joint
outliers in this hand-built space.
"""

import calendar
import math
import uuid
from dataclasses import dataclass
from decimal import Decimal

from app.models.transaction import Transaction

# The six feature columns, in matrix order. Kept as a module constant so the
# detector and its tests refer to features by name, not position.
FEATURE_NAMES: list[str] = [
    "amount_ratio_in_category",
    "amount_magnitude_log",
    "category_rarity",
    "merchant_novelty",
    "day_of_week_rarity",
    "time_of_month_rarity",
]

# Binary features can't have a meaningful robust z-score (MAD is usually 0),
# so the explainer treats them specially: a driver iff value == 1 and the
# feature is rare overall.
BINARY_FEATURES = frozenset({"merchant_novelty"})

_CATEGORY_MEDIAN_FLOOR = 1.0  # avoid divide-by-zero for a brand-new category


@dataclass
class TransactionFeatures:
    """One transaction's feature row plus the human-readable context the
    explainer needs to turn a flagged feature into a sentence."""

    transaction_id: uuid.UUID
    values: dict[str, float]

    # context for explanations
    category: str
    abs_amount: float
    category_median_amount: float
    amount_ratio: float
    category_txn_count: int
    total_txn_count: int
    merchant: str
    is_novel_merchant: bool
    day_of_week_name: str
    time_of_month_bucket: str

    def row(self) -> list[float]:
        return [self.values[name] for name in FEATURE_NAMES]


def _abs_float(amount: Decimal) -> float:
    return float(abs(amount))


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def category_key(t: Transaction) -> str:
    return t.category or "uncategorized"


def merchant_key(t: Transaction) -> str:
    return (t.normalized_merchant or t.raw_merchant or "").strip() or "unknown merchant"


def _time_of_month_bucket(day: int) -> str:
    if day <= 10:
        return "start"
    if day <= 20:
        return "middle"
    return "end"


def build_feature_rows(transactions: list[Transaction]) -> list[TransactionFeatures]:
    """Compute the feature matrix for a single user's outflow transactions.

    Only outflows (`amount < 0`) are scored — an unusually large *deposit*
    isn't the fraud/mistake signal this feature is about, and letting
    salary credits into the amount distribution would swamp everything.
    """
    outflows = [t for t in transactions if t.amount is not None and t.amount < 0]
    total = len(outflows)
    if total == 0:
        return []

    # Chronological order so "first time with this merchant" is well-defined.
    outflows.sort(key=lambda t: (t.date, t.created_at or t.date))

    category_of = category_key
    merchant_of = merchant_key

    # Per-category median absolute amount and per-category counts.
    category_amounts: dict[str, list[float]] = {}
    category_counts: dict[str, int] = {}
    dow_counts: dict[int, int] = {}
    tom_counts: dict[str, int] = {}
    for t in outflows:
        cat = category_of(t)
        category_amounts.setdefault(cat, []).append(_abs_float(t.amount))
        category_counts[cat] = category_counts.get(cat, 0) + 1
        dow_counts[t.date.weekday()] = dow_counts.get(t.date.weekday(), 0) + 1
        bucket = _time_of_month_bucket(t.date.day)
        tom_counts[bucket] = tom_counts.get(bucket, 0) + 1

    category_medians = {
        cat: max(_median(amounts), _CATEGORY_MEDIAN_FLOOR)
        for cat, amounts in category_amounts.items()
    }
    max_abs_amount = max((_abs_float(t.amount) for t in outflows), default=1.0)

    seen_merchants: set[str] = set()
    rows: list[TransactionFeatures] = []
    for t in outflows:
        cat = category_of(t)
        merchant = merchant_of(t)
        abs_amount = _abs_float(t.amount)

        category_median = category_medians[cat]
        amount_ratio = abs_amount / category_median

        # Log-compressed magnitude relative to this user's biggest outflow,
        # so the scale is 0..1-ish regardless of currency size.
        magnitude = (
            math.log1p(abs_amount) / math.log1p(max_abs_amount) if max_abs_amount > 0 else 0.0
        )

        category_rarity = 1.0 - (category_counts[cat] / total)

        is_novel = merchant not in seen_merchants
        seen_merchants.add(merchant)

        dow_rarity = 1.0 - (dow_counts[t.date.weekday()] / total)
        tom_rarity = 1.0 - (tom_counts[_time_of_month_bucket(t.date.day)] / total)

        values = {
            "amount_ratio_in_category": amount_ratio,
            "amount_magnitude_log": magnitude,
            "category_rarity": category_rarity,
            "merchant_novelty": 1.0 if is_novel else 0.0,
            "day_of_week_rarity": dow_rarity,
            "time_of_month_rarity": tom_rarity,
        }

        rows.append(
            TransactionFeatures(
                transaction_id=t.id,
                values=values,
                category=cat,
                abs_amount=abs_amount,
                category_median_amount=category_median,
                amount_ratio=amount_ratio,
                category_txn_count=category_counts[cat],
                total_txn_count=total,
                merchant=merchant,
                is_novel_merchant=is_novel,
                day_of_week_name=calendar.day_name[t.date.weekday()],
                time_of_month_bucket=_time_of_month_bucket(t.date.day),
            )
        )

    return rows


def explanation_for(feature: str, ctx: TransactionFeatures) -> str:
    """Human-readable reason string for a single driving feature."""
    if feature == "amount_ratio_in_category":
        return (
            f"Amount ${ctx.abs_amount:,.0f} is {ctx.amount_ratio:.1f}x your typical "
            f"{ctx.category} spend (${ctx.category_median_amount:,.0f})"
        )
    if feature == "amount_magnitude_log":
        return f"Amount ${ctx.abs_amount:,.0f} is among your largest transactions"
    if feature == "category_rarity":
        return (
            f"You rarely spend on {ctx.category} — only {ctx.category_txn_count} of your "
            f"{ctx.total_txn_count} transactions"
        )
    if feature == "merchant_novelty":
        return f"First time transacting with {ctx.merchant}"
    if feature == "day_of_week_rarity":
        return f"You rarely transact on a {ctx.day_of_week_name}"
    if feature == "time_of_month_rarity":
        return f"You rarely spend near the {ctx.time_of_month_bucket} of the month"
    return f"Unusual {feature.replace('_', ' ')}"
