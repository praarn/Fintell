from dataclasses import dataclass, field
from datetime import date as date_type
from decimal import Decimal


@dataclass
class ParsedRow:
    row_index: int
    date: date_type
    description: str
    amount: Decimal
    raw_line_text: str
    running_balance: Decimal | None = None


@dataclass
class RowFailure:
    raw_line_text: str
    reason_code: str
    reason: str
    row_index: int | None = None


@dataclass
class ParseOutcome:
    """Result of running one structure-specific parser against a statement.

    `column_map`, `date_format`, and `amount_sign_convention` are exactly
    what a BankProfile persists so the same layout can be recognized and
    reused next time, without re-deriving it from scratch.
    """

    rows: list[ParsedRow]
    failures: list[RowFailure]
    column_map: dict
    date_format: str
    amount_sign_convention: str
    regex_pattern: str | None = None
    header_fingerprint_text: str = ""
    header_cells: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    sample_lines: list[str] = field(default_factory=list)


class UnresolvableStructureError(Exception):
    """Raised when a statement's structure can't be parsed at all —
    e.g. no required columns resolved, or OCR was unavailable/low-confidence.
    Callers turn this into a whole-statement ParseFailure + failed_needs_manual.
    """

    def __init__(self, reason_code: str, reason: str) -> None:
        self.reason_code = reason_code
        self.reason = reason
        super().__init__(reason)
