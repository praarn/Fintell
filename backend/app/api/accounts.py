from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.account import AccountCreate, AccountOut
from app.services import account_service

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.post("", response_model=AccountOut, status_code=status.HTTP_201_CREATED)
async def create_account(
    payload: AccountCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AccountOut:
    return await account_service.create_account(
        db, current_user.id, payload.display_name, payload.bank_name, payload.account_type
    )


@router.get("", response_model=list[AccountOut])
async def list_accounts(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[AccountOut]:
    return await account_service.list_accounts(db, current_user.id)
