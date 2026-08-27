import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class QueryTemplateLog(Base):
    """Audit trail for the "ask your finances" feature — one row per
    question asked, whether or not it was answered.

    The LLM only ever picks a `matched_template` and fills `params_json`;
    it never sees or writes SQL. `matched_template` is NULL when the
    question was declined (no confident template match, or the params
    didn't validate). This log is also where the honest "template-match
    rate" metric comes from.
    """

    __tablename__ = "query_template_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    matched_template: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    params_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    declined: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    result_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
