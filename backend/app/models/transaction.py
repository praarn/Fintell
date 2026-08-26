import uuid
from datetime import date as date_type
from datetime import datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Transaction(Base):
    """A single parsed transaction.

    Tier 1 (this phase) populates raw_merchant/amount/date only. The
    categorization fields are nullable and untouched until Tier 2/3
    (later phases) fill them in — `categorization_method` is the
    auditability story for how each transaction ended up categorized.

    `amount` uses one canonical sign convention regardless of the source
    statement's layout: positive = inflow/credit, negative = outflow/debit.
    """

    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    statement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("statements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Denormalized from statements.account_id (same rationale as user_id
    # above) so account-scoped queries don't need a join.
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    raw_merchant: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_merchant: Mapped[str | None] = mapped_column(String(255), nullable=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    categorization_method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)

    amount: Mapped[Numeric] = mapped_column(Numeric(14, 2), nullable=False)
    date: Mapped[date_type] = mapped_column(Date, nullable=False)
    running_balance: Mapped[Numeric | None] = mapped_column(Numeric(14, 2), nullable=True)

    raw_line_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    row_index: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
