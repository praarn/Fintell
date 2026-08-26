from dataclasses import dataclass, field
from datetime import date as date_type
from decimal import Decimal

from app.services.parsing.text_utils import parse_amount

BALANCE_DELTA_TOLERANCE = Decimal("0.02")


@dataclass
class RowInputs:
    row_index: int
    debit_raw: str | None = None
    credit_raw: str | None = None
    amount_raw: str | None = None
    balance_raw: str | None = None
    sign_indicator_raw: str | None = None


@dataclass
class SignResult:
    convention: str
    signed_amounts: dict[int, Decimal]
    warnings: list[str] = field(default_factory=list)


def resolve_signs(
    roles: dict[str, int],
    rows: list[RowInputs],
    parsed_dates: dict[int, date_type],
) -> SignResult:
    """Resolves a canonical signed amount (positive=inflow, negative=outflow)
    per row, choosing among the conventions banks actually use. The result's
    `convention` string is exactly what gets persisted on the BankProfile so
    the same choice is reused (not re-derived) next time this layout is seen.
    """
    warnings: list[str] = []

    if "debit" in roles and "credit" in roles:
        signed: dict[int, Decimal] = {}
        for row in rows:
            debit = parse_amount(row.debit_raw) or Decimal("0")
            credit = parse_amount(row.credit_raw) or Decimal("0")
            if debit == 0 and credit == 0:
                continue
            signed[row.row_index] = credit - abs(debit)
        return SignResult("separate_debit_credit_columns", signed, warnings)

    # single "amount" column from here on.
    magnitudes: dict[int, Decimal] = {}
    raw_signed: dict[int, Decimal] = {}
    for row in rows:
        parsed = parse_amount(row.amount_raw)
        if parsed is None:
            continue
        raw_signed[row.row_index] = parsed
        magnitudes[row.row_index] = abs(parsed)

    if any(v < 0 for v in raw_signed.values()):
        return SignResult("debit_negative_single_column", dict(raw_signed), warnings)

    if "sign_indicator" in roles:
        signed = {}
        for row in rows:
            if row.row_index not in magnitudes:
                continue
            indicator = (row.sign_indicator_raw or "").strip().lower()
            magnitude = magnitudes[row.row_index]
            if any(tok in indicator for tok in ("cr", "credit", "deposit")):
                signed[row.row_index] = magnitude
            elif any(tok in indicator for tok in ("dr", "debit", "withdraw")):
                signed[row.row_index] = -magnitude
            else:
                signed[row.row_index] = -magnitude
                warnings.append(
                    f"row {row.row_index}: sign indicator '{indicator}' not recognized, "
                    "assumed debit"
                )
        return SignResult("single_column_sign_indicator", signed, warnings)

    if "balance" in roles:
        return _resolve_via_balance_delta(rows, magnitudes, parsed_dates, warnings)

    signed = {idx: -mag for idx, mag in magnitudes.items()}
    warnings.append(
        "single amount column with no sign, no debit/credit indicator, and no balance "
        "column to infer from — assumed all debit"
    )
    return SignResult("single_column_assume_debit", signed, warnings)


def _resolve_via_balance_delta(
    rows: list[RowInputs],
    magnitudes: dict[int, Decimal],
    parsed_dates: dict[int, date_type],
    warnings: list[str],
) -> SignResult:
    balances: dict[int, Decimal] = {}
    for row in rows:
        balance = parse_amount(row.balance_raw)
        if balance is not None:
            balances[row.row_index] = balance

    ordered = sorted(
        (idx for idx in magnitudes if idx in parsed_dates and idx in balances),
        key=lambda idx: (parsed_dates[idx], idx),
    )

    signed: dict[int, Decimal] = {}
    for position, idx in enumerate(ordered):
        if position == 0:
            continue
        prev_idx = ordered[position - 1]
        delta = balances[idx] - balances[prev_idx]
        magnitude = magnitudes[idx]
        if delta != 0 and abs(abs(delta) - magnitude) <= BALANCE_DELTA_TOLERANCE:
            signed[idx] = magnitude if delta > 0 else -magnitude

    unresolved_count = 0
    for idx, magnitude in magnitudes.items():
        if idx not in signed:
            signed[idx] = -magnitude
            unresolved_count += 1

    if unresolved_count:
        warnings.append(
            f"{unresolved_count} row(s) had no reliable balance delta to infer sign from — "
            "assumed debit for those rows"
        )

    return SignResult("single_column_balance_inferred", signed, warnings)
