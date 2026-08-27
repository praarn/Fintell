import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

Scalar = str | float | int | bool | None


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class AskChart(BaseModel):
    kind: str  # "bar" | "line"
    labels: list[str]
    values: list[float]


class AskResponse(BaseModel):
    answered: bool
    question: str
    matched_template: str | None
    confidence: float | None
    summary: str
    columns: list[str]
    rows: list[list[Scalar]]
    chart: AskChart | None


class QueryHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    question_text: str
    matched_template: str | None
    confidence: float | None
    declined: bool
    result_summary: str
    created_at: datetime
