"""Orchestrates a single "ask your finances" question:

    question -> LLM picks template + params -> Pydantic validates params
             -> user-scoped query builder runs it -> numbers + summary

Declines honestly (and logs the decline) whenever the LLM has no
confident template, or the params don't validate. Every outcome is
written to `query_template_log`.
"""

import uuid
from dataclasses import dataclass, field

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.query_template_log import QueryTemplateLog
from app.services.text_to_sql import llm_selector
from app.services.text_to_sql.templates import REGISTRY

settings = get_settings()

_DECLINE_NO_MATCH = (
    "I can only answer questions I can map to a supported query — spending totals, "
    "category breakdowns, top merchants, period comparisons, monthly trends, or largest "
    "transactions, each over a date range. Try rephrasing along those lines."
)
_DECLINE_NOT_CONFIGURED = "The finance assistant isn't configured (no LLM API key)."
_DECLINE_UNAVAILABLE = "The finance assistant is temporarily unavailable. Please try again."


@dataclass
class AnswerResult:
    answered: bool
    question: str
    matched_template: str | None
    confidence: float | None
    summary: str
    columns: list[str] = field(default_factory=list)
    rows: list[list] = field(default_factory=list)
    chart: dict | None = None


def _first_error(exc: ValidationError) -> str:
    err = exc.errors()[0]
    loc = ".".join(str(p) for p in err.get("loc", ())) or "parameters"
    return f"{loc}: {err.get('msg', 'invalid')}"


async def _log(
    db: AsyncSession,
    user_id: uuid.UUID,
    question: str,
    *,
    template: str | None,
    confidence: float | None,
    declined: bool,
    params: dict,
    summary: str,
) -> None:
    db.add(
        QueryTemplateLog(
            user_id=user_id,
            question_text=question,
            matched_template=template,
            confidence=confidence,
            params_json=params,
            declined=declined,
            result_summary=summary,
        )
    )
    await db.commit()


async def _decline(
    db: AsyncSession,
    user_id: uuid.UUID,
    question: str,
    summary: str,
    *,
    confidence: float | None = None,
) -> AnswerResult:
    # matched_template stays NULL on a decline — the data-model contract is
    # "NULL template == not answered".
    await _log(
        db,
        user_id,
        question,
        template=None,
        confidence=confidence,
        declined=True,
        params={},
        summary=summary,
    )
    return AnswerResult(
        answered=False,
        question=question,
        matched_template=None,
        confidence=confidence,
        summary=summary,
    )


async def answer_question(
    db: AsyncSession, user_id: uuid.UUID, question: str
) -> AnswerResult:
    if not settings.llm_api_key:
        return await _decline(db, user_id, question, _DECLINE_NOT_CONFIGURED)

    try:
        selection = await llm_selector.select_template(question)
    except Exception:
        return await _decline(db, user_id, question, _DECLINE_UNAVAILABLE)

    if selection is None or selection.template_name == "none":
        conf = selection.confidence if selection else None
        return await _decline(db, user_id, question, _DECLINE_NO_MATCH, confidence=conf)

    if selection.confidence < settings.text_to_sql_min_confidence:
        return await _decline(
            db, user_id, question, _DECLINE_NO_MATCH, confidence=selection.confidence
        )

    template = REGISTRY.get(selection.template_name)
    if template is None:  # unreachable given the structured-output enum, but be safe
        return await _decline(
            db, user_id, question, _DECLINE_NO_MATCH, confidence=selection.confidence
        )

    raw_params = selection.params.model_dump(exclude_none=True)
    try:
        typed_params = template.params_model.model_validate(raw_params)
    except ValidationError as exc:
        return await _decline(
            db,
            user_id,
            question,
            f"I matched that to '{template.name}' but couldn't fill it in — {_first_error(exc)}.",
            confidence=selection.confidence,
        )

    # The query builder scopes by this user_id itself; nothing from the LLM
    # (raw_params included) can widen it.
    result = await template.run(db, user_id, typed_params)

    await _log(
        db,
        user_id,
        question,
        template=template.name,
        confidence=selection.confidence,
        declined=False,
        params=typed_params.model_dump(mode="json"),
        summary=result.summary,
    )

    return AnswerResult(
        answered=True,
        question=question,
        matched_template=template.name,
        confidence=selection.confidence,
        summary=result.summary,
        columns=result.columns,
        rows=result.rows,
        chart=result.chart,
    )


async def list_history(
    db: AsyncSession, user_id: uuid.UUID, limit: int = 20
) -> list[QueryTemplateLog]:
    return list(
        (
            await db.scalars(
                select(QueryTemplateLog)
                .where(QueryTemplateLog.user_id == user_id)
                .order_by(QueryTemplateLog.created_at.desc())
                .limit(limit)
            )
        ).all()
    )
