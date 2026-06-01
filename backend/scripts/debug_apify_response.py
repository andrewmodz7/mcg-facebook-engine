"""Diagnostic dump of the raw Apify response — no database writes.

All 100 posts from the last smoke test were skipped because facebook_post_id
extraction failed. This script calls the Apify actor directly (the same payload
scrape_group builds) and dumps the untouched response to disk so we can inspect
the actual field structure and fix the mapping.

Run from inside backend/:
    python -m scripts.debug_apify_response
"""

import asyncio
import json
import logging
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import select

from app.db import async_session
from app.models import TargetGroup
from app.scrapers.apify_client import run_actor_sync
from app.scrapers.config import APIFY_ACTOR_ID, POSTS_PER_RUN, SORT_ORDER

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
)

# backend/tmp/ — anchored to backend/ regardless of cwd.
TMP_DIR = Path(__file__).resolve().parent.parent / "tmp"
RAW_RESPONSE_PATH = TMP_DIR / "raw_apify_response.json"
SAMPLE_PATH = TMP_DIR / "sample_post.json"


async def main() -> None:
    # Pick the oldest active group — deterministic, matches the smoke test.
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

    # Same payload scrape_group would build.
    payload = {
        "startUrls": [{"url": group.url}],
        "resultsLimit": POSTS_PER_RUN,
        "viewOption": SORT_ORDER,
    }

    posts = await run_actor_sync(APIFY_ACTOR_ID, payload)

    # Dump everything before touching anything else, so inspection never
    # depends on parsing/insert success.
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    RAW_RESPONSE_PATH.write_text(
        json.dumps(posts, indent=2, ensure_ascii=False)
    )

    print(f"\nTotal posts returned: {len(posts)}")

    if posts:
        SAMPLE_PATH.write_text(
            json.dumps(posts[0], indent=2, ensure_ascii=False)
        )
        print(f"First post keys: {list(posts[0].keys())}")
        print(f"Sample (first post) written to: {SAMPLE_PATH}")
    else:
        print("Response was an empty array — no first post to sample.")

    print(f"Full raw response written to:  {RAW_RESPONSE_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
