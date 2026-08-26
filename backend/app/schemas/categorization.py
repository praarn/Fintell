from pydantic import BaseModel

from app.services.categorization.constants import CategoryLiteral as Category


class RecategorizeRequest(BaseModel):
    category: Category


class CategorizationStatsOut(BaseModel):
    total_transactions: int
    by_categorization_method: dict[str, int]
    pct_resolved_without_llm: float


class LLMStatsOut(BaseModel):
    total_batch_calls: int
    total_merchants_categorized: int
    total_prompt_tokens: int
    total_completion_tokens: int
    total_estimated_cost_usd: float
    promoted_merchant_count: int


class PromotionJobResultOut(BaseModel):
    promoted_count: int
    promoted_merchants: list[str]
