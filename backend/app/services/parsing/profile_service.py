from dataclasses import dataclass
from datetime import UTC, datetime

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.bank_profile import BankProfile
from app.services.parsing import csv_parser, ocr_parser, pdf_table_parser, pdf_text_parser
from app.services.parsing.constants import (
    DTYPE_SAMPLE_SIZE,
    MAX_HEADER_SCAN_ROWS,
    PROFILE_REVALIDATION_MATCH_THRESHOLD,
    REQUIRED_ROLES,
)
from app.services.parsing.fingerprint import ProfileCandidate, find_candidate_profile
from app.services.parsing.grid_parser import parse_rows_with_known_roles
from app.services.parsing.text_utils import (
    normalize_cell,
    normalize_fingerprint_text,
    parse_date_with_format,
    sha256_hex,
)
from app.services.parsing.types import ParseOutcome

settings = get_settings()

STRUCTURE_TO_PROFILE_TYPE = {
    "clean_csv": "csv_header",
    "pdf_table": "pdf_table_header",
    "pdf_text_no_table": "pdf_text_regex",
    "pdf_scan_ocr": "pdf_text_regex",
}
GRID_PROFILE_TYPES = {"csv_header", "pdf_table_header"}


@dataclass
class ProfileParseResult:
    outcome: ParseOutcome
    parse_method: str  # "profile_reuse" | "cold_detection"
    profile: BankProfile
    match_score: float | None


@dataclass
class _ReuseAttempt:
    outcome: ParseOutcome | None
    candidate: ProfileCandidate | None
    header_row_idx: int | None = None


def _cold_parse(detected_structure: str, file_bytes: bytes) -> ParseOutcome:
    if detected_structure == "clean_csv":
        return csv_parser.parse_csv(file_bytes)
    if detected_structure == "pdf_table":
        return pdf_table_parser.parse_pdf_table(file_bytes)
    if detected_structure == "pdf_text_no_table":
        lines = pdf_text_parser.extract_lines_from_pdf(file_bytes)
        return pdf_text_parser.parse_text_lines(lines)
    if detected_structure == "pdf_scan_ocr":
        return ocr_parser.parse_pdf_ocr(file_bytes, settings.ocr_min_confidence)
    raise ValueError(f"unknown detected_structure: {detected_structure}")


def _grid_for(detected_structure: str, file_bytes: bytes) -> list[list[str]] | None:
    if detected_structure == "clean_csv":
        return csv_parser.read_csv_grid(file_bytes)
    if detected_structure == "pdf_table":
        return pdf_table_parser.extract_largest_table(file_bytes)
    return None


def _resolve_roles_from_profile(
    header_cells: list[str], column_map_json: dict, threshold: float
) -> dict[str, int] | None:
    normalized_cells = [normalize_cell(c) for c in header_cells]
    roles: dict[str, int] = {}
    for role, stored_text in column_map_json.items():
        stored_norm = normalize_cell(str(stored_text))
        best_idx, best_score = None, 0.0
        for idx, cell in enumerate(normalized_cells):
            score = fuzz.WRatio(stored_norm, cell)
            if score > best_score:
                best_score, best_idx = score, idx
        if best_idx is not None and best_score >= threshold:
            roles[role] = best_idx

    if not all(role in roles for role in REQUIRED_ROLES):
        return None
    if "amount" not in roles and not ("debit" in roles and "credit" in roles):
        return None
    return roles


def _date_format_still_fits(
    grid: list[list[str]], header_row_idx: int, date_col: int, date_format: str
) -> bool:
    data_rows = grid[header_row_idx + 1 : header_row_idx + 1 + DTYPE_SAMPLE_SIZE]
    samples = [row[date_col] for row in data_rows if date_col < len(row) and row[date_col].strip()]
    if not samples:
        return False
    hits = sum(1 for s in samples if parse_date_with_format(s, date_format) is not None)
    return (hits / len(samples)) >= 0.8


async def _try_reuse_grid_profile(
    db: AsyncSession, profile_type: str, grid: list[list[str]], fuzzy_threshold: float
) -> _ReuseAttempt:
    best: tuple[int, ProfileCandidate] | None = None
    scan_limit = min(MAX_HEADER_SCAN_ROWS, max(len(grid) - 1, 0))
    for row_idx in range(scan_limit):
        fingerprint_text = normalize_fingerprint_text(grid[row_idx])
        if not fingerprint_text.strip("|"):
            continue
        candidate = await find_candidate_profile(
            db, profile_type, fingerprint_text, fuzzy_threshold
        )
        if candidate is not None and (best is None or candidate.match_score > best[1].match_score):
            best = (row_idx, candidate)

    if best is None:
        return _ReuseAttempt(outcome=None, candidate=None)

    header_row_idx, candidate = best
    roles = _resolve_roles_from_profile(
        grid[header_row_idx],
        candidate.profile.column_map_json,
        PROFILE_REVALIDATION_MATCH_THRESHOLD,
    )
    if roles is None:
        return _ReuseAttempt(outcome=None, candidate=candidate, header_row_idx=header_row_idx)

    date_format = candidate.profile.date_format
    if not _date_format_still_fits(grid, header_row_idx, roles["date"], date_format):
        return _ReuseAttempt(outcome=None, candidate=candidate, header_row_idx=header_row_idx)

    outcome = parse_rows_with_known_roles(grid, header_row_idx, roles, date_format)
    return _ReuseAttempt(outcome=outcome, candidate=candidate, header_row_idx=header_row_idx)


