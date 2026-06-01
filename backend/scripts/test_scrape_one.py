"""One-off smoke test: scrape a single group end-to-end.

Proves the full pipeline (Apify call -> map -> dedupe -> insert) works before
running across all 14 groups. Picks the oldest active group deterministically,
scrapes it, prints the summary, and dumps the raw Apify JSON of that group's
most recently scraped post to backend/tmp/sample_post.json for inspection.

Run from inside backend/:
    python -m scripts.test_scrape_one
"""

import asyncio
import json
import logging
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import select

from app.db import async_session
from app.models import RawPost, TargetGroup
from app.scrapers import scrape_group

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
)

# backend/tmp/sample_post.json — anchored to backend/ regardless of cwd.
TMP_DIR = Path(__file__).resolve().parent.parent / "tmp"
SAMPLE_PATH = TMP_DIR / "sample_post.json"


async def main() -> None:
    # Pick the oldest active group — deterministic across runs.
    async with async_session() as session:
        group = await session.scalar(
            select(TargetGroup)
            .where(TargetGroup.is_active.is_(True))
            .order_by(TargetGroup.created_at.asc())
            .limit(1)
        )

    if group is None:
        print("No active target groups found. Seed the table first:")
        print("    python -m scripts.seed_target_groups")
        return

    print(f"Scraping oldest active group: {group.name} ({group.facebook_id})")

    summary = await scrape_group(group)
    print("\nSummary:")
    print(json.dumps(summary, indent=2))

    # Dump the raw Apify payload of the most recently scraped post for review.
    async with async_session() as session:
        sample_post = await session.scalar(
            select(RawPost)
            .where(RawPost.group_id == group.id)
            .order_by(RawPost.scraped_at.desc())
            .limit(1)
        )

    if sample_post is None:
        print(
            "\nNo raw_posts found for this group, so no sample was dumped."
        )
        return

    TMP_DIR.mkdir(parents=True, exist_ok=True)
    SAMPLE_PATH.write_text(
        json.dumps(sample_post.raw_json, indent=2, ensure_ascii=False)
    )
    print(f"\nSample post raw_json written to: {SAMPLE_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
