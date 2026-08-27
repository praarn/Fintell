import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class StatementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    account_id: uuid.UUID | None
    original_filename: str
    file_type: str
    detected_structure: str | None
    parse_status: str
    parse_method: str | None
    bank_profile_id: uuid.UUID | None
    bank_profile_match_score: float | None
    row_count_total: int
    row_count_parsed: int
    row_count_failed: int
    error_message: str | None
    uploaded_at: datetime


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    account_id: uuid.UUID | None
    raw_merchant: str
    normalized_merchant: str | None
    category: str | None
    categorization_method: str | None
    confidence: Decimal | None
    amount: Decimal
    date: date
    running_balance: Decimal | None
    row_index: int | None
    is_split: bool = False


class ParseFailureOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    row_index: int | None
    reason_code: str
    reason: str
    raw_line_text: str
    created_at: datetime


class DownloadUrlOut(BaseModel):
    url: str
    expires_in_seconds: int


class StatementStatsOut(BaseModel):
    distinct_bank_profiles: int
    total_statements_processed: int
    pct_profile_reuse: float
    by_parse_method: dict[str, int]
    by_detected_structure: dict[str, int]
    by_parse_status: dict[str, int]