async def _upsert_profile(
    db: AsyncSession, profile_type: str, outcome: ParseOutcome
) -> BankProfile:
    fingerprint_hash = sha256_hex(outcome.header_fingerprint_text)
    existing = await db.scalar(
        select(BankProfile).where(
            BankProfile.structure_type == profile_type,
            BankProfile.header_fingerprint_hash == fingerprint_hash,
        )
    )

    if profile_type in GRID_PROFILE_TYPES:
        column_map_json = {
            role: outcome.header_cells[idx]
            for role, idx in outcome.column_map.items()
            if idx < len(outcome.header_cells)
        }
    else:
        column_map_json = outcome.column_map

    now = datetime.now(UTC)
    if existing is not None:
        existing.column_map_json = column_map_json
        existing.date_format = outcome.date_format
        existing.amount_sign_convention = outcome.amount_sign_convention
        existing.regex_pattern = outcome.regex_pattern
        existing.sample_lines_json = {"lines": outcome.sample_lines}
        existing.times_used += 1
        existing.last_used_at = now
        await db.commit()
        return existing

    profile = BankProfile(
        structure_type=profile_type,
        header_fingerprint_hash=fingerprint_hash,
        header_fingerprint_normalized=outcome.header_fingerprint_text,
        column_map_json=column_map_json,
        date_format=outcome.date_format,
        amount_sign_convention=outcome.amount_sign_convention,
        regex_pattern=outcome.regex_pattern,
        sample_lines_json={"lines": outcome.sample_lines},
        times_used=1,
        last_used_at=now,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


async def parse_statement_file(
    db: AsyncSession, detected_structure: str, file_bytes: bytes
) -> ProfileParseResult:
    """Tries the saved bank profile first, validates it still fits, and
    falls back to full cold detection otherwise — the adaptive-profile
    story. Bank profiles are global (no user scoping): only column-layout/
    date-format metadata is ever compared or stored here, never
    transaction data.

    For CSV/PDF-table statements, a matching profile lets us skip straight
    to known column roles + date format (genuine reuse, not just a label).
    For text/OCR statements, the regex parser is cheap enough that we parse
    first regardless and then classify the outcome as reuse-vs-cold by
    comparing its structural fingerprint against saved profiles — the
    metric is still honest, it just isn't a performance shortcut for this
    particular structure type.
    """
    profile_type = STRUCTURE_TO_PROFILE_TYPE[detected_structure]
    fuzzy_threshold = settings.bank_profile_fuzzy_match_threshold

    if profile_type in GRID_PROFILE_TYPES:
        grid = _grid_for(detected_structure, file_bytes)
        if grid:
            attempt = await _try_reuse_grid_profile(db, profile_type, grid, fuzzy_threshold)
            if attempt.outcome is not None and attempt.candidate is not None:
                attempt.candidate.profile.times_used += 1
                attempt.candidate.profile.last_used_at = datetime.now(UTC)
                await db.commit()
                return ProfileParseResult(
                    attempt.outcome,
                    "profile_reuse",
                    attempt.candidate.profile,
                    attempt.candidate.match_score,
                )
            if attempt.candidate is not None:
                attempt.candidate.profile.times_rejected += 1
                await db.commit()

        outcome = _cold_parse(detected_structure, file_bytes)
        profile = await _upsert_profile(db, profile_type, outcome)
        return ProfileParseResult(outcome, "cold_detection", profile, None)

    outcome = _cold_parse(detected_structure, file_bytes)
    candidate = await find_candidate_profile(
        db, profile_type, outcome.header_fingerprint_text, fuzzy_threshold
    )
    if candidate is not None:
        candidate.profile.times_used += 1
        candidate.profile.last_used_at = datetime.now(UTC)
        await db.commit()
        return ProfileParseResult(
            outcome, "profile_reuse", candidate.profile, candidate.match_score
        )

    profile = await _upsert_profile(db, profile_type, outcome)
    return ProfileParseResult(outcome, "cold_detection", profile, None)
