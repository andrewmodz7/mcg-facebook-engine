"""Manually run the first-pass deterministic filter over pending raw_posts.

Applies the filter to every row WHERE filter_status IS NULL, stamping each
with a filter_status and filter_reason, then prints a per-bucket summary table.

Run from inside backend/:
    python -m scripts.run_filter
"""

import asyncio
import logging

from dotenv import load_dotenv

from app.filters import filter_pending_posts

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
)


def _print_summary(summary: dict) -> None:
    """Print a fixed-width per-bucket table with a total line."""
    rows = [
        ("passed", summary["passed"]),
        ("rejected_empty", summary["rejected_empty"]),
        ("rejected_url_only", summary["rejected_url_only"]),
        ("rejected_too_short", summary["rejected_too_short"]),
    ]

    header = f"{'BUCKET':<22} {'COUNT':>8}"
    print()
    print(header)
    print("-" * len(header))

    for label, count in rows:
        print(f"{label:<22} {count:>8}")

    print("-" * len(header))
    print(f"{'TOTAL EVALUATED':<22} {summary['total_evaluated']:>8}")


async def main() -> None:
    summary = await filter_pending_posts()
    _print_summary(summary)


if __name__ == "__main__":
    asyncio.run(main())
