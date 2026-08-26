import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class LLMBatchCall(Base):
    """One row per Tier 3 LLM API call (a batch of distinct merchants sent
    in a single request — never one call per transaction). Cost is tracked
    here, at the call level, rather than repeated on every
    llm_decision_log row, so summing across calls can't double-count.
    """

    __tablename__ = "llm_batch_calls"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_used: Mapped[str] = mapped_column(String(128), nullable=False)
    merchant_count: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
