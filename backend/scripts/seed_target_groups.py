"""Seed the target_groups table with the Facebook groups we scrape.

Idempotent: inserts groups that don't yet exist (keyed on facebook_id) and
skips any that are already present. Safe to run repeatedly.

Run from inside backend/:
    python -m scripts.seed_target_groups
"""

import asyncio

from dotenv import load_dotenv
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.db import async_session
from app.models import TargetGroup

load_dotenv()

SEED_GROUPS = [
    {"facebook_id": "289807992071085", "name": "Chicago RE Group 1", "url": "https://www.facebook.com/groups/289807992071085/"},
    {"facebook_id": "877895048955117", "name": "Chicago RE Group 2", "url": "https://www.facebook.com/groups/877895048955117/"},
    {"facebook_id": "chicagoreinetwork", "name": "Chicago REI Network", "url": "https://www.facebook.com/groups/chicagoreinetwork/"},
    {"facebook_id": "1482994858475918", "name": "Chicago RE Group 3", "url": "https://www.facebook.com/groups/1482994858475918/"},
    {"facebook_id": "chicago.illinois.real.estate.investing", "name": "Chicago Illinois Real Estate Investing", "url": "https://www.facebook.com/groups/chicago.illinois.real.estate.investing/"},
    {"facebook_id": "1557850617724794", "name": "Chicago RE Group 4", "url": "https://www.facebook.com/groups/1557850617724794/"},
    {"facebook_id": "724140937130539", "name": "Chicago RE Group 5", "url": "https://www.facebook.com/groups/724140937130539/"},
    {"facebook_id": "425844688698610", "name": "Chicago RE Group 6", "url": "https://www.facebook.com/groups/425844688698610/"},
    {"facebook_id": "Manufacturedhomes", "name": "Manufactured Homes", "url": "https://www.facebook.com/groups/Manufacturedhomes/"},
    {"facebook_id": "1756127461810445", "name": "Chicago RE Group 7", "url": "https://www.facebook.com/groups/1756127461810445/"},
    {"facebook_id": "324309955413033", "name": "Chicago RE Group 8", "url": "https://www.facebook.com/groups/324309955413033/"},
    {"facebook_id": "3028362000721594", "name": "Chicago Trade Contractors", "url": "https://www.facebook.com/groups/3028362000721594/"},
    {"facebook_id": "3873133236339166", "name": "Chicago RE Group 9", "url": "https://www.facebook.com/groups/3873133236339166/"},
    {"facebook_id": "470730068060176", "name": "Chicago RE Group 10", "url": "https://www.facebook.com/groups/470730068060176/"},
]


async def main() -> None:
    inserted = 0
    skipped = 0

    async with async_session() as session:
        for group in SEED_GROUPS:
            stmt = (
                insert(TargetGroup)
                .values(**group)
                .on_conflict_do_nothing(index_elements=["facebook_id"])
                .returning(TargetGroup.id)
            )
            result = await session.execute(stmt)
            if result.scalar_one_or_none() is not None:
                inserted += 1
            else:
                skipped += 1

        await session.commit()

        active_count = await session.scalar(
            select(func.count())
            .select_from(TargetGroup)
            .where(TargetGroup.is_active.is_(True))
        )

    print(f"Inserted: {inserted}")
    print(f"Already existed: {skipped}")
    print(f"Active groups in table: {active_count}")


if __name__ == "__main__":
    asyncio.run(main())
