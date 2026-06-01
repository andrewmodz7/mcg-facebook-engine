"""Manually trigger a full Facebook Groups scrape run.

Scrapes every active target group via Apify, inserts new raw_posts, and prints
a per-group summary table plus a grand-total line.

Run from inside backend/:
    python -m scripts.run_scraper
"""

import asyncio
import logging

from dotenv import load_dotenv

from app.scrapers import scrape_all_active_groups

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
)


def _print_summary(summaries: list[dict]) -> None:
    """Print a fixed-width per-group table and a grand-total line."""
    header = (
        f"{'GROUP':<22} {'RETURNED':>8} {'INSERTED':>8} "
        f"{'SKIPPED':>8}  ERROR"
    )
    print()
    print(header)
    print("-" * len(header))

    total_returned = 0
    total_inserted = 0
    total_skipped = 0
    error_count = 0

    for s in summaries:
        total_returned += s["posts_returned"]
        total_inserted += s["posts_inserted"]
        total_skipped += s["posts_skipped"]
        if s["error"]:
            error_count += 1

        name = s["facebook_id"]
        error = s["error"] or ""
        print(
            f"{name:<22.22} {s['posts_returned']:>8} "
            f"{s['posts_inserted']:>8} {s['posts_skipped']:>8}  {error}"
        )

    print("-" * len(header))
    print(
        f"{'TOTAL (' + str(len(summaries)) + ' groups)':<22} "
        f"{total_returned:>8} {total_inserted:>8} {total_skipped:>8}  "
        f"{error_count} error(s)"
    )


async def main() -> None:
    summaries = await scrape_all_active_groups()
    _print_summary(summaries)


if __name__ == "__main__":
    asyncio.run(main())
