from typing import Literal

from pydantic import BaseModel

from app.services.categorization.constants import CATEGORIES

Category = Literal[*CATEGORIES]  # type: ignore[valid-type]


class RecategorizeRequest(BaseModel):
    category: Category


class CategorizationStatsOut(BaseModel):
    total_transactions: int
    by_categorization_method: dict[str, int]
    pct_resolved_without_llm: float
