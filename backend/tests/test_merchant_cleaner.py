from app.services.categorization.merchant_cleaner import clean_merchant_string


def test_strips_pos_prefix_and_terminal_digits() -> None:
    assert clean_merchant_string("POS 4829 STARBUCKS COFFEE #4471") == "starbucks coffee"


def test_strips_upi_prefix_and_handle() -> None:
    assert clean_merchant_string("UPI-SWIGGY@okhdfcbank-201029383") == "swiggy"


def test_strips_trailing_state_code() -> None:
    assert clean_merchant_string("Starbucks Coffee Seattle WA") == "starbucks coffee seattle"


def test_strips_neft_reference_code() -> None:
    result = clean_merchant_string("NEFT-N029388273482-ACME CORP")
    assert "029388273482" not in result
    assert "acme corp" in result


def test_collapses_whitespace_and_lowercases() -> None:
    assert clean_merchant_string("  Whole   Foods   Market  ") == "whole foods market"


def test_empty_string_stays_empty() -> None:
    assert clean_merchant_string("") == ""
    assert clean_merchant_string("   ") == ""
