import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.services.account_service import ACCOUNT_TYPES

AccountType = Literal[*ACCOUNT_TYPES]  # type: ignore[valid-type]


class AccountCreate(BaseModel):
    display_name: str
    bank_name: str | None = None
    account_type: AccountType = "other"


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    display_name: str
    bank_name: str | None
    account_type: str
    created_at: datetime
