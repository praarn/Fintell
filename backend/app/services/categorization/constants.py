from typing import Literal

CATEGORIES = [
    "groceries",
    "dining",
    "food_delivery",
    "transit",
    "utilities",
    "subscriptions",
    "entertainment",
    "shopping",
    "travel",
    "health",
    "income",
    "transfers",
    "fees",
    "other",
]

CategoryLiteral = Literal[*CATEGORIES]  # type: ignore[valid-type]

# How a transaction was categorized — the auditability story. `None` means
# genuinely unresolved at Tier 1/2 (a Tier 3 LLM call, added in Phase 4,
# is what would resolve it next).
METHOD_RULE_EXACT = "rule_exact"
METHOD_RULE_FUZZY = "rule_fuzzy"
METHOD_LLM = "llm"
METHOD_MANUAL_USER_CORRECTION = "manual_user_correction"

# How a merchant_lookup row itself came to exist.
MATCH_TYPE_SEED = "seed"
MATCH_TYPE_USER_CORRECTION = "user_correction"
MATCH_TYPE_LLM_PROMOTION = "llm_promotion"

FUZZY_MATCH_SCORE_FLOOR = 60.0  # below this, not even worth surfacing as a low-confidence guess
