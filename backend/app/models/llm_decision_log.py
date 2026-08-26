import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class LLMDecisionLog(Base):
    """One row per distinct merchant the LLM categorized (not per
    transaction — several transactions can share one cleaned merchant and
    therefore one decision). This log is the growing labeled dataset the
    promotion job mines: once the same cleaned_merchant has enough
    consistent decisions, it gets promoted into merchant_lookup and
    `promoted` flips true.
    """

    __tablename__ = "llm_decision_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    raw_merchant: Mapped[str] = mapped_column(Text, nullable=False)
    cleaned_merchant: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    llm_category: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    model_used: Mapped[str] = mapped_column(String(128), nullable=False)
    batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("llm_batch_calls.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    promoted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
