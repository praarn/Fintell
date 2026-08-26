import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BankProfile(Base):
    """A learned statement layout, keyed by a fingerprint of its header text
    (or structural signature, for non-tabular PDFs) — never by bank name.

    Global across all users on purpose: this row only ever stores
    column-layout/date-format metadata, never transaction data, so sharing
    it is what lets the system get better per-bank over time for everyone,
    not just the user who first uploaded that layout.
    """

    __tablename__ = "bank_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    structure_type: Mapped[str] = mapped_column(String(32), nullable=False)
    header_fingerprint_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    header_fingerprint_normalized: Mapped[str] = mapped_column(Text, nullable=False)
    column_map_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    date_format: Mapped[str] = mapped_column(String(64), nullable=False)
    amount_sign_convention: Mapped[str] = mapped_column(String(64), nullable=False)
    regex_pattern: Mapped[str | None] = mapped_column(Text, nullable=True)
    sample_lines_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    learned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    times_used: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    times_rejected: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
