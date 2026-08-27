"""Recording and reading the security audit trail.

`record()` only stages the row; the caller decides when to commit so an
audit entry can share the same transaction as the action it describes.
Pass `commit=True` for standalone events (a failed login, a download)
that have no other write to piggyback on.
"""

import uuid

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog

# Canonical action names — keep this list and the README's audit section
# in sync.
LOGIN = "auth.login"
LOGIN_FAILED = "auth.login_failed"
REFRESH_REUSE_DETECTED = "auth.refresh_reuse_detected"
SESSION_REVOKED = "auth.session_revoked"
STATEMENT_UPLOAD = "statement.upload"
STATEMENT_DELETE = "statement.delete"
STATEMENT_DOWNLOAD = "statement.download"
TRANSACTIONS_EXPORT = "transactions.export"


async def record(
    db: AsyncSession,
    action: str,
    *,
    user_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: object | None = None,
    request: Request | None = None,
    detail: dict | None = None,
    commit: bool = False,
) -> None:
    ip_address = None
    user_agent = None
    if request is not None:
        ip_address = request.client.host if request.client else None
        ua = request.headers.get("user-agent")
        user_agent = ua[:512] if ua else None

    db.add(
        AuditLog(
            user_id=user_id,
            action=action,
            target_type=target_type,
            target_id=None if target_id is None else str(target_id),
            ip_address=ip_address,
            user_agent=user_agent,
            detail_json=detail or {},
        )
    )
    if commit:
        await db.commit()


async def list_for_user(
    db: AsyncSession, user_id: uuid.UUID, limit: int = 50
) -> list[AuditLog]:
    result = await db.scalars(
        select(AuditLog)
        .where(AuditLog.user_id == user_id)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )
    return list(result)
