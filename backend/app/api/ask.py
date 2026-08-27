from dataclasses import asdict

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.ask import AskRequest, AskResponse, QueryHistoryItem
from app.services.text_to_sql import service as ask_service

router = APIRouter(prefix="/ask", tags=["ask"])


@router.post("", response_model=AskResponse)
async def ask(
    payload: AskRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AskResponse:
    """Natural-language question → reviewed query template + typed params →
    user-scoped query → numbers plus a plain-language summary. Declines
    honestly when no template fits."""
    result = await ask_service.answer_question(db, current_user.id, payload.question)
    return AskResponse(**asdict(result))


@router.get("/history", response_model=list[QueryHistoryItem])
async def history(
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[QueryHistoryItem]:
    return await ask_service.list_history(db, current_user.id, limit)
