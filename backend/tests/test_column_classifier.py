from app.services.parsing.column_classifier import classify_columns


def test_classifies_standard_headers_by_synonym_match() -> None:
    header = ["Date", "Description", "Amount"]
    samples = [
        ["01/03/2024", "Grocery Mart", "-54.23"],
        ["01/05/2024", "Salary Deposit", "2500.00"],
    ]
    result = classify_columns(header, samples)
    assert result is not None
    assert result.roles == {"date": 0, "description": 1, "amount": 2}
    assert result.warnings == []


def test_classifies_reordered_and_nonstandard_headers() -> None:
    header = ["Particulars", "Type", "Amt", "Txn Date"]
    samples = [
        ["Grocery Mart", "DR", "54.23", "01/03/2024"],
        ["Salary Deposit", "CR", "2500.00", "01/05/2024"],
    ]
    result = classify_columns(header, samples)
    assert result is not None
    assert result.roles["date"] == 3
    assert result.roles["description"] == 0
    assert result.roles["amount"] == 2
    assert result.roles["sign_indicator"] == 1


def test_dtype_contradiction_unassigns_role_and_warns() -> None:
    # "Balance" header matches, but the column holds non-numeric text —
    # dtype sniffing should override the header match, drop the role, and
    # warn, while the still-resolvable required roles (via Amount) succeed.
    header = ["Date", "Description", "Amount", "Balance"]
    samples = [
        ["01/03/2024", "Grocery Mart", "-54.23", "not a number"],
        ["01/05/2024", "Salary Deposit", "2500.00", "also not a number"],
    ]
    result = classify_columns(header, samples)
    assert result is not None
    assert "balance" not in result.roles
    assert result.roles["amount"] == 2
    assert len(result.warnings) == 1


def test_all_amount_columns_dtype_contradiction_returns_none() -> None:
    header = ["Date", "Description", "Amount"]
    samples = [
        ["01/03/2024", "Grocery Mart", "not a number"],
        ["01/05/2024", "Salary Deposit", "also not a number"],
    ]
    # amount is unassigned and there's no debit/credit pair either, so
    # required-role resolution fails.
    assert classify_columns(header, samples) is None


def test_missing_required_role_returns_none() -> None:
    header = ["Reference", "Notes"]
    samples = [["REF001", "something"], ["REF002", "something else"]]
    assert classify_columns(header, samples) is None
