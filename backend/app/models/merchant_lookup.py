import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MerchantLookup(Base):
    """raw_pattern -> normalized_name/category, matched exactly or via
    rapidfuzz against a cleaned merchant string (see
    app/services/categorization/merchant_cleaner.py). `match_type` records
    how this row itself came to exist (`seed` / `user_correction` /
    `llm_promotion`), not how any particular transaction matched it.
    """

    __tablename__ = "merchant_lookup"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    raw_pattern: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    match_type: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    promoted_from_llm: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
