import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.categorization import CategorizationStatsOut, RecategorizeRequest
from app.schemas.statement import TransactionOut
from app.schemas.views import (
    RecurringGroupOut,
    SpendingByCategoryOut,
    SpendingTrendPointOut,
    SplitRequest,
    TopMerchantOut,
    TransactionListOut,
    TransactionSplitOut,
)
from app.services import recurring_service, transaction_service
from app.services.categorization import service as categorization_service

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.get("", response_model=TransactionListOut)
async def list_transactions(
    account_id: uuid.UUID | None = None,
    category: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    search: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TransactionListOut:
    """The unified, cross-statement/cross-account transaction table."""
    result = await transaction_service.list_all_transactions(
        db,
        current_user.id,
        account_id=account_id,
        category=category,
        start_date=start_date,
        end_date=end_date,
        search=search,
        page=page,
        page_size=page_size,
    )
    items = []
    for t in result.items:
        item = TransactionOut.model_validate(t)
        item.is_split = t.id in result.split_transaction_ids
        items.append(item)
    return TransactionListOut(items=items, total=result.total, page=page, page_size=page_size)


@router.get("/stats", response_model=CategorizationStatsOut)
async def get_categorization_stats(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> CategorizationStatsOut:
    return CategorizationStatsOut(**await categorization_service.compute_categorization_stats(db))


@router.get("/recurring", response_model=list[RecurringGroupOut])
async def get_recurring_transactions(
    account_id: uuid.UUID | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[RecurringGroupOut]:
    groups = await recurring_service.detect_recurring_transactions(db, current_user.id, account_id)
    return [RecurringGroupOut(**vars(g)) for g in groups]


@router.get("/spending/by-category", response_model=SpendingByCategoryOut)
async def get_spending_by_category(
    account_id: uuid.UUID | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SpendingByCategoryOut:
    by_category = await transaction_service.get_spending_by_category(
        db, current_user.id, start_date, end_date, account_id
    )
    return SpendingByCategoryOut(by_category=by_category, total_spend=sum(by_category.values()))


@router.get("/spending/trend", response_model=list[SpendingTrendPointOut])
async def get_spending_trend(
    months: int = Query(6, ge=1, le=24),
    account_id: uuid.UUID | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SpendingTrendPointOut]:
    trend = await transaction_service.get_spending_trend(db, current_user.id, months, account_id)
    return [SpendingTrendPointOut(**point) for point in trend]


@router.get("/spending/top-merchants", response_model=list[TopMerchantOut])
async def get_top_merchants(
    account_id: uuid.UUID | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TopMerchantOut]:
    merchants = await transaction_service.get_top_merchants(
        db, current_user.id, start_date, end_date, account_id, limit
    )
    return [TopMerchantOut(**m) for m in merchants]


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


@router.get("/{transaction_id}/splits", response_model=list[TransactionSplitOut])
async def get_transaction_splits(
    transaction_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TransactionSplitOut]:
    try:
        await transaction_service.get_owned_transaction(db, current_user.id, transaction_id)
    except transaction_service.TransactionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Transaction not found") from exc
    return await transaction_service.get_transaction_splits(db, transaction_id)


@router.post("/{transaction_id}/split", response_model=TransactionOut)
async def split_transaction(
    transaction_id: uuid.UUID,
    payload: SplitRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TransactionOut:
    try:
        transaction = await transaction_service.split_transaction(
            db,
            current_user.id,
            transaction_id,
            [(s.category, s.amount) for s in payload.splits],
        )
        # is_split isn't a real column — it's computed at read time by the
        # list endpoints. Set it explicitly here too, or this response
        # looks like the split never happened.
        result = TransactionOut.model_validate(transaction)
        result.is_split = True
        return result
    except transaction_service.TransactionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Transaction not found") from exc
    except transaction_service.InvalidSplitError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/{transaction_id}/split", response_model=TransactionOut)
async def unsplit_transaction(
    transaction_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TransactionOut:
    try:
        transaction = await transaction_service.unsplit_transaction(
            db, current_user.id, transaction_id
        )
        result = TransactionOut.model_validate(transaction)
        result.is_split = False
        return result
    except transaction_service.TransactionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Transaction not found") from exc
