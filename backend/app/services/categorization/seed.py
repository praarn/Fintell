from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.merchant_lookup import MerchantLookup
from app.services.categorization.constants import MATCH_TYPE_SEED
from app.services.categorization.merchant_cleaner import clean_merchant_string
from app.services.categorization.seed_data import SEED_MERCHANTS


async def seed_merchant_lookup(db: AsyncSession) -> int:
    """Idempotent: only inserts patterns that don't already exist. Returns
    the number of rows actually inserted."""
    existing_patterns = set((await db.scalars(select(MerchantLookup.raw_pattern))).all())

    inserted = 0
    for display_name, category in SEED_MERCHANTS:
        pattern = clean_merchant_string(display_name)
        if not pattern or pattern in existing_patterns:
            continue
        db.add(
            MerchantLookup(
                raw_pattern=pattern,
                normalized_name=display_name,
                category=category,
                match_type=MATCH_TYPE_SEED,
            )
        )
        existing_patterns.add(pattern)
        inserted += 1

    await db.commit()
    return inserted
