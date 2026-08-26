import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, field_validator

from app.schemas.statement import TransactionOut
from app.services.categorization.constants import CategoryLiteral as Category


class TransactionListOut(BaseModel):
    items: list[TransactionOut]
    total: int
    page: int
    page_size: int


class SplitAllocation(BaseModel):
    category: Category
    amount: Decimal


class SplitRequest(BaseModel):
    splits: list[SplitAllocation]

    @field_validator("splits")
    @classmethod
    def at_least_two(cls, value: list[SplitAllocation]) -> list[SplitAllocation]:
        if len(value) < 2:
            raise ValueError("a split needs at least two category allocations")
        return value


class TransactionSplitOut(BaseModel):
    category: str
    amount: Decimal


class SpendingByCategoryOut(BaseModel):
    by_category: dict[str, Decimal]
    total_spend: Decimal


class SpendingTrendPointOut(BaseModel):
    month: str
    total_spend: Decimal


class TopMerchantOut(BaseModel):
    merchant: str
    total_spend: Decimal
    transaction_count: int


class RecurringGroupOut(BaseModel):
    normalized_merchant: str
    typical_amount: Decimal
    frequency_label: str
    occurrences: int
    last_date: date
    next_expected_date: date
    transaction_ids: list[uuid.UUID]
