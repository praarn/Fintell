from dataclasses import dataclass

from rapidfuzz import fuzz, process

from app.models.merchant_lookup import MerchantLookup
from app.services.categorization.constants import (
    FUZZY_MATCH_SCORE_FLOOR,
    METHOD_RULE_EXACT,
    METHOD_RULE_FUZZY,
)


@dataclass
class MatchOutcome:
    normalized_name: str
    category: str
    method: str
    confidence: float  # 0-1
    match_score: float  # 0-100, as returned by rapidfuzz — logged for threshold tuning


class MerchantMatcher:
    """Exact match first (O(1) dict lookup on the cleaned string), then
    rapidfuzz fuzzy match against every known pattern. Built once per
    statement/batch from a single fetch of merchant_lookup, not re-queried
    per transaction.
    """

    def __init__(self, lookup_rows: list[MerchantLookup], confidence_threshold: float) -> None:
        self._rows = lookup_rows
        self._by_pattern = {row.raw_pattern: row for row in lookup_rows}
        self._confidence_threshold = confidence_threshold

    def match(self, cleaned: str) -> MatchOutcome | None:
        if not cleaned:
            return None

        exact = self._by_pattern.get(cleaned)
        if exact is not None:
            return MatchOutcome(
                exact.normalized_name, exact.category, METHOD_RULE_EXACT, 1.0, 100.0
            )

        if not self._rows:
            return None

        choices = {row.id: row.raw_pattern for row in self._rows}
        # token_set_ratio, not WRatio: merchant strings frequently carry
        # extra tokens (city, POS codes) around the real name, and
        # WRatio's partial-ratio component false-positives badly on short
        # seed patterns — e.g. "grocery mart" vs "bart" scores 77 under
        # WRatio (character-substring illusion) but 37.5 under
        # token_set_ratio, which compares token sets instead.
        result = process.extractOne(cleaned, choices, scorer=fuzz.token_set_ratio)
        if result is None:
            return None

        _, score, row_id = result
        if score < FUZZY_MATCH_SCORE_FLOOR:
            return None

        confidence = score / 100.0
        if confidence < self._confidence_threshold:
            return None

        row = next(r for r in self._rows if r.id == row_id)
        return MatchOutcome(
            row.normalized_name, row.category, METHOD_RULE_FUZZY, confidence, float(score)
        )
