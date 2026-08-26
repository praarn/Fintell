from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from httpx import AsyncClient
from sqlalchemy import select

from app.models.statement import Statement
from app.models.transaction import Transaction
from app.models.user import User


async def _seed_statement(db_session, authed_client: AsyncClient) -> Statement:
    await authed_client.get("/accounts")  # ensures the authed user row exists
    user = await db_session.scalar(select(User).limit(1))
    statement = Statement(
        user_id=user.id, original_filename="synthetic.csv", file_path="x", file_type="csv"
    )
    db_session.add(statement)
    await db_session.flush()
    return statement, user


async def _add_txn(db_session, statement, user, merchant, amount, on_date):
    db_session.add(
        Transaction(
            statement_id=statement.id,
            user_id=user.id,
            raw_merchant=merchant,
            normalized_merchant=merchant,
            amount=Decimal(amount),
            date=on_date,
        )
    )


async def test_monthly_subscription_detected_as_recurring(
    authed_client: AsyncClient, db_session
) -> None:
    statement, user = await _seed_statement(db_session, authed_client)
    today = date.today()
    for i in range(4):
        await _add_txn(
            db_session,
            statement,
            user,
            "Netflix",
            "-15.99",
            today - relativedelta(months=3 - i),
        )
    await db_session.commit()

    groups = (await authed_client.get("/transactions/recurring")).json()
    netflix = next((g for g in groups if g["normalized_merchant"] == "Netflix"), None)
    assert netflix is not None
    assert netflix["frequency_label"] == "monthly"
    assert netflix["occurrences"] == 4
    assert Decimal(netflix["typical_amount"]) == Decimal("-15.99")


async def test_irregular_transactions_not_flagged_recurring(
    authed_client: AsyncClient, db_session
) -> None:
    statement, user = await _seed_statement(db_session, authed_client)
    today = date.today()
    # Same merchant/amount, but wildly irregular gaps.
    for offset in (0, 5, 40, 41):
        await _add_txn(
            db_session, statement, user, "Random Cafe", "-8.50", today - relativedelta(days=offset)
        )
    await db_session.commit()

    groups = (await authed_client.get("/transactions/recurring")).json()
    assert not any(g["normalized_merchant"] == "Random Cafe" for g in groups)


async def test_too_few_occurrences_not_flagged(authed_client: AsyncClient, db_session) -> None:
    statement, user = await _seed_statement(db_session, authed_client)
    today = date.today()
    for i in range(2):
        await _add_txn(
            db_session, statement, user, "Gym Membership", "-40.00", today - relativedelta(months=i)
        )
    await db_session.commit()

    groups = (await authed_client.get("/transactions/recurring")).json()
    assert not any(g["normalized_merchant"] == "Gym Membership" for g in groups)


async def test_different_amount_clusters_kept_separate(
    authed_client: AsyncClient, db_session
) -> None:
    statement, user = await _seed_statement(db_session, authed_client)
    today = date.today()
    # Same merchant, two very different amount tiers — should not merge.
    for i in range(3):
        await _add_txn(
            db_session, statement, user, "Utility Co", "-30.00", today - relativedelta(months=3 - i)
        )
    for i in range(3):
        await _add_txn(
            db_session,
            statement,
            user,
            "Utility Co",
            "-300.00",
            today - relativedelta(months=3 - i, days=2),
        )
    await db_session.commit()

    groups = [
        g
        for g in (await authed_client.get("/transactions/recurring")).json()
        if g["normalized_merchant"] == "Utility Co"
    ]
    assert len(groups) == 2
