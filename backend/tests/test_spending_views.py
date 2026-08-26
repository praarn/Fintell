from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from httpx import AsyncClient
from sqlalchemy import select

from app.models.statement import Statement
from app.models.transaction import Transaction
from app.models.user import User
from tests.conftest import FIXTURES_DIR


async def _upload(client: AsyncClient, filename: str = "csv_clean_standard.csv"):
    data = (FIXTURES_DIR / filename).read_bytes()
    return await client.post("/statements/upload", files={"file": (filename, data, "text/csv")})


async def test_spending_by_category_only_counts_outflows(authed_client: AsyncClient) -> None:
    await _upload(authed_client)
    upload = (await _upload(authed_client, "csv_debit_credit_columns.csv")).json()
    transactions = (await authed_client.get(f"/statements/{upload['id']}/transactions")).json()
    for t in transactions:
        if Decimal(t["amount"]) < 0:
            await authed_client.patch(
                f"/transactions/{t['id']}/category", json={"category": "groceries"}
            )

    spending = (await authed_client.get("/transactions/spending/by-category")).json()
    # income (salary deposit, transfer) never appears as "spend"
    assert Decimal(spending["total_spend"]) > 0
    assert "income" not in spending["by_category"]


async def test_top_merchants_ranks_by_total_spend(authed_client: AsyncClient) -> None:
    await _upload(authed_client)

    top = (await authed_client.get("/transactions/spending/top-merchants")).json()
    assert len(top) > 0
    spends = [Decimal(m["total_spend"]) for m in top]
    assert spends == sorted(spends, reverse=True)


async def test_spending_trend_zero_fills_and_sums_current_month(
    authed_client: AsyncClient, db_session
) -> None:
    await authed_client.get("/accounts")  # ensures the authed user exists before we query it
    user = await db_session.scalar(select(User).limit(1))
    statement = Statement(
        user_id=user.id,
        original_filename="synthetic.csv",
        file_path="synthetic.csv",
        file_type="csv",
    )
    db_session.add(statement)
    await db_session.flush()

    today = date.today()
    db_session.add_all(
        [
            Transaction(
                statement_id=statement.id,
                user_id=user.id,
                raw_merchant="Test Merchant A",
                amount=Decimal("-25.00"),
                date=today,
            ),
            Transaction(
                statement_id=statement.id,
                user_id=user.id,
                raw_merchant="Test Merchant B",
                amount=Decimal("-15.00"),
                date=today - relativedelta(months=1),
            ),
        ]
    )
    await db_session.commit()

    trend = (await authed_client.get("/transactions/spending/trend", params={"months": 3})).json()
    assert len(trend) == 3
    by_month = {p["month"]: Decimal(p["total_spend"]) for p in trend}
    current_key = f"{today.year:04d}-{today.month:02d}"
    assert by_month[current_key] == Decimal("25.00")
    two_months_ago = today - relativedelta(months=2)
    oldest_key = f"{two_months_ago.year:04d}-{two_months_ago.month:02d}"
    assert by_month[oldest_key] == Decimal("0")
