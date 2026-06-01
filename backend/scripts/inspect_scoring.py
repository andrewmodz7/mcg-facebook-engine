"""Inspect the scoring agent's output — pure dry-run, read-only.

Prints two sections for eyeballing a scoring run:
  1. LEADS, sorted by urgency_score DESC, with angle and reasoning.
  2. A random sample of 5 not-a-lead decisions, with the rejection reasoning.

No DB writes, no API calls.

Run from inside backend/:
    python -m scripts.inspect_scoring
"""

import asyncio
import logging

from dotenv import load_dotenv
from sqlalchemy import func, select

from app.db import async_session
from app.models import Lead, RawPost

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
)

SEP = "-----"


def _truncate(text: str | None, limit: int) -> str:
    text = text or ""
    return text[:limit] + ("..." if len(text) > limit else "")


async def _print_leads() -> None:
    print("=" * 72)
    print("SECTION 1: LEADS (sorted by urgency_score DESC)")
    print("=" * 72)

    async with async_session() as session:
        stmt = (
            select(Lead, RawPost)
            .join(RawPost, Lead.raw_post_id == RawPost.id)
            .order_by(Lead.urgency_score.desc())
        )
        result = await session.execute(stmt)
        rows = result.all()

    if not rows:
        print("(no leads)")
        print()
        return

    for i, (lead, post) in enumerate(rows, start=1):
        print(f"#{i} — Score {lead.urgency_score} — {lead.lead_type}")
        print(f"Author: {post.author_name or '<unknown>'}")
        print(f"Post URL: {post.post_url}")
        print(f"Post text: {_truncate(post.post_text, 400)}")
        print(f"Angle: {lead.angle or ''}")
        print(f"Reasoning: {lead.reasoning or ''}")
        print(SEP)

    print()


async def _print_not_a_lead_sample() -> None:
    print("=" * 72)
    print("SECTION 2: RANDOM NOT-A-LEAD DECISIONS (sample of 5)")
    print("=" * 72)

    async with async_session() as session:
        stmt = (
            select(RawPost)
            .where(RawPost.score_status == "scored_not_a_lead")
            .order_by(func.random())
            .limit(5)
        )
        result = await session.execute(stmt)
        posts = result.scalars().all()

    if not posts:
        print("(no not-a-lead decisions)")
        print()
        return

    for post in posts:
        print(f"Author: {post.author_name or '<unknown>'}")
        print(f"Post text: {_truncate(post.post_text, 400)}")
        print(f"Reasoning (why not a lead): {post.score_reasoning or ''}")
        print(SEP)

    print()


async def main() -> None:
    await _print_leads()
    await _print_not_a_lead_sample()


if __name__ == "__main__":
    asyncio.run(main())
