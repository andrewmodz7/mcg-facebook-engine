"""Single-post smoke test for the scoring agent.

Scores ONE real post from the DB and prints the full Opus response without
writing anything back. Proves the full chain (env -> API call -> JSON parse ->
output shape) before committing to scoring all pending posts.

Pure dry-run: no DB writes. Costs roughly one Opus call (~$0.05).

Run from inside backend/:
    python -m scripts.test_score_one
    python -m scripts.test_score_one --facebook-post-id 27097826336535297
"""

import argparse
import asyncio
import json
import logging
import os

from anthropic import AsyncAnthropic
from dotenv import load_dotenv
from sqlalchemy import select

from app.agents.scoring_agent import score_post
from app.db import async_session
from app.models import RawPost, TargetGroup

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Score a single post as a dry-run smoke test."
    )
    parser.add_argument(
        "--facebook-post-id",
        dest="facebook_post_id",
        default=None,
        help=(
            "Score this specific post by facebook_post_id. "
            "If omitted, scores the most recently scraped pending post."
        ),
    )
    return parser.parse_args()


async def main() -> None:
    args = _parse_args()

    # Fetch one post (and its group name) ready for scoring.
    async with async_session() as session:
        stmt = (
            select(RawPost, TargetGroup.name)
            .join(TargetGroup, RawPost.group_id == TargetGroup.id)
            .where(RawPost.filter_status == "passed")
            .where(RawPost.score_status.is_(None))
        )
        if args.facebook_post_id:
            stmt = stmt.where(
                RawPost.facebook_post_id == args.facebook_post_id
            )
        else:
            stmt = stmt.order_by(RawPost.scraped_at.desc())

        stmt = stmt.limit(1)
        result = await session.execute(stmt)
        row = result.first()

    if row is None:
        if args.facebook_post_id:
            print(
                f"No pending post found with facebook_post_id="
                f"{args.facebook_post_id} (filter_status='passed' AND "
                f"score_status IS NULL)."
            )
        else:
            print(
                "No pending posts found "
                "(filter_status='passed' AND score_status IS NULL)."
            )
        return

    post, group_name = row

    # Show what's about to be scored.
    print()
    print("=" * 72)
    print("ABOUT TO SCORE (dry run)")
    print("=" * 72)
    print(f"Group:      {group_name or '<unknown>'}")
    print(f"Author:     {post.author_name or '<unknown>'}")
    print(f"Post ID:    {post.facebook_post_id}")
    print(
        f"Engagement: {post.reactions_count or 0} reactions | "
        f"{post.comments_count or 0} comments"
    )
    posted_at = post.posted_at.isoformat() if post.posted_at else None
    print(f"Posted:     {posted_at or '<unknown>'}")
    print("-" * 72)
    text = post.post_text or ""
    truncated = text[:300] + ("..." if len(text) > 300 else "")
    print(truncated)
    print("=" * 72)

    # Call the agent.
    client = AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    result_dict = await score_post(
        post_text=post.post_text,
        author_name=post.author_name,
        group_name=group_name,
        posted_at=posted_at,
        reactions_count=post.reactions_count or 0,
        comments_count=post.comments_count or 0,
        client=client,
    )

    print()
    print("AGENT RESPONSE")
    print("-" * 72)
    print(json.dumps(result_dict, indent=2, ensure_ascii=False))
    print("-" * 72)

    print()
    print(
        "DRY RUN — no DB writes made. Review the output above. If it looks "
        "right, run python -m scripts.run_scoring to score all pending posts."
    )


if __name__ == "__main__":
    asyncio.run(main())
