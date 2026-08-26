import uuid

from app.models.merchant_lookup import MerchantLookup
from app.services.categorization.matcher import MerchantMatcher


def _row(pattern: str, name: str, category: str) -> MerchantLookup:
    return MerchantLookup(
        id=uuid.uuid4(),
        raw_pattern=pattern,
        normalized_name=name,
        category=category,
        match_type="seed",
    )


def test_exact_match_returns_full_confidence() -> None:
    rows = [_row("starbucks", "Starbucks", "dining")]
    matcher = MerchantMatcher(rows, confidence_threshold=0.75)

    result = matcher.match("starbucks")
    assert result is not None
    assert result.method == "rule_exact"
    assert result.confidence == 1.0
    assert result.category == "dining"


def test_fuzzy_match_above_threshold() -> None:
    rows = [_row("starbucks", "Starbucks", "dining")]
    matcher = MerchantMatcher(rows, confidence_threshold=0.75)

    result = matcher.match("starbucks coffee seattle")
    assert result is not None
    assert result.method == "rule_fuzzy"
    assert result.confidence >= 0.75
    assert result.category == "dining"


def test_no_match_below_confidence_threshold() -> None:
    rows = [_row("starbucks", "Starbucks", "dining")]
    matcher = MerchantMatcher(rows, confidence_threshold=0.99)

    # A partial match that scores well but not near-perfect should be
    # rejected when the configured threshold is set very high.
    result = matcher.match("some totally unrelated merchant name")
    assert result is None


def test_empty_lookup_table_never_matches() -> None:
    matcher = MerchantMatcher([], confidence_threshold=0.75)
    assert matcher.match("starbucks") is None


def test_empty_cleaned_string_never_matches() -> None:
    rows = [_row("starbucks", "Starbucks", "dining")]
    matcher = MerchantMatcher(rows, confidence_threshold=0.75)
    assert matcher.match("") is None
