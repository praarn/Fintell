import uuid

import jwt
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.database import get_db
from app.core.rate_limit import upload_rate_limit
from app.core.security import create_download_token, decode_download_token
from app.models.statement import Statement
from app.models.user import User
from app.schemas.statement import (
    DownloadUrlOut,
    ParseFailureOut,
    StatementOut,
    StatementStatsOut,
    TransactionOut,
)
from app.services import account_service, audit_service, statement_service, transaction_service

router = APIRouter(prefix="/statements", tags=["statements"])
settings = get_settings()


@router.post(
    "/upload",
    response_model=StatementOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[upload_rate_limit],
)
async def upload_statement(
    request: Request,
    file: UploadFile = File(...),
    bank_hint: str | None = Form(None),
    account_id: uuid.UUID | None = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StatementOut:
    if not file.filename or not file.filename.strip():
        raise HTTPException(status_code=400, detail="A file with a name is required")

    # Any file type is accepted. The Tier 1 pipeline sniffs the actual
    # content (CSV/TSV/text grids, PDF tables/text/scans, and bare images
    # via OCR) and, for anything it genuinely can't read, records an
    # honest `failed_needs_manual` statement with a logged reason rather
    # than rejecting the upload outright.
    file_bytes = await file.read()
    if len(file_bytes) > settings.max_upload_size_bytes:
        raise HTTPException(status_code=413, detail="File exceeds the maximum upload size")

    try:
        statement = await statement_service.upload_and_parse_statement(
            db, current_user.id, file.filename, file_bytes, bank_hint, account_id
        )
    except account_service.AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Account not found") from exc

    await audit_service.record(
        db,
        audit_service.STATEMENT_UPLOAD,
        user_id=current_user.id,
        target_type="statement",
        target_id=statement.id,
        request=request,
        detail={"filename": statement.original_filename, "parse_status": statement.parse_status},
        commit=True,
    )
    return statement


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


@router.delete("/{statement_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_statement(
    statement_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await statement_service.delete_statement(db, current_user.id, statement_id)
    except statement_service.StatementNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Statement not found") from exc

    await audit_service.record(
        db,
        audit_service.STATEMENT_DELETE,
        user_id=current_user.id,
        target_type="statement",
        target_id=statement_id,
        request=request,
        commit=True,
    )


@router.post("/{statement_id}/download-url", response_model=DownloadUrlOut)
async def create_statement_download_url(
    statement_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DownloadUrlOut:
    """Mint a short-lived signed URL for the owner to fetch the raw file.
    Uploaded statements are never served from a static path."""
    try:
        statement = await statement_service.get_owned_statement(
            db, current_user.id, statement_id
        )
    except statement_service.StatementNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Statement not found") from exc

    token = create_download_token(statement.id, current_user.id)
    return DownloadUrlOut(
        url=f"/statements/{statement.id}/file?token={token}",
        expires_in_seconds=settings.download_url_ttl_seconds,
    )


@router.get("/{statement_id}/file")
async def download_statement_file(
    statement_id: uuid.UUID,
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """Serve the raw file, authorized solely by the signed `token` query
    param (so the URL works in a plain browser navigation). No bearer
    needed; the token carries the owner id and a short expiry."""
    try:
        payload = decode_download_token(token)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=403, detail="Invalid or expired download link") from exc

    if payload.get("sid") != str(statement_id):
        raise HTTPException(status_code=403, detail="Token does not match this statement")

    owner_id = uuid.UUID(payload["sub"])
    statement = await db.scalar(
        select(Statement).where(Statement.id == statement_id, Statement.user_id == owner_id)
    )
    if statement is None:
        raise HTTPException(status_code=404, detail="Statement not found")

    try:
        path = statement_service.resolve_stored_file(statement)
    except statement_service.StatementNotFoundError as exc:
        raise HTTPException(status_code=404, detail="File no longer available") from exc

    await audit_service.record(
        db,
        audit_service.STATEMENT_DOWNLOAD,
        user_id=owner_id,
        target_type="statement",
        target_id=statement_id,
        request=request,
        commit=True,
    )
    return FileResponse(
        path,
        filename=statement.original_filename,
        media_type="application/octet-stream",
    )


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
