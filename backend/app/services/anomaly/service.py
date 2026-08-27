"""Orchestration for anomaly detection: run a per-user refit, persist the
resulting flags, serve the feed, and handle dismissals (which feed back
into the next refit)."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.anomaly_flag import AnomalyFlag
from app.models.transaction import Transaction
from app.services.anomaly import detector
from app.services.anomaly.features import category_key, merchant_key


class AnomalyFlagNotFoundError(Exception):
    pass


async def _load_user_transactions(db: AsyncSession, user_id: uuid.UUID) -> list[Transaction]:
    return list(
        (await db.scalars(select(Transaction).where(Transaction.user_id == user_id))).all()
    )


async def _load_suppressed_signatures(
    db: AsyncSession, user_id: uuid.UUID
) -> set[tuple[str, str]]:
    """`(merchant, category)` pairs the user has dismissed at least once —
    the model treats these as "known normal" on the next refit."""
    rows = (
        await db.scalars(
            select(Transaction)
            .join(AnomalyFlag, AnomalyFlag.transaction_id == Transaction.id)
            .where(AnomalyFlag.user_id == user_id, AnomalyFlag.dismissed.is_(True))
        )
    ).all()
    return {(merchant_key(t).lower(), category_key(t)) for t in rows}


async def run_anomaly_detection(db: AsyncSession, user_id: uuid.UUID) -> dict:
    """Refit this user's IsolationForest on their full history and
    reconcile the flag table with the fresh result.

    Triggerable via `POST /anomalies/detect`, and also run best-effort
    after each statement upload so a user's "normal" keeps up with their
    spending. Dismissed flags are sticky — never re-created, never
    counted as new.
    """
    transactions = await _load_user_transactions(db, user_id)
    suppressed = await _load_suppressed_signatures(db, user_id)
    results, model_trained = detector.detect(transactions, suppressed_signatures=suppressed)
    outflow_count = sum(1 for t in transactions if t.amount is not None and t.amount < 0)

    existing = list(
        (await db.scalars(select(AnomalyFlag).where(AnomalyFlag.user_id == user_id))).all()
    )
    existing_by_txn = {f.transaction_id: f for f in existing}
    dismissed_txn_ids = {f.transaction_id for f in existing if f.dismissed}

    flagged_txn_ids: set[uuid.UUID] = set()
    new_count = 0
    for result in results:
        flagged_txn_ids.add(result.transaction_id)
        if result.transaction_id in dismissed_txn_ids:
            continue

        flag = existing_by_txn.get(result.transaction_id)
        if flag is None:
            db.add(
                AnomalyFlag(
                    transaction_id=result.transaction_id,
                    user_id=user_id,
                    severity=result.severity,
                    score=result.score,
                    driving_features_json=result.drivers,
                )
            )
            new_count += 1
        else:
            flag.severity = result.severity
            flag.score = result.score
            flag.driving_features_json = result.drivers

    # Anything previously flagged (and not dismissed) that the refit no
    # longer considers anomalous is cleared — the user's normal moved.
    cleared_count = 0
    if model_trained:
        for flag in existing:
            if not flag.dismissed and flag.transaction_id not in flagged_txn_ids:
                await db.delete(flag)
                cleared_count += 1

    await db.commit()

    active_flag_count = await db.scalar(
        select(func.count())
        .select_from(AnomalyFlag)
        .where(AnomalyFlag.user_id == user_id, AnomalyFlag.dismissed.is_(False))
    )

    return {
        "transactions_considered": outflow_count,
        "model_trained": model_trained,
        "active_flag_count": active_flag_count or 0,
        "new_flag_count": new_count,
        "cleared_flag_count": cleared_count,
    }


async def list_anomaly_flags(
    db: AsyncSession, user_id: uuid.UUID, include_dismissed: bool = False
) -> list[tuple[AnomalyFlag, Transaction]]:
    stmt = (
        select(AnomalyFlag, Transaction)
        .join(Transaction, Transaction.id == AnomalyFlag.transaction_id)
        .where(AnomalyFlag.user_id == user_id)
        .order_by(AnomalyFlag.score.asc(), AnomalyFlag.created_at.desc())
    )
    if not include_dismissed:
        stmt = stmt.where(AnomalyFlag.dismissed.is_(False))
    return [(flag, txn) for flag, txn in (await db.execute(stmt)).all()]


async def dismiss_anomaly_flag(
    db: AsyncSession, user_id: uuid.UUID, flag_id: uuid.UUID, reason: str | None = None
) -> tuple[AnomalyFlag, Transaction]:
    row = (
        await db.execute(
            select(AnomalyFlag, Transaction)
            .join(Transaction, Transaction.id == AnomalyFlag.transaction_id)
            .where(AnomalyFlag.id == flag_id, AnomalyFlag.user_id == user_id)
        )
    ).first()
    if row is None:
        raise AnomalyFlagNotFoundError(str(flag_id))

    flag, txn = row
    flag.dismissed = True
    flag.dismissal_reason = reason.strip()[:255] if reason and reason.strip() else None
    flag.dismissed_at = func.now()
    await db.commit()
    await db.refresh(flag)
    return flag, txn


async def compute_anomaly_stats(db: AsyncSession, user_id: uuid.UUID) -> dict:
    flags = list(
        (await db.scalars(select(AnomalyFlag).where(AnomalyFlag.user_id == user_id))).all()
    )
    total = len(flags)
    dismissed = sum(1 for f in flags if f.dismissed)
    active = total - dismissed

    by_severity: dict[str, int] = {}
    for f in flags:
        if not f.dismissed:
            by_severity[f.severity] = by_severity.get(f.severity, 0) + 1

    return {
        "total_flags": total,
        "active_flags": active,
        "dismissed_flags": dismissed,
        "by_severity": by_severity,
        "dismissal_rate": round(dismissed / total, 3) if total else 0.0,
    }
