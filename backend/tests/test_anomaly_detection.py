"""Phase 6 — per-user IsolationForest anomaly detection with explainability.

The synthetic history below is a stable, ~5-month spending pattern for one
user (regular groceries / dining / transit / a monthly power bill), into
which two *known* anomalies are injected:

* ``anomaly_big``   — a $1,200 grocery charge, ~20x the user's normal
  grocery spend. Expected driver: ``amount_ratio_in_category``.
* ``anomaly_novel`` — a modest charge in a category (travel) and at a
  merchant the user has never used. Expected drivers: ``merchant_novelty``
  and/or ``category_rarity``.

Recall against that injected set is asserted exactly (both must be
flagged). Precision only gets a sanity floor — the "normal" rows are
unlabelled and legitimately contain a few borderline-odd transactions
(a first-ever utility payment, etc.), so demanding perfect precision
against synthetic data would be dishonest.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.anomaly_flag import AnomalyFlag
from app.models.statement import Statement
from app.models.transaction import Transaction
from app.models.user import User
from app.services.anomaly import detector
from app.services.anomaly import service as anomaly_service

# (merchant, category, repeating amounts, cadence in days, start offset, count)
_NORMAL_SPECS = [
    ("Whole Foods", "groceries", ["-58", "-62", "-60", "-64", "-56", "-61"], 7, 1, 24),
    ("Chipotle", "dining", ["-22", "-26", "-24"], 8, 5, 10),
    ("Olive Garden", "dining", ["-31", "-29", "-33"], 8, 9, 10),
    ("Metro Transit", "transit", ["-2.75", "-3.00", "-2.50"], 11, 3, 16),
    ("City Power", "utilities", ["-118", "-122", "-120", "-125"], 30, 15, 8),
]
_NORMAL_COUNT = sum(spec[5] for spec in _NORMAL_SPECS)  # 68


async def _seed_user_and_statement(db_session, authed_client: AsyncClient):
    await authed_client.get("/accounts")  # ensures the authed user row exists
    user = await db_session.scalar(select(User).limit(1))
    statement = Statement(
        user_id=user.id, original_filename="synthetic.csv", file_path="x", file_type="csv"
    )
    db_session.add(statement)
    await db_session.flush()
    return statement, user


def _txn(statement, user, merchant, category, amount, on_date) -> Transaction:
    return Transaction(
        id=uuid.uuid4(),
        statement_id=statement.id,
        user_id=user.id,
        raw_merchant=merchant,
        normalized_merchant=merchant,
        category=category,
        amount=Decimal(amount),
        date=on_date,
    )


def _normal_history(statement, user) -> list[Transaction]:
    base = date(2026, 1, 1)
    txns: list[Transaction] = []
    for merchant, category, amounts, cadence, start, count in _NORMAL_SPECS:
        for i in range(count):
            txns.append(
                _txn(
                    statement,
                    user,
                    merchant,
                    category,
                    amounts[i % len(amounts)],
                    base + timedelta(days=start + i * cadence),
                )
            )
    return txns


async def _seed_history_with_anomalies(db_session, authed_client):
    statement, user = await _seed_user_and_statement(db_session, authed_client)
    txns = _normal_history(statement, user)

    anomaly_big = _txn(
        statement, user, "Whole Foods", "groceries", "-1200.00", date(2026, 3, 3)
    )
    anomaly_novel = _txn(
        statement, user, "Anteros Air", "travel", "-95.00", date(2026, 4, 7)
    )
    txns.extend([anomaly_big, anomaly_novel])

    db_session.add_all(txns)
    await db_session.commit()
    return user, anomaly_big, anomaly_novel


async def test_injected_anomalies_are_flagged_with_correct_drivers(
    authed_client: AsyncClient, db_session
) -> None:
    user, anomaly_big, anomaly_novel = await _seed_history_with_anomalies(
        db_session, authed_client
    )

    result = await anomaly_service.run_anomaly_detection(db_session, user.id)
    assert result["model_trained"] is True
    assert result["transactions_considered"] == _NORMAL_COUNT + 2

    flags = await anomaly_service.list_anomaly_flags(db_session, user.id)
    flag_by_txn = {txn.id: flag for flag, txn in flags}
    flagged_ids = set(flag_by_txn)
    injected = {anomaly_big.id, anomaly_novel.id}

    # Recall: every injected anomaly is caught.
    assert injected <= flagged_ids
    recall = len(injected & flagged_ids) / len(injected)
    assert recall == 1.0

    # Precision: a sanity floor only (see module docstring).
    precision = len(injected & flagged_ids) / len(flagged_ids)
    assert precision >= 0.4, f"too many false positives: {flagged_ids - injected}"

    big_drivers = {d["feature"] for d in flag_by_txn[anomaly_big.id].driving_features_json}
    assert "amount_ratio_in_category" in big_drivers
    big_explanation = next(
        d["explanation"]
        for d in flag_by_txn[anomaly_big.id].driving_features_json
        if d["feature"] == "amount_ratio_in_category"
    )
    assert "typical" in big_explanation and "groceries" in big_explanation

    novel_drivers = {d["feature"] for d in flag_by_txn[anomaly_novel.id].driving_features_json}
    assert novel_drivers & {"merchant_novelty", "category_rarity"}

    # Severity is populated and within the known vocabulary.
    assert flag_by_txn[anomaly_big.id].severity in {"low", "medium", "high"}


async def test_thin_history_trains_no_model(authed_client: AsyncClient, db_session) -> None:
    statement, user = await _seed_user_and_statement(db_session, authed_client)
    db_session.add_all(
        [
            _txn(statement, user, "Whole Foods", "groceries", "-60", date(2026, 1, d))
            for d in range(1, 6)
        ]
    )
    await db_session.commit()

    result = await anomaly_service.run_anomaly_detection(db_session, user.id)
    assert result["model_trained"] is False
    assert result["active_flag_count"] == 0
    assert (await anomaly_service.list_anomaly_flags(db_session, user.id)) == []


async def test_dismissal_is_sticky_across_refits(
    authed_client: AsyncClient, db_session
) -> None:
    user, _anomaly_big, anomaly_novel = await _seed_history_with_anomalies(
        db_session, authed_client
    )
    await anomaly_service.run_anomaly_detection(db_session, user.id)

    flags = await anomaly_service.list_anomaly_flags(db_session, user.id)
    novel_flag = next(flag for flag, txn in flags if txn.id == anomaly_novel.id)

    await anomaly_service.dismiss_anomaly_flag(
        db_session, user.id, novel_flag.id, reason="known — booked a flight"
    )

    # Re-running detection must not resurface or duplicate the dismissed flag.
    second = await anomaly_service.run_anomaly_detection(db_session, user.id)
    assert second["new_flag_count"] == 0

    active = await anomaly_service.list_anomaly_flags(db_session, user.id)
    assert anomaly_novel.id not in {txn.id for _flag, txn in active}

    all_flags = await anomaly_service.list_anomaly_flags(
        db_session, user.id, include_dismissed=True
    )
    novel_rows = [flag for flag, txn in all_flags if txn.id == anomaly_novel.id]
    assert len(novel_rows) == 1
    assert novel_rows[0].dismissed is True
    assert novel_rows[0].dismissal_reason == "known — booked a flight"


async def test_dismissal_feedback_suppresses_soft_but_not_hard_repeat(
    authed_client: AsyncClient, db_session
) -> None:
    """The core of the feedback loop, tested at the detector: once a
    (merchant, category) pair is dismissed, a *soft* repeat (novel/rare
    only) is suppressed, but a hard one (large amount) still surfaces."""
    user, anomaly_big, anomaly_novel = await _seed_history_with_anomalies(
        db_session, authed_client
    )
    transactions = list(
        (await db_session.scalars(select(Transaction).where(Transaction.user_id == user.id))).all()
    )

    baseline, trained = detector.detect(transactions)
    assert trained
    baseline_ids = {r.transaction_id for r in baseline}
    assert {anomaly_big.id, anomaly_novel.id} <= baseline_ids

    # Dismissing the novel-merchant signature suppresses it (soft drivers only)...
    suppressed_novel = detector.detect(
        transactions, suppressed_signatures={("anteros air", "travel")}
    )[0]
    assert anomaly_novel.id not in {r.transaction_id for r in suppressed_novel}

    # ...but dismissing the grocery signature does NOT excuse a 20x charge.
    suppressed_big = detector.detect(
        transactions, suppressed_signatures={("whole foods", "groceries")}
    )[0]
    assert anomaly_big.id in {r.transaction_id for r in suppressed_big}


async def test_anomaly_feed_and_dismiss_endpoints(
    authed_client: AsyncClient, db_session
) -> None:
    user, anomaly_big, _anomaly_novel = await _seed_history_with_anomalies(
        db_session, authed_client
    )

    run = await authed_client.post("/anomalies/detect")
    assert run.status_code == 200
    assert run.json()["model_trained"] is True

    feed = (await authed_client.get("/anomalies")).json()
    assert len(feed) >= 2
    big_item = next(item for item in feed if item["transaction_id"] == str(anomaly_big.id))
    assert big_item["transaction"]["raw_merchant"] == "Whole Foods"
    assert big_item["transaction"]["amount"] == "-1200.00"
    assert any(
        d["feature"] == "amount_ratio_in_category" for d in big_item["driving_features"]
    )
    # feed is ordered most-anomalous (lowest score) first
    scores = [item["score"] for item in feed]
    assert scores == sorted(scores)

    dismiss = await authed_client.post(
        f"/anomalies/{big_item['id']}/dismiss", json={"reason": "verified with the bank"}
    )
    assert dismiss.status_code == 200
    assert dismiss.json()["dismissed"] is True

    feed_after = (await authed_client.get("/anomalies")).json()
    assert big_item["id"] not in {item["id"] for item in feed_after}

    stats = (await authed_client.get("/anomalies/stats")).json()
    assert stats["dismissed_flags"] == 1
    assert stats["total_flags"] >= 2
    assert 0.0 < stats["dismissal_rate"] <= 1.0


async def test_dismiss_unknown_flag_returns_404(authed_client: AsyncClient) -> None:
    response = await authed_client.post(f"/anomalies/{uuid.uuid4()}/dismiss", json={})
    assert response.status_code == 404


@pytest.mark.parametrize("include_dismissed", [False, True])
async def test_flags_are_user_scoped(
    authed_client: AsyncClient, db_session, include_dismissed
) -> None:
    user, _big, _novel = await _seed_history_with_anomalies(db_session, authed_client)
    await anomaly_service.run_anomaly_detection(db_session, user.id)

    other = User(email="other@example.com", hashed_password="x")
    db_session.add(other)
    await db_session.commit()

    rows = await anomaly_service.list_anomaly_flags(db_session, other.id, include_dismissed)
    assert rows == []
    other_flags = await db_session.scalar(
        select(AnomalyFlag).where(AnomalyFlag.user_id == other.id)
    )
    assert other_flags is None
