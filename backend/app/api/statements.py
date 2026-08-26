import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.database import get_db
from app.models.user import User
from app.schemas.statement import ParseFailureOut, StatementOut, StatementStatsOut, TransactionOut
from app.services import account_service, statement_service, transaction_service

router = APIRouter(prefix="/statements", tags=["statements"])
settings = get_settings()


@router.post("/upload", response_model=StatementOut, status_code=status.HTTP_201_CREATED)
async def upload_statement(
    file: UploadFile = File(...),
    bank_hint: str | None = Form(None),
    account_id: uuid.UUID | None = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StatementOut:
    if not file.filename or not file.filename.lower().endswith((".csv", ".pdf")):
        raise HTTPException(status_code=400, detail="Only .csv and .pdf files are supported")

    file_bytes = await file.read()
    if len(file_bytes) > settings.max_upload_size_bytes:
        raise HTTPException(status_code=413, detail="File exceeds the maximum upload size")

    try:
        return await statement_service.upload_and_parse_statement(
            db, current_user.id, file.filename, file_bytes, bank_hint, account_id
        )
    except account_service.AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Account not found") from exc


@router.get("", response_model=list[StatementOut])
async def list_statements(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[StatementOut]:
    return await statement_service.list_statements(db, current_user.id)


@router.get("/stats", response_model=StatementStatsOut)
async def get_statement_stats(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> StatementStatsOut:
    return StatementStatsOut(**await statement_service.compute_stats(db))


@router.get("/{statement_id}", response_model=StatementOut)
async def get_statement(
    statement_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StatementOut:
    try:
        return await statement_service.get_owned_statement(db, current_user.id, statement_id)
    except statement_service.StatementNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Statement not found") from exc


@router.get("/{statement_id}/transactions", response_model=list[TransactionOut])
async def get_statement_transactions(
    statement_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TransactionOut]:
    try:
        transactions = await statement_service.list_transactions(db, current_user.id, statement_id)
    except statement_service.StatementNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Statement not found") from exc

    split_ids = await transaction_service.get_split_transaction_ids(
        db, [t.id for t in transactions]
    )
    items = []
    for t in transactions:
        item = TransactionOut.model_validate(t)
        item.is_split = t.id in split_ids
        items.append(item)
    return items


@router.get("/{statement_id}/parse-failures", response_model=list[ParseFailureOut])
async def get_statement_parse_failures(
    statement_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ParseFailureOut]:
    try:
        return await statement_service.list_parse_failures(db, current_user.id, statement_id)
    except statement_service.StatementNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Statement not found") from exc
