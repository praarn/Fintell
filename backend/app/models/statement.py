import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.bank_profile import BankProfile
    from app.models.user import User


class Statement(Base):
    __tablename__ = "statements"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    bank_hint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bank_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bank_profiles.id", ondelete="SET NULL"), nullable=True
    )

    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_type: Mapped[str] = mapped_column(String(16), nullable=False)

    # clean_csv / pdf_table / pdf_text_no_table / pdf_scan_ocr
    detected_structure: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # pending / parsed_clean / parsed_with_warnings / failed_needs_manual
    parse_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    # profile_reuse / cold_detection
    parse_method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    bank_profile_match_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    row_count_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    row_count_parsed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    row_count_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship()
    bank_profile: Mapped["BankProfile | None"] = relationship()
