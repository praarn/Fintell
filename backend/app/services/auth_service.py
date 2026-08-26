import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import TokenPair

settings = get_settings()


class AuthError(Exception):
    """Base class for auth/session errors the API layer maps to HTTP responses."""


class EmailAlreadyRegisteredError(AuthError):
    pass


class InvalidCredentialsError(AuthError):
    pass


class InvalidRefreshTokenError(AuthError):
    pass


class RefreshTokenReuseDetectedError(AuthError):
    """Raised when an already-rotated-out refresh token is presented again.

    The entire session family has already been revoked by the time this is
    raised — the caller should treat this as a signal to force re-login.
    """


class SessionNotFoundError(AuthError):
    pass


async def register_user(db: AsyncSession, email: str, password: str) -> User:
    existing = await db.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise EmailAlreadyRegisteredError(email)

    user = User(email=email, hashed_password=hash_password(password))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User:
    user = await db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(password, user.hashed_password):
        raise InvalidCredentialsError(email)
    return user


def _refresh_expiry() -> datetime:
    return datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)


async def _issue_token_pair(
    db: AsyncSession,
    user_id: uuid.UUID,
    family_id: uuid.UUID,
    user_agent: str | None,
    ip_address: str | None,
) -> TokenPair:
    raw_refresh_token, token_hash = generate_refresh_token()
    db.add(
        RefreshToken(
            user_id=user_id,
            token_hash=token_hash,
            family_id=family_id,
            expires_at=_refresh_expiry(),
            user_agent=user_agent,
            ip_at_creation=ip_address,
        )
    )
    await db.commit()

    access_token = create_access_token(user_id, family_id)
    return TokenPair(access_token=access_token, refresh_token=raw_refresh_token)


async def login(
    db: AsyncSession, user: User, user_agent: str | None, ip_address: str | None
) -> TokenPair:
    family_id = uuid.uuid4()
    return await _issue_token_pair(db, user.id, family_id, user_agent, ip_address)


async def _revoke_family(db: AsyncSession, family_id: uuid.UUID) -> None:
    await db.execute(
        update(RefreshToken).where(RefreshToken.family_id == family_id).values(revoked=True)
    )
    await db.commit()


async def rotate_refresh_token(
    db: AsyncSession,
    raw_refresh_token: str,
    user_agent: str | None,
    ip_address: str | None,
) -> TokenPair:
    token_hash = hash_refresh_token(raw_refresh_token)
    row = await db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))

    if row is None:
        raise InvalidRefreshTokenError("unknown refresh token")

    if row.revoked:
        # Someone presented a token that was already rotated out — either a
        # replay or the token was stolen. Kill the whole session family.
        await _revoke_family(db, row.family_id)
        raise RefreshTokenReuseDetectedError(str(row.family_id))

    if row.expires_at < datetime.now(UTC):
        raise InvalidRefreshTokenError("expired refresh token")

    row.revoked = True
    await db.commit()

    return await _issue_token_pair(db, row.user_id, row.family_id, user_agent, ip_address)


async def logout(db: AsyncSession, raw_refresh_token: str) -> None:
    token_hash = hash_refresh_token(raw_refresh_token)
    row = await db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    if row is not None:
        await _revoke_family(db, row.family_id)


async def list_active_sessions(db: AsyncSession, user_id: uuid.UUID) -> list[RefreshToken]:
    result = await db.scalars(
        select(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False))
        .order_by(RefreshToken.created_at.desc())
    )
    return list(result)


async def revoke_session(db: AsyncSession, user_id: uuid.UUID, family_id: uuid.UUID) -> None:
    owned = await db.scalar(
        select(RefreshToken).where(
            RefreshToken.family_id == family_id, RefreshToken.user_id == user_id
        )
    )
    if owned is None:
        raise SessionNotFoundError(str(family_id))
    await _revoke_family(db, family_id)
