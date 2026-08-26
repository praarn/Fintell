from dataclasses import dataclass, field

from openai import AsyncOpenAI
from pydantic import BaseModel

from app.core.config import get_settings
from app.services.categorization.constants import CategoryLiteral

settings = get_settings()

SYSTEM_PROMPT = (
    "You categorize bank transaction merchant names into a fixed set of "
    "categories for a personal finance app. For each merchant string given, "
    "choose exactly one category from the allowed set and give your "
    "confidence in that choice from 0 to 1. Never invent a category outside "
    "the allowed set."
)


class MerchantCategorization(BaseModel):
    merchant: str
    category: CategoryLiteral
    confidence: float


class BatchCategorizationResponse(BaseModel):
    categorizations: list[MerchantCategorization]


@dataclass
class LLMCallResult:
    categorizations: list[MerchantCategorization]
    model_used: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    warnings: list[str] = field(default_factory=list)


async def categorize_merchants_batch(merchants: list[str]) -> LLMCallResult:
    """Calls the configured OpenAI-compatible LLM once for the whole batch
    (never once per transaction). Categories are constrained to the fixed
    enum via structured output — the model literally cannot return
    anything outside it. Raises on failure; callers decide how to degrade.
    """
    client = AsyncOpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        timeout=settings.llm_request_timeout_seconds,
    )
    user_prompt = "Merchant strings to categorize, one per line:\n" + "\n".join(
        f"- {m}" for m in merchants
    )

    completion = await client.chat.completions.parse(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        response_format=BatchCategorizationResponse,
    )

    parsed = completion.choices[0].message.parsed
    usage = completion.usage
    return LLMCallResult(
        categorizations=parsed.categorizations if parsed else [],
        model_used=settings.llm_model,
        prompt_tokens=usage.prompt_tokens if usage else 0,
        completion_tokens=usage.completion_tokens if usage else 0,
    )
