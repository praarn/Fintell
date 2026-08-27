"""The fixed, reviewed query-template set behind "ask your finances".

Why templates instead of letting the LLM write SQL:

* **Security boundary.** The LLM never emits SQL, so there's no injection
  surface and no way for a bad completion to read another user's rows.
* **Auditability.** Every query the system can possibly run is in this
  file and can be reviewed. `query_template_log` records which one ran.
* **Correctness.** Structured financial questions want exact aggregates,
  not embedding similarity. This is a text-to-*query* problem, not RAG.

Every `run()` here takes `user_id` as a direct argument and every
statement is scoped `Transaction.user_id == user_id` in the query builder
itself — never from anything the LLM produced. That scoping is defence in
depth: the parameter models below also drop unknown fields, so even an
adversarial completion that stuffs a `user_id` into its params can't
change whose data is read.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import Transaction
from app.services.categorization.constants import CategoryLiteral

# --------------------------------------------------------------------------
# Result shape
# --------------------------------------------------------------------------


@dataclass
class TemplateResult:
    summary: str
    columns: list[str]
    rows: list[list]
    chart: dict | None = None


# --------------------------------------------------------------------------
# Parameter models — Pydantic-validated before any query runs.
# `extra="ignore"` is deliberate: it strips anything the LLM added that
# isn't a real parameter (e.g. a smuggled user_id).
# --------------------------------------------------------------------------


class PeriodParams(BaseModel):
    model_config = ConfigDict(extra="ignore")

    start_date: date
    end_date: date
    category: CategoryLiteral | None = None

    @model_validator(mode="after")
    def _ordered(self) -> PeriodParams:
        if self.end_date < self.start_date:
            raise ValueError("end_date is before start_date")
        return self


class TopNPeriodParams(PeriodParams):
    limit: int = Field(default=5, ge=1, le=50)


class TrendParams(BaseModel):
    model_config = ConfigDict(extra="ignore")

    months: int = Field(default=6, ge=1, le=24)
    category: CategoryLiteral | None = None


class ComparePeriodsParams(BaseModel):
    model_config = ConfigDict(extra="ignore")

    period_a_start: date
    period_a_end: date
    period_b_start: date
    period_b_end: date
    category: CategoryLiteral | None = None

    @model_validator(mode="after")
    def _ordered(self) -> ComparePeriodsParams:
        if self.period_a_end < self.period_a_start:
            raise ValueError("period_a_end is before period_a_start")
        if self.period_b_end < self.period_b_start:
            raise ValueError("period_b_end is before period_b_start")
        return self


# --------------------------------------------------------------------------
# Shared query helpers — outflow spend only, reported as positive magnitudes.
# --------------------------------------------------------------------------


def _spend_filters(user_id: uuid.UUID, start: date, end: date, category: str | None) -> list:
    filters = [
        Transaction.user_id == user_id,  # <-- the scoping the LLM can't touch
        Transaction.amount < 0,
        Transaction.date >= start,
        Transaction.date <= end,
    ]
    if category is not None:
        filters.append(Transaction.category == category)
    return filters


async def _total_spend(
    db: AsyncSession, user_id: uuid.UUID, start: date, end: date, category: str | None
) -> Decimal:
    total = await db.scalar(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            *_spend_filters(user_id, start, end, category)
        )
    )
    return abs(Decimal(total or 0))


def _money(value: Decimal) -> str:
    return f"${value:,.2f}"


def _for_category(category: str | None) -> str:
    return f" on {category}" if category else ""


# --------------------------------------------------------------------------
# Templates
# --------------------------------------------------------------------------


@dataclass
class QueryTemplate:
    name: str
    description: str
    params_model: type[BaseModel]
    run: object  # async callable (db, user_id, params) -> TemplateResult


async def _run_total_spend(
    db: AsyncSession, user_id: uuid.UUID, p: PeriodParams
) -> TemplateResult:
    total = await _total_spend(db, user_id, p.start_date, p.end_date, p.category)
    return TemplateResult(
        summary=(
            f"You spent {_money(total)}{_for_category(p.category)} between "
            f"{p.start_date} and {p.end_date}."
        ),
        columns=["total_spend"],
        rows=[[float(total)]],
    )


async def _run_spend_by_category(
    db: AsyncSession, user_id: uuid.UUID, p: PeriodParams
) -> TemplateResult:
    result = (
        await db.execute(
            select(Transaction.category, func.sum(Transaction.amount))
            .where(*_spend_filters(user_id, p.start_date, p.end_date, p.category))
            .group_by(Transaction.category)
        )
    ).all()
    pairs = sorted(
        ((cat or "uncategorized", abs(Decimal(total or 0))) for cat, total in result),
        key=lambda x: x[1],
        reverse=True,
    )
    if not pairs:
        return TemplateResult(
            summary=f"No spending found between {p.start_date} and {p.end_date}.",
            columns=["category", "total_spend"],
            rows=[],
        )
    top = ", ".join(f"{cat} ({_money(amt)})" for cat, amt in pairs[:3])
    return TemplateResult(
        summary=(
            f"Between {p.start_date} and {p.end_date} your biggest categories were {top}."
        ),
        columns=["category", "total_spend"],
        rows=[[cat, float(amt)] for cat, amt in pairs],
        chart={
            "kind": "bar",
            "labels": [cat for cat, _ in pairs],
            "values": [float(amt) for _, amt in pairs],
        },
    )


async def _run_top_merchants(
    db: AsyncSession, user_id: uuid.UUID, p: TopNPeriodParams
) -> TemplateResult:
    result = (
        await db.execute(
            select(
                Transaction.normalized_merchant,
                func.sum(Transaction.amount),
                func.count(),
            )
            .where(
                *_spend_filters(user_id, p.start_date, p.end_date, p.category),
                Transaction.normalized_merchant.is_not(None),
            )
            .group_by(Transaction.normalized_merchant)
            .order_by(func.sum(Transaction.amount))
            .limit(p.limit)
        )
    ).all()
    rows = [[m, float(abs(Decimal(total or 0))), int(count)] for m, total, count in result]
    if not rows:
        return TemplateResult(
            summary=f"No merchant spending found between {p.start_date} and {p.end_date}.",
            columns=["merchant", "total_spend", "transaction_count"],
            rows=[],
        )
    lead = ", ".join(f"{m} ({_money(Decimal(str(amt)))})" for m, amt, _ in rows[:3])
    return TemplateResult(
        summary=(
            f"Your top merchants{_for_category(p.category)} between {p.start_date} and "
            f"{p.end_date} were {lead}."
        ),
        columns=["merchant", "total_spend", "transaction_count"],
        rows=rows,
        chart={"kind": "bar", "labels": [r[0] for r in rows], "values": [r[1] for r in rows]},
    )


async def _run_compare_periods(
    db: AsyncSession, user_id: uuid.UUID, p: ComparePeriodsParams
) -> TemplateResult:
    a = await _total_spend(db, user_id, p.period_a_start, p.period_a_end, p.category)
    b = await _total_spend(db, user_id, p.period_b_start, p.period_b_end, p.category)
    delta = b - a
    pct = (delta / a * 100) if a else None
    direction = "more" if delta > 0 else "less" if delta < 0 else "the same"
    pct_text = f" ({pct:+.1f}%)" if pct is not None else ""
    return TemplateResult(
        summary=(
            f"You spent {_money(b)}{_for_category(p.category)} in the second period vs "
            f"{_money(a)} in the first — {_money(abs(delta))} {direction}{pct_text}."
        ),
        columns=["period", "total_spend"],
        rows=[
            [f"{p.period_a_start} to {p.period_a_end}", float(a)],
            [f"{p.period_b_start} to {p.period_b_end}", float(b)],
            ["change", float(delta)],
        ],
    )


async def _run_monthly_trend(
    db: AsyncSession, user_id: uuid.UUID, p: TrendParams
) -> TemplateResult:
    today = date.today()
    start = today.replace(day=1) - relativedelta(months=p.months - 1)
    month_expr = func.date_trunc("month", Transaction.date)
    result = (
        await db.execute(
            select(month_expr, func.sum(Transaction.amount))
            .where(*_spend_filters(user_id, start, today, p.category))
            .group_by(month_expr)
        )
    ).all()

    totals: dict[str, Decimal] = {}
    for month_start, total in result:
        key = f"{month_start.year:04d}-{month_start.month:02d}"
        totals[key] = abs(Decimal(total or 0))

    rows: list[list] = []
    cursor = start
    for _ in range(p.months):
        key = f"{cursor.year:04d}-{cursor.month:02d}"
        rows.append([key, float(totals.get(key, Decimal(0)))])
        cursor = cursor + relativedelta(months=1)

    return TemplateResult(
        summary=(
            f"Monthly spending{_for_category(p.category)} for the last {p.months} months, "
            f"ending {rows[-1][0]}."
        ),
        columns=["month", "total_spend"],
        rows=rows,
        chart={"kind": "line", "labels": [r[0] for r in rows], "values": [r[1] for r in rows]},
    )


async def _run_largest_transactions(
    db: AsyncSession, user_id: uuid.UUID, p: TopNPeriodParams
) -> TemplateResult:
    result = list(
        (
            await db.scalars(
                select(Transaction)
                .where(*_spend_filters(user_id, p.start_date, p.end_date, p.category))
                .order_by(Transaction.amount)
                .limit(p.limit)
            )
        ).all()
    )
    rows = [
        [
            str(t.date),
            t.normalized_merchant or t.raw_merchant,
            float(abs(Decimal(t.amount))),
            t.category or "uncategorized",
        ]
        for t in result
    ]
    if not rows:
        return TemplateResult(
            summary=f"No transactions found between {p.start_date} and {p.end_date}.",
            columns=["date", "merchant", "amount", "category"],
            rows=[],
        )
    biggest = rows[0]
    return TemplateResult(
        summary=(
            f"Your largest transaction{_for_category(p.category)} between {p.start_date} and "
            f"{p.end_date} was {_money(Decimal(str(biggest[2])))} at {biggest[1]} on {biggest[0]}."
        ),
        columns=["date", "merchant", "amount", "category"],
        rows=rows,
    )


TEMPLATES: list[QueryTemplate] = [
    QueryTemplate(
        name="total_spend_in_period",
        description=(
            "Total amount spent between two dates, optionally filtered to one category. "
            "Use for 'how much did I spend last month', 'what did I spend on groceries in Q1'."
        ),
        params_model=PeriodParams,
        run=_run_total_spend,
    ),
    QueryTemplate(
        name="spend_by_category_in_period",
        description=(
            "Spending broken down per category between two dates. Use for 'where did my "
            "money go last month', 'break down my spending for March'."
        ),
        params_model=PeriodParams,
        run=_run_spend_by_category,
    ),
    QueryTemplate(
        name="top_merchants_in_period",
        description=(
            "The merchants you spent the most at between two dates (limit N, default 5), "
            "optionally within one category. Use for 'who did I pay the most', 'top stores "
            "this year'."
        ),
        params_model=TopNPeriodParams,
        run=_run_top_merchants,
    ),
    QueryTemplate(
        name="compare_spend_between_periods",
        description=(
            "Compare total spending between two date ranges (period A then period B), "
            "optionally within one category. Use for 'did I spend more this month than "
            "last', 'compare my dining spend between Q1 and Q2'."
        ),
        params_model=ComparePeriodsParams,
        run=_run_compare_periods,
    ),
    QueryTemplate(
        name="monthly_spend_trend",
        description=(
            "Total spend per month for the trailing N months (default 6), optionally within "
            "one category. Use for 'show my spending trend', 'how has my grocery spend "
            "changed'."
        ),
        params_model=TrendParams,
        run=_run_monthly_trend,
    ),
    QueryTemplate(
        name="largest_transactions",
        description=(
            "The single biggest transactions between two dates (limit N, default 5), "
            "optionally within one category. Use for 'what were my biggest purchases', "
            "'largest charge in December'."
        ),
        params_model=TopNPeriodParams,
        run=_run_largest_transactions,
    ),
]

REGISTRY: dict[str, QueryTemplate] = {t.name: t for t in TEMPLATES}
