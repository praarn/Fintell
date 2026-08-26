"""Seeds merchant_lookup with a starter set of common merchants.

Run manually against the dev/demo database:
    uv run python scripts/seed_merchant_lookup.py

Idempotent — safe to run more than once, only inserts patterns that don't
already exist.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import async_session_factory  # noqa: E402
from app.services.categorization.seed import seed_merchant_lookup  # noqa: E402


async def main() -> None:
    async with async_session_factory() as db:
        inserted = await seed_merchant_lookup(db)
        print(f"Inserted {inserted} new merchant_lookup row(s).")


if __name__ == "__main__":
    asyncio.run(main())
