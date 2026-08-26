from datetime import date
from decimal import Decimal

from app.services.parsing.sign_convention import RowInputs, resolve_signs


def test_separate_debit_credit_columns() -> None:
    rows = [
        RowInputs(row_index=0, debit_raw="54.23", credit_raw=""),
        RowInputs(row_index=1, debit_raw="", credit_raw="2500.00"),
    ]
    result = resolve_signs({"debit": 0, "credit": 1}, rows, {})
    assert result.convention == "separate_debit_credit_columns"
    assert result.signed_amounts[0] == Decimal("-54.23")
    assert result.signed_amounts[1] == Decimal("2500.00")


def test_single_column_with_explicit_negative_values() -> None:
    rows = [
        RowInputs(row_index=0, amount_raw="-54.23"),
        RowInputs(row_index=1, amount_raw="2500.00"),
    ]
    result = resolve_signs({"amount": 0}, rows, {})
    assert result.convention == "debit_negative_single_column"
    assert result.signed_amounts[0] == Decimal("-54.23")
    assert result.signed_amounts[1] == Decimal("2500.00")


def test_single_column_with_sign_indicator() -> None:
    rows = [
        RowInputs(row_index=0, amount_raw="54.23", sign_indicator_raw="DR"),
        RowInputs(row_index=1, amount_raw="2500.00", sign_indicator_raw="CR"),
    ]
    result = resolve_signs({"amount": 0, "sign_indicator": 1}, rows, {})
    assert result.convention == "single_column_sign_indicator"
    assert result.signed_amounts[0] == Decimal("-54.23")
    assert result.signed_amounts[1] == Decimal("2500.00")


def test_single_column_balance_delta_inference_oldest_first() -> None:
    rows = [
        RowInputs(row_index=0, amount_raw="54.23", balance_raw="4945.77"),
        RowInputs(row_index=1, amount_raw="2500.00", balance_raw="7445.77"),
        RowInputs(row_index=2, amount_raw="15.99", balance_raw="7429.78"),
    ]
    dates = {0: date(2024, 1, 3), 1: date(2024, 1, 5), 2: date(2024, 1, 7)}
    result = resolve_signs({"amount": 0, "balance": 1}, rows, dates)
    assert result.convention == "single_column_balance_inferred"
    assert result.signed_amounts[0] == Decimal("-54.23")
    assert result.signed_amounts[1] == Decimal("2500.00")
    assert result.signed_amounts[2] == Decimal("-15.99")
    # The earliest row in the sequence has no prior balance to diff against,
    # so it always falls back to assume-debit — that's the one expected warning.
    assert len(result.warnings) == 1


def test_single_column_balance_delta_inference_newest_first() -> None:
    # Same three transactions, listed in reverse chronological order —
    # sign inference sorts by parsed date internally, not file order.
    rows = [
        RowInputs(row_index=0, amount_raw="15.99", balance_raw="7429.78"),
        RowInputs(row_index=1, amount_raw="2500.00", balance_raw="7445.77"),
        RowInputs(row_index=2, amount_raw="54.23", balance_raw="4945.77"),
    ]
    dates = {0: date(2024, 1, 7), 1: date(2024, 1, 5), 2: date(2024, 1, 3)}
    result = resolve_signs({"amount": 0, "balance": 1}, rows, dates)
    assert result.signed_amounts[0] == Decimal("-15.99")
    assert result.signed_amounts[1] == Decimal("2500.00")
    assert result.signed_amounts[2] == Decimal("-54.23")


def test_single_column_no_signal_assumes_debit_and_warns() -> None:
    rows = [RowInputs(row_index=0, amount_raw="54.23")]
    result = resolve_signs({"amount": 0}, rows, {})
    assert result.convention == "single_column_assume_debit"
    assert result.signed_amounts[0] == Decimal("-54.23")
    assert len(result.warnings) == 1
