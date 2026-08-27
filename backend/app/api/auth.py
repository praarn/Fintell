import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_family_id, get_current_user
from app.core.database import get_db
from app.core.rate_limit import auth_rate_limit
from app.models.user import User
from app.schemas.auth import (
    AuditLogOut,
    RefreshRequest,
    SessionOut,
    TokenPair,
    UserCreate,
    UserLogin,
    UserRead,
)
from app.services import audit_service, auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[auth_rate_limit],
)
async def register(payload: UserCreate, db: AsyncSession = Depends(get_db)) -> User:
    try:
        return await auth_service.register_user(db, payload.email, payload.password)
    except auth_service.EmailAlreadyRegisteredError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        ) from exc


@router.post("/login", response_model=TokenPair, dependencies=[auth_rate_limit])
async def login(
    payload: UserLogin, request: Request, db: AsyncSession = Depends(get_db)
) -> TokenPair:
    try:
        user = await auth_service.authenticate_user(db, payload.email, payload.password)
    except auth_service.InvalidCredentialsError as exc:
        await audit_service.record(
            db,
            audit_service.LOGIN_FAILED,
            target_type="email",
            target_id=payload.email,
            request=request,
            commit=True,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        ) from exc

    tokens = await auth_service.login(db, user, _user_agent(request), _client_ip(request))
    await audit_service.record(
        db, audit_service.LOGIN, user_id=user.id, request=request, commit=True
    )
    return tokens


@router.post("/refresh", response_model=TokenPair, dependencies=[auth_rate_limit])
async def refresh(
    payload: RefreshRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> TokenPair:
    try:
        return await auth_service.rotate_refresh_token(
            db, payload.refresh_token, _user_agent(request), _client_ip(request)
        )
    except auth_service.RefreshTokenReuseDetectedError as exc:
        await audit_service.record(
            db,
            audit_service.REFRESH_REUSE_DETECTED,
            target_type="session_family",
            target_id=str(exc),
            request=request,
            commit=True,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token reuse detected — all sessions for this device chain "
            "have been revoked. Please log in again.",
        ) from exc
    except auth_service.InvalidRefreshTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        ) from exc


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(payload: RefreshRequest, db: AsyncSession = Depends(get_db)) -> None:
    await auth_service.logout(db, payload.refresh_token)


@router.get("/me", response_model=UserRead)
async def get_current_user_info(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.get("/sessions", response_model=list[SessionOut])
async def list_sessions(
    current_user: User = Depends(get_current_user),
    current_family_id: uuid.UUID = Depends(get_current_family_id),
    db: AsyncSession = Depends(get_db),
) -> list[SessionOut]:
    rows = await auth_service.list_active_sessions(db, current_user.id)
    return [
        SessionOut(
            family_id=row.family_id,
            created_at=row.created_at,
            expires_at=row.expires_at,
            user_agent=row.user_agent,
            ip_at_creation=row.ip_at_creation,
            is_current=row.family_id == current_family_id,
        )
        for row in rows
    ]


@router.delete("/sessions/{family_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(
    family_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await auth_service.revoke_session(db, current_user.id, family_id)
    except auth_service.SessionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
        ) from exc

    await audit_service.record(
        db,
        audit_service.SESSION_REVOKED,
        user_id=current_user.id,
        target_type="session_family",
        target_id=family_id,
        request=request,
        commit=True,
    )


@router.get("/activity", response_model=list[AuditLogOut])
async def list_activity(
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AuditLogOut]:
    """The signed-in user's own audit trail — logins, uploads, deletes,
    downloads, session revocations."""
    limit = max(1, min(limit, 200))
    return await audit_service.list_for_user(db, current_user.id, limit)
