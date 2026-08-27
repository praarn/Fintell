"""The one and only job the LLM has in "ask your finances": read the
user's question and pick a template + fill parameters. It never sees the
database, the schema, or SQL.

Structured output (a fixed `response_format`) means the model literally
cannot return a template name outside the known set, and its params come
back as a flat, typed object. Whatever it returns is then re-validated
against the chosen template's own Pydantic model before anything runs.
"""

from datetime import date
from typing import Literal, get_args

from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict

from app.core.config import get_settings
from app.services.text_to_sql.templates import REGISTRY

settings = get_settings()

TemplateName = Literal[
    "total_spend_in_period",
    "spend_by_category_in_period",
    "top_merchants_in_period",
    "compare_spend_between_periods",
    "monthly_spend_trend",
    "largest_transactions",
    "none",
]

# Guard against the Literal drifting from the actual template set.
assert set(get_args(TemplateName)) == set(REGISTRY) | {"none"}, (
    "TemplateName out of sync with REGISTRY"
)


class SelectionParams(BaseModel):
    """Union of every parameter any template accepts, all optional. The
    LLM fills what's relevant; `extra="ignore"` drops anything else."""

    model_config = ConfigDict(extra="ignore")

    start_date: str | None = None
    end_date: str | None = None
    category: str | None = None
    limit: int | None = None
    months: int | None = None
    period_a_start: str | None = None
    period_a_end: str | None = None
    period_b_start: str | None = None
    period_b_end: str | None = None


class TemplateSelection(BaseModel):
    template_name: TemplateName
    confidence: float
    params: SelectionParams


def _system_prompt() -> str:
    catalog = "\n".join(f"- {t.name}: {t.description}" for t in REGISTRY.values())
    return (
        "You route natural-language questions about a user's own bank transactions to a "
        "fixed set of query templates for a personal finance app. Pick the single best "
        "template and fill its parameters. Dates must be ISO (YYYY-MM-DD); resolve "
        f"relative dates against today, {date.today().isoformat()}. Categories, if used, "
        "must be one of: groceries, dining, food_delivery, transit, utilities, "
        "subscriptions, entertainment, shopping, travel, health, income, transfers, fees, "
        "other. If no template genuinely fits the question, return template_name 'none'. "
        "Report a calibrated confidence in [0, 1].\n\nTemplates:\n" + catalog
    )


async def select_template(question: str) -> TemplateSelection | None:
    client = AsyncOpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        timeout=settings.llm_request_timeout_seconds,
    )
    completion = await client.chat.completions.parse(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": question},
        ],
        response_format=TemplateSelection,
    )
    return completion.choices[0].message.parsed
