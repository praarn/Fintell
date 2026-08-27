import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AnomalyFlag(Base):
    """One row per transaction the per-user IsolationForest flagged as
    unusual.

    `driving_features_json` is the whole point: a ranked list of
    ``{feature, explanation, z_score, value}`` objects saying *why* the
    transaction was flagged ("amount is 4.2x your typical dining spend",
    "first time transacting with this merchant"). A bare "anomalous"
    boolean isn't a useful product; the explanation is.

    `score` is the raw IsolationForest ``decision_function`` output — more
    negative means more isolated/anomalous. `severity` buckets that score
    into low/medium/high for the UI (a heuristic, not a calibrated
    probability).

    A dismissed flag is never re-created on the next refit: the dismissal
    is the user telling the model "this is normal for me", and the
    detector feeds that back in (see app/services/anomaly/service.py).
    """

    __tablename__ = "anomaly_flags"
    __table_args__ = (
        UniqueConstraint("transaction_id", name="uq_anomaly_flags_transaction_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    severity: Mapped[str] = mapped_column(String(16), nullable=False)  # low / medium / high
    score: Mapped[float] = mapped_column(Float, nullable=False)
    driving_features_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    dismissed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    dismissal_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
