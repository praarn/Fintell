import hashlib
import re
from datetime import date as date_type
from datetime import datetime
from decimal import Decimal, InvalidOperation

CANDIDATE_DATE_FORMATS = [
    "%m/%d/%Y",
    "%d/%m/%Y",
    "%Y-%m-%d",
    "%d-%m-%Y",
    "%m-%d-%Y",
    "%d/%m/%y",
    "%m/%d/%y",
    "%d %b %Y",
    "%d %B %Y",
    "%b %d, %Y",
    "%B %d, %Y",
    "%d-%b-%Y",
    "%d-%b-%y",
]

_AMOUNT_CLEAN_RE = re.compile(r"[^\d.\-]")


def normalize_cell(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_fingerprint_text(cells: list[str]) -> str:
    return "|".join(normalize_cell(c) for c in cells)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_amount(raw: str) -> Decimal | None:
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None

    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1]
    elif text.startswith("-"):
        negative = True
    elif text.startswith("+"):
        text = text[1:]

    text = text.replace(",", "")
    cleaned = _AMOUNT_CLEAN_RE.sub("", text)
    if not cleaned or cleaned in {"-", "."}:
        return None

    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None

    value = abs(value)
    return -value if negative else value


def looks_like_amount(raw: str) -> bool:
    return parse_amount(raw) is not None


def detect_date_format(samples: list[str]) -> str | None:
    samples = [s.strip() for s in samples if s and s.strip()]
    if not samples:
        return None

    best_format = None
    best_score = 0
    for fmt in CANDIDATE_DATE_FORMATS:
        score = 0
        for sample in samples:
            try:
                datetime.strptime(sample, fmt)
                score += 1
            except ValueError:
                pass
        if score > best_score:
            best_score = score
            best_format = fmt

    if best_format is None or best_score < max(1, len(samples) // 2):
        return None
    return best_format


def parse_date_with_format(raw: str, fmt: str) -> date_type | None:
    if not raw:
        return None
    try:
        return datetime.strptime(raw.strip(), fmt).date()
    except ValueError:
        return None


def looks_like_date(raw: str) -> bool:
    if not raw or not raw.strip():
        return False
    for fmt in CANDIDATE_DATE_FORMATS:
        try:
            datetime.strptime(raw.strip(), fmt)
            return True
        except ValueError:
            continue
    return False
