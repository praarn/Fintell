import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account

ACCOUNT_TYPES = ["checking", "savings", "credit_card", "other"]


class AccountNotFoundError(Exception):
    pass


async def create_account(
    db: AsyncSession,
    user_id: uuid.UUID,
    display_name: str,
    bank_name: str | None,
    account_type: str,
) -> Account:
    account = Account(
        user_id=user_id, display_name=display_name, bank_name=bank_name, account_type=account_type
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return account


async def list_accounts(db: AsyncSession, user_id: uuid.UUID) -> list[Account]:
    result = await db.scalars(
        select(Account).where(Account.user_id == user_id).order_by(Account.created_at)
    )
    return list(result)


async def get_owned_account(db: AsyncSession, user_id: uuid.UUID, account_id: uuid.UUID) -> Account:
    account = await db.scalar(
        select(Account).where(Account.id == account_id, Account.user_id == user_id)
    )
    if account is None:
        raise AccountNotFoundError(str(account_id))
    return account


async def get_or_create_account_for_bank_hint(
    db: AsyncSession, user_id: uuid.UUID, bank_hint: str
) -> Account:
    """Backward-compatible auto-provisioning: an upload that only supplies
    a free-text bank_hint (no explicit account_id) gets a lightweight
    account keyed by that hint, so old-style uploads still land somewhere
    sensible without requiring the account-creation UI first.
    """
    existing = await db.scalar(
        select(Account).where(Account.user_id == user_id, Account.display_name == bank_hint)
    )
    if existing is not None:
        return existing
    return await create_account(
        db, user_id, display_name=bank_hint, bank_name=bank_hint, account_type="other"
    )
