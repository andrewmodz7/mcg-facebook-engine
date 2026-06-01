"""Manually run the AI scoring agent over filtered raw_posts.

Scores every post WHERE filter_status='passed' AND score_status IS NULL via
one Claude Opus 4.7 call each, promotes the leads into the leads table, and
prints a per-bucket summary plus a rough cost estimate.

Run from inside backend/:
    python -m scripts.run_scoring
"""

import asyncio
import logging

from dotenv import load_dotenv

from app.agents import score_pending_posts

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
)

# Rough Opus per-post estimate for the summary line. Not billing-accurate —
# just a sanity check on run cost.
COST_PER_POST_USD = 0.03


def _print_summary(summary: dict) -> None:
    """Print a fixed-width per-bucket table with a total and cost estimate."""
    rows = [
        ("is_lead", summary["is_lead"]),
        ("not_a_lead", summary["not_a_lead"]),
        ("errors", summary["errors"]),
    ]

    header = f"{'BUCKET':<22} {'COUNT':>8}"
    print()
    print(header)
    print("-" * len(header))

    for label, count in rows:
        print(f"{label:<22} {count:>8}")

    print("-" * len(header))
    print(f"{'TOTAL EVALUATED':<22} {summary['total_evaluated']:>8}")

    est_cost = summary["total_evaluated"] * COST_PER_POST_USD
    print()
    print(
        f"Estimated cost: ${est_cost:,.2f} "
        f"({summary['total_evaluated']} posts x ${COST_PER_POST_USD:.2f}/post, rough Opus estimate)"
    )


async def main() -> None:
    summary = await score_pending_posts()
    _print_summary(summary)


if __name__ == "__main__":
    asyncio.run(main())
