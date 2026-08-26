import uuid
from datetime import date

from app.models.merchant_lookup import MerchantLookup
from app.models.statement import Statement
from app.models.transaction import Transaction
from app.models.user import User
from app.services.categorization.service import categorize_statement_transactions


async def _make_user_and_statement(db_session) -> tuple[User, Statement]:
    user = User(email=f"{uuid.uuid4()}@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.flush()

    statement = Statement(
        user_id=user.id,
        original_filename="test.csv",
        file_path="test.csv",
        file_type="csv",
    )
    db_session.add(statement)
    await db_session.flush()
    return user, statement


async def test_categorizes_exact_fuzzy_and_leaves_unresolved(db_session) -> None:
    db_session.add(
        MerchantLookup(
            raw_pattern="starbucks",
            normalized_name="Starbucks",
            category="dining",
            match_type="seed",
        )
    )
    await db_session.flush()

    _, statement = await _make_user_and_statement(db_session)

    exact_txn = Transaction(
        statement_id=statement.id,
        user_id=statement.user_id,
        raw_merchant="STARBUCKS",
        amount=-5.50,
        date=date(2024, 1, 3),
        row_index=0,
    )
    fuzzy_txn = Transaction(
        statement_id=statement.id,
        user_id=statement.user_id,
        raw_merchant="POS 1234 STARBUCKS COFFEE SEATTLE WA",
        amount=-6.75,
        date=date(2024, 1, 4),
        row_index=1,
    )
    unresolved_txn = Transaction(
        statement_id=statement.id,
        user_id=statement.user_id,
        raw_merchant="NEFT-N029388273482-JOHN DOE SALARY",
        amount=2500.00,
        date=date(2024, 1, 5),
        row_index=2,
    )
    db_session.add_all([exact_txn, fuzzy_txn, unresolved_txn])
    await db_session.commit()

    counts = await categorize_statement_transactions(db_session, statement.id)
    assert counts == {"rule_exact": 1, "rule_fuzzy": 1, "unresolved": 1}

    await db_session.refresh(exact_txn)
    await db_session.refresh(fuzzy_txn)
    await db_session.refresh(unresolved_txn)

    assert exact_txn.categorization_method == "rule_exact"
    assert exact_txn.category == "dining"
    assert float(exact_txn.confidence) == 1.0

    assert fuzzy_txn.categorization_method == "rule_fuzzy"
    assert fuzzy_txn.category == "dining"
    assert 0.75 <= float(fuzzy_txn.confidence) <= 1.0

    assert unresolved_txn.categorization_method is None
    assert unresolved_txn.category is None
    assert unresolved_txn.normalized_merchant  # still gets a cleaned display name
