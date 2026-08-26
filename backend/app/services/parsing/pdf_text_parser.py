import io
import re
from dataclasses import dataclass
from datetime import date as date_type
from datetime import datetime

import pdfplumber

from app.services.parsing.constants import (
    REASON_AMBIGUOUS_SIGN_CONVENTION,
    REASON_MALFORMED_ROW,
    REASON_NO_REQUIRED_COLUMNS_RESOLVED,
    REASON_UNPARSEABLE_AMOUNT,
    REASON_UNPARSEABLE_DATE,
)
from app.services.parsing.sign_convention import RowInputs, resolve_signs
from app.services.parsing.text_utils import parse_amount
from app.services.parsing.types import (
    ParsedRow,
    ParseOutcome,
    RowFailure,
    UnresolvableStructureError,
)

AMOUNT_RE = re.compile(r"\(?-?\$?\s?[\d,]+\.\d{2}\)?")

# Order matters: more specific patterns first. "slash"/"dash" numeric patterns
# are day/month-ambiguous and resolved once per statement below.
DATE_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("iso", re.compile(r"\b\d{4}-\d{2}-\d{2}\b")),
    ("day_month_name", re.compile(r"\b\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4}\b")),
    ("month_name_day", re.compile(r"\b[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{2,4}\b")),
    ("slash_ambiguous", re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b")),
    ("dash_ambiguous", re.compile(r"\b\d{1,2}-\d{1,2}-\d{2,4}\b")),
]

MAX_SAMPLE_LINES = 20


def extract_lines_from_pdf(file_bytes: bytes) -> list[str]:
    lines: list[str] = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            lines.extend(text.splitlines())
    return lines


@dataclass
class _Candidate:
    line_index: int
    raw_line: str
    date_pattern_name: str
    date_span: tuple[int, int]
    date_text: str
    amount_matches: list[re.Match]


def _find_date(line: str) -> tuple[str, re.Match] | None:
    for name, pattern in DATE_PATTERNS:
        m = pattern.search(line)
        if m:
            return name, m
    return None


def _candidates(lines: list[str]) -> list[_Candidate]:
    """Every line containing a date-like token — even if it turns out to
    have no usable amount — so it can be logged rather than silently
    dropped. Lines with no date token at all are ordinary statement prose
    (headers, disclaimers, page footers) and are never transaction
    candidates in the first place.
    """
    result = []
    for idx, line in enumerate(lines):
        date_match = _find_date(line)
        if date_match is None:
            continue
        pattern_name, m = date_match
        amounts = list(AMOUNT_RE.finditer(line))
        result.append(_Candidate(idx, line, pattern_name, (m.start(), m.end()), m.group(), amounts))
    return result


def _resolve_date_order(samples: list[str]) -> bool:
    """True = day-first. Resolved once per statement from a sample of the
    dominant pattern's matched date tokens (some component >12 in the
    second slot proves day-first; in the first slot proves month-first;
    genuinely ambiguous samples default to day-first)."""
    day_first_possible = True
    month_first_possible = True
    for s in samples:
        parts = re.split(r"[/-]", s)
        if len(parts) < 2:
            continue
        first, second = int(parts[0]), int(parts[1])
        if first > 12:
            month_first_possible = False
        if second > 12:
            day_first_possible = False
    return not (month_first_possible and not day_first_possible)


