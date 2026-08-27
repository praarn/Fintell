import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class AnomalyDriverOut(BaseModel):
    feature: str
    explanation: str
    z_score: float | None = None
    value: float | None = None


class AnomalyTransactionOut(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID | None
    raw_merchant: str
    normalized_merchant: str | None
    category: str | None
    amount: Decimal
    date: date


class AnomalyFlagOut(BaseModel):
    id: uuid.UUID
    transaction_id: uuid.UUID
    severity: str
    score: float
    driving_features: list[AnomalyDriverOut]
    dismissed: bool
    dismissal_reason: str | None
    created_at: datetime
    transaction: AnomalyTransactionOut


class AnomalyDismissRequest(BaseModel):
    reason: str | None = None


class AnomalyDetectRunOut(BaseModel):
    transactions_considered: int
    model_trained: bool
    active_flag_count: int
    new_flag_count: int
    cleared_flag_count: int


class AnomalyStatsOut(BaseModel):
    total_flags: int
    active_flags: int
    dismissed_flags: int
    by_severity: dict[str, int]
    dismissal_rate: float
