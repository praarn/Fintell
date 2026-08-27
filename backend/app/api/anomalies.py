import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.anomaly_flag import AnomalyFlag
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.anomaly import (
    AnomalyDetectRunOut,
    AnomalyDismissRequest,
    AnomalyFlagOut,
    AnomalyStatsOut,
    AnomalyTransactionOut,
)
from app.services.anomaly import service as anomaly_service

router = APIRouter(prefix="/anomalies", tags=["anomalies"])


def _serialize(flag: AnomalyFlag, txn: Transaction) -> AnomalyFlagOut:
    return AnomalyFlagOut(
        id=flag.id,
        transaction_id=flag.transaction_id,
        severity=flag.severity,
        score=flag.score,
        driving_features=flag.driving_features_json or [],
        dismissed=flag.dismissed,
        dismissal_reason=flag.dismissal_reason,
        created_at=flag.created_at,
        transaction=AnomalyTransactionOut(
            id=txn.id,
            account_id=txn.account_id,
            raw_merchant=txn.raw_merchant,
            normalized_merchant=txn.normalized_merchant,
            category=txn.category,
            amount=txn.amount,
            date=txn.date,
        ),
    )


@router.get("", response_model=list[AnomalyFlagOut])
async def list_anomalies(
    include_dismissed: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AnomalyFlagOut]:
    """The anomaly feed — most-anomalous first. Dismissed items are hidden
    unless `include_dismissed=true`."""
    rows = await anomaly_service.list_anomaly_flags(db, current_user.id, include_dismissed)
    return [_serialize(flag, txn) for flag, txn in rows]


@router.post("/detect", response_model=AnomalyDetectRunOut)
async def run_detection(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> AnomalyDetectRunOut:
    """Refit this user's model on their full history and refresh flags."""
    return AnomalyDetectRunOut(**await anomaly_service.run_anomaly_detection(db, current_user.id))


@router.get("/stats", response_model=AnomalyStatsOut)
async def get_anomaly_stats(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> AnomalyStatsOut:
    return AnomalyStatsOut(**await anomaly_service.compute_anomaly_stats(db, current_user.id))


@router.post("/{flag_id}/dismiss", response_model=AnomalyFlagOut)
async def dismiss_anomaly(
    flag_id: uuid.UUID,
    payload: AnomalyDismissRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AnomalyFlagOut:
    try:
        flag, txn = await anomaly_service.dismiss_anomaly_flag(
            db, current_user.id, flag_id, payload.reason if payload else None
        )
    except anomaly_service.AnomalyFlagNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Anomaly flag not found") from exc
    return _serialize(flag, txn)