def _parse_date_token(pattern_name: str, text: str, day_first: bool) -> date_type | None:
    text = text.strip()
    if pattern_name == "iso":
        attempts_fmt = ["%Y-%m-%d"]
    elif pattern_name in ("slash_ambiguous", "dash_ambiguous"):
        sep = "/" if pattern_name == "slash_ambiguous" else "-"
        primary = f"%d{sep}%m{sep}%Y" if day_first else f"%m{sep}%d{sep}%Y"
        attempts_fmt = [primary, primary.replace("%Y", "%y")]
    elif pattern_name == "day_month_name":
        attempts_fmt = ["%d %b %Y", "%d %B %Y"]
    elif pattern_name == "month_name_day":
        text = text.replace(",", "")
        attempts_fmt = ["%b %d %Y", "%B %d %Y"]
    else:
        attempts_fmt = []

    for fmt in attempts_fmt:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def parse_text_lines(lines: list[str]) -> ParseOutcome:
    candidates = _candidates(lines)
    if not candidates:
        raise UnresolvableStructureError(
            REASON_NO_REQUIRED_COLUMNS_RESOLVED,
            "no lines containing a date-like token were found",
        )

    pattern_counts: dict[str, int] = {}
    for c in candidates:
        pattern_counts[c.date_pattern_name] = pattern_counts.get(c.date_pattern_name, 0) + 1
    dominant_pattern = max(pattern_counts, key=pattern_counts.get)

    failures: list[RowFailure] = []
    dominant_candidates = []
    for c in candidates:
        if c.date_pattern_name != dominant_pattern:
            failures.append(
                RowFailure(
                    row_index=c.line_index,
                    raw_line_text=c.raw_line,
                    reason_code=REASON_MALFORMED_ROW,
                    reason=(
                        f"date format '{c.date_pattern_name}' is inconsistent with this "
                        f"statement's dominant format '{dominant_pattern}'"
                    ),
                )
            )
        else:
            dominant_candidates.append(c)

    day_first = True
    if dominant_pattern in ("slash_ambiguous", "dash_ambiguous"):
        day_first = _resolve_date_order(
            [c.date_text for c in dominant_candidates[:MAX_SAMPLE_LINES]]
        )

    amount_counts = [len(c.amount_matches) for c in dominant_candidates[:MAX_SAMPLE_LINES]]
    modal_amount_count = max(set(amount_counts), key=amount_counts.count) if amount_counts else 1
    has_balance_column = modal_amount_count >= 2

    parsed_dates: dict[int, date_type] = {}
    row_inputs: list[RowInputs] = []
    descriptions: dict[int, str] = {}
    raw_lines: dict[int, str] = {}

    for c in dominant_candidates:
        raw_lines[c.line_index] = c.raw_line

        if not c.amount_matches:
            failures.append(
                RowFailure(
                    row_index=c.line_index,
                    raw_line_text=c.raw_line,
                    reason_code=REASON_UNPARSEABLE_AMOUNT,
                    reason="line has a date but no amount-like token",
                )
            )
            continue

        parsed_date = _parse_date_token(c.date_pattern_name, c.date_text, day_first)
        if parsed_date is None:
            failures.append(
                RowFailure(
                    row_index=c.line_index,
                    raw_line_text=c.raw_line,
                    reason_code=REASON_UNPARSEABLE_DATE,
                    reason=f"could not parse date token '{c.date_text}'",
                )
            )
            continue
        parsed_dates[c.line_index] = parsed_date

        remaining = c.raw_line[: c.date_span[0]] + c.raw_line[c.date_span[1] :]
        for m in c.amount_matches:
            remaining = remaining.replace(m.group(), " ")
        descriptions[c.line_index] = re.sub(r"\s+", " ", remaining).strip()

        if has_balance_column and len(c.amount_matches) >= 2:
            amount_raw = c.amount_matches[-2].group()
            balance_raw = c.amount_matches[-1].group()
        else:
            amount_raw = c.amount_matches[0].group()
            balance_raw = None

        row_inputs.append(
            RowInputs(row_index=c.line_index, amount_raw=amount_raw, balance_raw=balance_raw)
        )

    roles: dict[str, int] = {"amount": 0}
    if has_balance_column:
        roles["balance"] = 1

    sign_result = resolve_signs(roles, row_inputs, parsed_dates)

    rows: list[ParsedRow] = []
    for row_input in row_inputs:
        idx = row_input.row_index
        if idx not in sign_result.signed_amounts:
            failures.append(
                RowFailure(
                    row_index=idx,
                    raw_line_text=raw_lines[idx],
                    reason_code=REASON_UNPARSEABLE_AMOUNT,
                    reason="could not resolve a transaction amount for this line",
                )
            )
            continue
        rows.append(
            ParsedRow(
                row_index=idx,
                date=parsed_dates[idx],
                description=descriptions.get(idx, ""),
                amount=sign_result.signed_amounts[idx],
                raw_line_text=raw_lines[idx],
                running_balance=(
                    parse_amount(row_input.balance_raw) if row_input.balance_raw else None
                ),
            )
        )

    warnings = list(sign_result.warnings)
    if sign_result.convention == "single_column_assume_debit":
        failures.append(
            RowFailure(
                row_index=None,
                raw_line_text="",
                reason_code=REASON_AMBIGUOUS_SIGN_CONVENTION,
                reason=sign_result.warnings[-1] if sign_result.warnings else "assumed all-debit",
            )
        )

    structural_signature = (
        f"structure=pdf_text|date_pattern={dominant_pattern}|day_first={day_first}|"
        f"amounts_per_line={modal_amount_count}"
    )

    return ParseOutcome(
        rows=rows,
        failures=failures,
        column_map={
            "date_pattern": dominant_pattern,
            "day_first": day_first,
            "amounts_per_line": modal_amount_count,
        },
        date_format=dominant_pattern,
        amount_sign_convention=sign_result.convention,
        regex_pattern=dominant_pattern,
        header_fingerprint_text=structural_signature,
        warnings=warnings,
        sample_lines=[c.raw_line for c in dominant_candidates[:5]],
    )
