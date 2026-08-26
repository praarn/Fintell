import re

# Card-network / payment-rail boilerplate prefixes seen at the start of a
# raw merchant string. Stripped first since everything after them is what
# actually identifies the merchant.
_PREFIX_RE = re.compile(
    r"^(pos|upi|neft|imps|ach|rtgs|atm|card purchase|debit card purchase|"
    r"visa debit|mc debit|purchase)[\s\-/:]+",
    re.IGNORECASE,
)

_UPI_HANDLE_RE = re.compile(r"@[\w.\-]+")
_LONG_REF_CODE_RE = re.compile(r"[#*]?\d{6,}")
_STANDALONE_DIGIT_TOKEN_RE = re.compile(r"\b\d{4,}\b")
_SEPARATOR_RE = re.compile(r"[-_/]+")
_PUNCTUATION_RE = re.compile(r"[^\w\s]")
_WHITESPACE_RE = re.compile(r"\s+")

# Statements commonly append "MERCHANT NAME CITY ST" — stripping a trailing
# real US state code is a cheap, low-risk win. Anything beyond this (full
# city-name removal) would need a city gazetteer, which is out of scope for
# rule-based Tier 1/2 cleanup — fuzzy matching is what picks up that slack.
_US_STATE_CODES = {
    "al",
    "ak",
    "az",
    "ar",
    "ca",
    "co",
    "ct",
    "de",
    "fl",
    "ga",
    "hi",
    "id",
    "il",
    "in",
    "ia",
    "ks",
    "ky",
    "la",
    "me",
    "md",
    "ma",
    "mi",
    "mn",
    "ms",
    "mo",
    "mt",
    "ne",
    "nv",
    "nh",
    "nj",
    "nm",
    "ny",
    "nc",
    "nd",
    "oh",
    "ok",
    "or",
    "pa",
    "ri",
    "sc",
    "sd",
    "tn",
    "tx",
    "ut",
    "vt",
    "va",
    "wa",
    "wv",
    "wi",
    "wy",
}


def clean_merchant_string(raw: str) -> str:
    """Strips transaction reference codes, POS/payment-rail boilerplate,
    UPI handles, and trailing state codes, returning a lowercase matching
    key. This is deliberately boring, regex-only string cleanup — most of
    the "AI-sounding" merchant normalization problem is actually solved
    here, before any matching (exact or fuzzy) ever runs.
    """
    text = raw.strip()
    text = _PREFIX_RE.sub("", text)
    text = _UPI_HANDLE_RE.sub("", text)
    text = _LONG_REF_CODE_RE.sub("", text)
    text = _STANDALONE_DIGIT_TOKEN_RE.sub("", text)
    text = _SEPARATOR_RE.sub(" ", text)
    text = _PUNCTUATION_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()

    tokens = text.split(" ")
    if len(tokens) > 1 and tokens[-1].lower() in _US_STATE_CODES:
        tokens = tokens[:-1]
    text = " ".join(tokens)

    return text.lower().strip()
