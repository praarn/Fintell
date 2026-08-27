"""Seed a demo user with a realistic, multi-bank synthetic history so a
fresh clone is immediately demoable.

    uv run python scripts/seed_demo.py            # create / top up
    uv run python scripts/seed_demo.py --reset    # wipe the demo user first

Everything generated here is synthetic. No real bank, person, or
transaction is represented. Statements are pushed through the *real*
upload+parse+categorize pipeline, so the demo also exercises bank-profile
reuse (each bank's second statement reuses the profile learned from its
first) and the Tier 1/2/3 categorization path.
"""

import argparse
import asyncio
import csv
import io
import random
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, select  # noqa: E402

from app.core.database import async_session_factory  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services import statement_service  # noqa: E402
from app.services.auth_service import register_user  # noqa: E402
from app.services.categorization.seed import seed_merchant_lookup  # noqa: E402

DEMO_EMAIL = "demo@fintell.app"
DEMO_PASSWORD = "demo-password-123"

# Recurring monthly spend pattern, shared across banks (merchant, category-ish
# label only for our own readability, typical amount range).
_RECURRING = [
    ("Whole Foods Market", (55, 95)),
    ("Trader Joes", (30, 60)),
    ("Costco Wholesale", (90, 180)),
    ("Starbucks", (4, 9)),
    ("Chipotle Mexican Grill", (11, 18)),
    ("Olive Garden", (28, 52)),
    ("DoorDash", (22, 41)),
    ("Uber", (8, 26)),
    ("Metro Transit", (2, 3)),
    ("Pge", (80, 160)),
    ("Comcast", (70, 90)),
    ("Verizon", (60, 85)),
    ("Netflix", (16, 16)),
    ("Spotify", (11, 11)),
    ("Amazon", (18, 120)),
    ("Target", (25, 90)),
    ("Planet Fitness", (10, 10)),
    ("Cvs Pharmacy", (8, 34)),
]

_SALARY = ("Salary Deposit Acme Corp", Decimal("4200.00"))


def _month_starts(n_months: int, end: date) -> list[date]:
    starts = []
    cursor = end.replace(day=1)
    for _ in range(n_months):
        starts.append(cursor)
        # step back one month
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    return list(reversed(starts))


def _generate_rows(month_starts: list[date], rng: random.Random, *, inject_anomaly: bool):
    """(date, description, signed Decimal amount) tuples for a run of months."""
    rows: list[tuple[date, str, Decimal]] = []
    for i, ms in enumerate(month_starts):
        rows.append((ms.replace(day=1), _SALARY[0], _SALARY[1]))
        for merchant, (lo, hi) in _RECURRING:
            hits = 1 if hi < 20 else rng.choice((1, 1, 2))
            for _ in range(hits):
                day = rng.randint(2, 27)
                amt = Decimal(str(-round(rng.uniform(lo, hi), 2)))
                rows.append((ms.replace(day=day), merchant, amt))
        # one anomalous charge in the middle month of the range
        if inject_anomaly and i == len(month_starts) // 2:
            rows.append((ms.replace(day=14), "Whole Foods Market", Decimal("-1180.00")))
            rows.append((ms.replace(day=19), "Anteros Air Charter", Decimal("-320.00")))
    rows.sort(key=lambda r: r[0])
    return rows


def _csv_clean_standard(rows) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Date", "Description", "Amount"])
    for d, desc, amt in rows:
        w.writerow([d.strftime("%m/%d/%Y"), desc, f"{amt:.2f}"])
    return buf.getvalue().encode()


def _csv_debit_credit_columns(rows) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Value Date", "Narration", "Withdrawal Amt", "Deposit Amt"])
    for d, desc, amt in rows:
        withdrawal = f"{-amt:.2f}" if amt < 0 else ""
        deposit = f"{amt:.2f}" if amt > 0 else ""
        w.writerow([d.strftime("%d-%m-%Y"), desc, withdrawal, deposit])
    return buf.getvalue().encode()


def _csv_reordered_positive_debit(rows) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Particulars", "Type", "Amt", "Txn Date"])
    for d, desc, amt in rows:
        w.writerow([desc, "DR" if amt < 0 else "CR", f"{abs(amt):.2f}", d.strftime("%m/%d/%Y")])
    return buf.getvalue().encode()


# (bank hint, layout builder). Each bank gets two statements so the second
# upload reuses the profile learned from the first.
_BANKS = [
    ("Northwind Checking", _csv_clean_standard),
    ("Acme Rewards Card", _csv_debit_credit_columns),
    ("Vanguard Savings", _csv_reordered_positive_debit),
]


async def _wipe_demo_user(db) -> None:
    user = await db.scalar(select(User).where(User.email == DEMO_EMAIL))
    if user is None:
        return
    # statements cascade to transactions/splits/anomaly flags; also clear the
    # per-user logs that don't cascade from users automatically in dev.
    for stmt in await statement_service.list_statements(db, user.id):
        await statement_service.delete_statement(db, user.id, stmt.id)
    await db.execute(delete(User).where(User.id == user.id))
    await db.commit()
    print(f"Wiped existing demo user {DEMO_EMAIL}.")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="wipe the demo user first")
    args = parser.parse_args()

    rng = random.Random(20260827)

    async with async_session_factory() as db:
        await seed_merchant_lookup(db)

        if args.reset:
            await _wipe_demo_user(db)

        existing = await db.scalar(select(User).where(User.email == DEMO_EMAIL))
        if existing is not None:
            print(
                f"Demo user {DEMO_EMAIL} already exists — pass --reset to rebuild. "
                "Nothing to do."
            )
            return

        user = await register_user(db, DEMO_EMAIL, DEMO_PASSWORD)
        print(f"Created demo user {DEMO_EMAIL} / {DEMO_PASSWORD}")

        today = date.today()
        halves = [
            _month_starts(6, end=today)[:3],
            _month_starts(6, end=today)[3:],
        ]

        for bank_hint, build in _BANKS:
            for half_idx, months in enumerate(halves):
                rows = _generate_rows(months, rng, inject_anomaly=(half_idx == 1))
                data = build(rows)
                statement = await statement_service.upload_and_parse_statement(
                    db,
                    user.id,
                    original_filename=f"{bank_hint.lower().replace(' ', '_')}_{half_idx + 1}.csv",
                    file_bytes=data,
                    bank_hint=bank_hint,
                )
                print(
                    f"  {bank_hint} #{half_idx + 1}: "
                    f"{statement.row_count_parsed}/{statement.row_count_total} rows parsed "
                    f"via {statement.parse_method}"
                )

    print("\nDone. Log in as the demo user to explore.")


if __name__ == "__main__":
    asyncio.run(main())
