import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.categorization import CategorizationStatsOut, RecategorizeRequest
from app.schemas.statement import TransactionOut
from app.services.categorization import service as categorization_service

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.get("/stats", response_model=CategorizationStatsOut)
async def get_categorization_stats(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> CategorizationStatsOut:
    return CategorizationStatsOut(**await categorization_service.compute_categorization_stats(db))


@router.patch("/{transaction_id}/category", response_model=TransactionOut)
async def recategorize_transaction(
    transaction_id: uuid.UUID,
    payload: RecategorizeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TransactionOut:
    try:
        return await categorization_service.recategorize_transaction(
            db, current_user.id, transaction_id, payload.category
        )
    except categorization_service.TransactionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Transaction not found") from exc
    except categorization_service.InvalidCategoryError as exc:
        raise HTTPException(status_code=422, detail="Invalid category") from exc
