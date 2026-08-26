from dataclasses import dataclass, field

from rapidfuzz import fuzz

from app.services.parsing.constants import (
    HEADER_SYNONYM_MATCH_THRESHOLD,
    REQUIRED_ROLES,
    ROLE_SYNONYMS,
)
from app.services.parsing.text_utils import looks_like_amount, looks_like_date, normalize_cell

# Roles whose values should look numeric/date-like; used to sanity-check a
# header-based assignment against the actual column contents.
_DTYPE_EXPECTATIONS = {
    "date": "date",
    "amount": "numeric",
    "debit": "numeric",
    "credit": "numeric",
    "balance": "numeric",
}

_CONTRADICTION_RATIO_FLOOR = 0.3


@dataclass
class ColumnRoleMap:
    roles: dict[str, int]
    header_cells: list[str]
    warnings: list[str] = field(default_factory=list)


def _dtype_ratio(values: list[str], kind: str) -> float | None:
    non_empty = [v for v in values if v and v.strip()]
    if not non_empty:
        return None
    check = looks_like_date if kind == "date" else looks_like_amount
    matches = sum(1 for v in non_empty if check(v))
    return matches / len(non_empty)


def classify_columns(header_cells: list[str], sample_rows: list[list[str]]) -> ColumnRoleMap | None:
    normalized_headers = [normalize_cell(h) for h in header_cells]

    scored: list[tuple[float, int, str]] = []
    for col_idx, header in enumerate(normalized_headers):
        if not header:
            continue
        for role, synonyms in ROLE_SYNONYMS.items():
            best = max(fuzz.WRatio(header, syn) for syn in synonyms)
            if best >= HEADER_SYNONYM_MATCH_THRESHOLD:
                scored.append((best, col_idx, role))

    scored.sort(key=lambda t: t[0], reverse=True)

    roles: dict[str, int] = {}
    used_columns: set[int] = set()
    for _score, col_idx, role in scored:
        if role in roles or col_idx in used_columns:
            continue
        roles[role] = col_idx
        used_columns.add(col_idx)

    warnings: list[str] = []
    for role, expected_kind in _DTYPE_EXPECTATIONS.items():
        col_idx = roles.get(role)
        if col_idx is None:
            continue
        values = [row[col_idx] for row in sample_rows if col_idx < len(row)]
        ratio = _dtype_ratio(values, expected_kind)
        if ratio is not None and ratio < _CONTRADICTION_RATIO_FLOOR:
            warnings.append(
                f"header matched '{role}' at column {col_idx} but values don't look "
                f"{expected_kind}-like ({ratio:.0%} matched) — unassigning"
            )
            del roles[role]
            used_columns.discard(col_idx)

    if not all(role in roles for role in REQUIRED_ROLES):
        return None
    if "amount" not in roles and not ("debit" in roles and "credit" in roles):
        return None

    return ColumnRoleMap(roles=roles, header_cells=header_cells, warnings=warnings)
