from datetime import date
from decimal import Decimal

from app.services.parsing.csv_parser import parse_csv
from tests.conftest import FIXTURES_DIR


def _read(name: str) -> bytes:
    return (FIXTURES_DIR / name).read_bytes()


def test_clean_standard_debit_negative() -> None:
    outcome = parse_csv(_read("csv_clean_standard.csv"))
    assert len(outcome.rows) == 10
    assert not outcome.failures
    assert outcome.amount_sign_convention == "debit_negative_single_column"
    first = outcome.rows[0]
    assert first.date == date(2024, 1, 3)
    assert first.description == "Grocery Mart #4471"
    assert first.amount == Decimal("-54.23")


def test_separate_debit_credit_columns_nonstandard_headers() -> None:
    outcome = parse_csv(_read("csv_debit_credit_columns.csv"))
    assert len(outcome.rows) == 10
    assert not outcome.failures
    assert outcome.amount_sign_convention == "separate_debit_credit_columns"
    assert outcome.rows[1].amount == Decimal("2500.00")  # salary deposit, a credit


def test_reordered_columns_with_sign_indicator() -> None:
    outcome = parse_csv(_read("csv_reordered_columns_positive_debit.csv"))
    assert len(outcome.rows) == 10
    assert not outcome.failures
    assert outcome.amount_sign_convention == "single_column_sign_indicator"
    assert outcome.rows[0].amount == Decimal("-54.23")


def test_single_column_balance_inference() -> None:
    outcome = parse_csv(_read("csv_single_column_balance_inference.csv"))
    assert len(outcome.rows) == 10
    assert not outcome.failures
    assert outcome.amount_sign_convention == "single_column_balance_inferred"
    assert outcome.rows[0].amount == Decimal("-54.23")
    assert outcome.rows[0].running_balance == Decimal("4945.77")


def test_banner_rows_are_skipped_to_find_real_header() -> None:
    outcome = parse_csv(_read("csv_with_banner_rows.csv"))
    assert len(outcome.rows) == 10
    assert not outcome.failures


def test_malformed_rows_logged_without_failing_whole_statement() -> None:
    outcome = parse_csv(_read("csv_malformed_rows.csv"))
    assert len(outcome.rows) == 8
    assert len(outcome.failures) == 2
    reason_codes = {f.reason_code for f in outcome.failures}
    assert reason_codes == {"unparseable_date", "unparseable_amount"}
