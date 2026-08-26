from datetime import date as date_type

from app.services.parsing.column_classifier import ColumnRoleMap, classify_columns
from app.services.parsing.constants import (
    DTYPE_SAMPLE_SIZE,
    MAX_HEADER_SCAN_ROWS,
    REASON_AMBIGUOUS_SIGN_CONVENTION,
    REASON_MALFORMED_ROW,
    REASON_NO_REQUIRED_COLUMNS_RESOLVED,
    REASON_UNPARSEABLE_AMOUNT,
    REASON_UNPARSEABLE_DATE,
)
from app.services.parsing.sign_convention import RowInputs, resolve_signs
from app.services.parsing.text_utils import (
    detect_date_format,
    normalize_fingerprint_text,
    parse_amount,
    parse_date_with_format,
)
from app.services.parsing.types import (
    ParsedRow,
    ParseOutcome,
    RowFailure,
    UnresolvableStructureError,
)


def _find_header_row(grid: list[list[str]]) -> tuple[int, ColumnRoleMap] | None:
    scan_limit = min(MAX_HEADER_SCAN_ROWS, max(len(grid) - 1, 0))
    for row_idx in range(scan_limit):
        sample_rows = grid[row_idx + 1 : row_idx + 1 + DTYPE_SAMPLE_SIZE]
        role_map = classify_columns(grid[row_idx], sample_rows)
        if role_map is not None:
            return row_idx, role_map
    return None


def _cell(row: list[str], col_idx: int | None) -> str | None:
    if col_idx is None or col_idx >= len(row):
        return None
    return row[col_idx]


def detect_date_format_for_column(
    grid: list[list[str]], header_row_idx: int, date_col: int
) -> str | None:
    data_rows = grid[header_row_idx + 1 :]
    date_samples = [row[date_col] for row in data_rows[:DTYPE_SAMPLE_SIZE] if date_col < len(row)]
    return detect_date_format(date_samples)


def parse_rows_with_known_roles(
    grid: list[list[str]],
    header_row_idx: int,
    roles: dict[str, int],
    date_format: str,
    column_warnings: list[str] | None = None,
) -> ParseOutcome:
    """Row-parsing shared by cold detection and profile-driven reuse: given
    an already-resolved header row position, role→column mapping, and date
    format, parses every data row. Never re-derives roles/date-format
    itself — callers are responsible for having validated those first.
    """
    data_rows = grid[header_row_idx + 1 :]
    date_col = roles["date"]
    desc_col = roles["description"]

    failures: list[RowFailure] = []
    parsed_dates: dict[int, date_type] = {}
    row_inputs: list[RowInputs] = []

    for offset, row in enumerate(data_rows):
        row_index = header_row_idx + 1 + offset
        raw_line_text = ",".join(row)

        required_cols = [
            date_col,
            desc_col,
            roles.get("amount"),
            roles.get("debit"),
            roles.get("credit"),
        ]
        if any(c is not None and c >= len(row) for c in required_cols):
            failures.append(
                RowFailure(
                    row_index=row_index,
                    raw_line_text=raw_line_text,
                    reason_code=REASON_MALFORMED_ROW,
                    reason="row has fewer columns than the detected header",
                )
            )
            continue

        date_raw = _cell(row, date_col) or ""
        parsed_date = parse_date_with_format(date_raw, date_format)
        if parsed_date is None:
            failures.append(
                RowFailure(
                    row_index=row_index,
                    raw_line_text=raw_line_text,
                    reason_code=REASON_UNPARSEABLE_DATE,
                    reason=f"could not parse '{date_raw}' as {date_format}",
                )
            )
            continue
        parsed_dates[row_index] = parsed_date

        row_inputs.append(
            RowInputs(
                row_index=row_index,
                debit_raw=_cell(row, roles.get("debit")),
                credit_raw=_cell(row, roles.get("credit")),
                amount_raw=_cell(row, roles.get("amount")),
                balance_raw=_cell(row, roles.get("balance")),
                sign_indicator_raw=_cell(row, roles.get("sign_indicator")),
            )
        )

    sign_result = resolve_signs(roles, row_inputs, parsed_dates)

    rows: list[ParsedRow] = []
    raw_by_index = {header_row_idx + 1 + offset: row for offset, row in enumerate(data_rows)}
    for row_input in row_inputs:
        idx = row_input.row_index
        row = raw_by_index[idx]
        raw_line_text = ",".join(row)
        if idx not in sign_result.signed_amounts:
            failures.append(
                RowFailure(
                    row_index=idx,
                    raw_line_text=raw_line_text,
                    reason_code=REASON_UNPARSEABLE_AMOUNT,
                    reason="could not resolve a transaction amount for this row",
                )
            )
            continue

        balance_col = roles.get("balance")
        running_balance = None
        if balance_col is not None:
            running_balance = parse_amount(_cell(row, balance_col))

        rows.append(
            ParsedRow(
                row_index=idx,
                date=parsed_dates[idx],
                description=(_cell(row, desc_col) or "").strip(),
                amount=sign_result.signed_amounts[idx],
                raw_line_text=raw_line_text,
                running_balance=running_balance,
            )
        )

    warnings = list(column_warnings or []) + list(sign_result.warnings)
    if sign_result.convention == "single_column_assume_debit":
        failures.append(
            RowFailure(
                row_index=None,
                raw_line_text="",
                reason_code=REASON_AMBIGUOUS_SIGN_CONVENTION,
                reason=sign_result.warnings[-1]
                if sign_result.warnings
                else "amount sign convention could not be determined; assumed all-debit",
            )
        )

    return ParseOutcome(
        rows=rows,
        failures=failures,
        column_map=roles,
        date_format=date_format,
        amount_sign_convention=sign_result.convention,
        header_fingerprint_text=normalize_fingerprint_text(grid[header_row_idx]),
        header_cells=grid[header_row_idx],
        warnings=warnings,
        sample_lines=[",".join(r) for r in grid[header_row_idx : header_row_idx + 4]],
    )


def parse_grid(grid: list[list[str]]) -> ParseOutcome:
    """Cold-detection entry point: finds the header row, classifies columns,
    and detects the date format from scratch, then delegates row-parsing to
    `parse_rows_with_known_roles`. Used for CSV and pdfplumber-extracted PDF
    tables alike — both reduce to the same raw string grid.
    """
    if len(grid) < 2:
        raise UnresolvableStructureError(
            REASON_NO_REQUIRED_COLUMNS_RESOLVED, "fewer than 2 rows in the extracted grid"
        )

    found = _find_header_row(grid)
    if found is None:
        raise UnresolvableStructureError(
            REASON_NO_REQUIRED_COLUMNS_RESOLVED,
            "Could not resolve required columns (date/description/amount, or "
            "debit+credit) from any candidate header row in the first "
            f"{MAX_HEADER_SCAN_ROWS} rows",
        )
    header_row_idx, role_map = found
    roles = role_map.roles

    date_format = detect_date_format_for_column(grid, header_row_idx, roles["date"])
    if date_format is None:
        raise UnresolvableStructureError(
            REASON_NO_REQUIRED_COLUMNS_RESOLVED,
            "Date column resolved but no consistent date format could be detected",
        )

    return parse_rows_with_known_roles(
        grid, header_row_idx, roles, date_format, column_warnings=role_map.warnings
    )
