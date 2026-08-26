ROLE_SYNONYMS: dict[str, list[str]] = {
    "date": [
        "date",
        "txn date",
        "transaction date",
        "value date",
        "posting date",
        "posted date",
        "trans date",
    ],
    "description": [
        "description",
        "narration",
        "details",
        "particulars",
        "transaction details",
        "memo",
        "payee",
        "merchant",
    ],
    "debit": [
        "debit",
        "withdrawal",
        "withdrawal amt",
        "debit amount",
        "dr",
        "paid out",
    ],
    "credit": [
        "credit",
        "deposit",
        "deposit amt",
        "credit amount",
        "cr",
        "paid in",
    ],
    "amount": [
        "amount",
        "transaction amount",
        "amt",
        "value",
    ],
    "balance": [
        "balance",
        "running balance",
        "closing balance",
        "available balance",
        "balance amt",
    ],
    "sign_indicator": [
        "type",
        "dr/cr",
        "cr/dr",
        "transaction type",
        "dc indicator",
    ],
}

REQUIRED_ROLES = ("date", "description")

HEADER_SYNONYM_MATCH_THRESHOLD = 85.0
PROFILE_REVALIDATION_MATCH_THRESHOLD = 95.0

# reason codes for parse_failures.reason_code
REASON_UNPARSEABLE_DATE = "unparseable_date"
REASON_UNPARSEABLE_AMOUNT = "unparseable_amount"
REASON_NO_REQUIRED_COLUMNS_RESOLVED = "no_required_columns_resolved"
REASON_AMBIGUOUS_SIGN_CONVENTION = "ambiguous_sign_convention"
REASON_OCR_UNAVAILABLE = "ocr_unavailable"
REASON_OCR_LOW_CONFIDENCE = "ocr_low_confidence"
REASON_NO_TEXT_EXTRACTED = "no_text_extracted"
REASON_MALFORMED_ROW = "malformed_row"

MAX_HEADER_SCAN_ROWS = 5
DTYPE_SAMPLE_SIZE = 20
