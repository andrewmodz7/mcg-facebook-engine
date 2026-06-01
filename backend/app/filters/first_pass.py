"""First-pass deterministic filter for raw_posts.

Kills only unambiguous garbage. Three rules, conservative by design:
1. rejected_empty: no text AND no link — nothing to score
2. rejected_url_only: empty text AND link is a bare URL with no commentary
3. rejected_too_short: stripped text < 30 chars AND no link to provide context

Anything else returns "passed" — the AI agent does all real judgment.
"""

import logging

from sqlalchemy import select, update

from app.db import async_session
from app.models import RawPost

logger = logging.getLogger(__name__)

# Constants — easy to tune later
MIN_TEXT_LENGTH = 30  # chars after stripping whitespace/punctuation/emoji


def _stripped_length(text: str) -> int:
    """Length of text after removing whitespace, punctuation, and emoji-like chars.

    Used to catch posts that are technically non-empty but have no real content
    (e.g. just '!!! ???' or '????'). Uses a permissive 'is alphanumeric' check
    per character; emoji and most punctuation get dropped, letters and digits
    in any language are preserved.
    """
    return sum(1 for c in (text or "") if c.isalnum())


def evaluate(post_text: str | None, link: str | None) -> tuple[str, str]:
    """Apply the three filter rules to a single post.

    Returns (filter_status, filter_reason) where:
    - filter_status: one of "passed", "rejected_empty", "rejected_url_only", "rejected_too_short"
    - filter_reason: short human-readable explanation
    """
    text = (post_text or "").strip()
    link_clean = (link or "").strip()

    # Rule 1: nothing to score
    if not text and not link_clean:
        return "rejected_empty", "post_text empty and link empty"

    # Rule 2: link only, no commentary
    if not text and link_clean:
        return "rejected_url_only", f"post_text empty, only link present: {link_clean[:80]}"

    # Rule 3: text too short and no link for context
    stripped_len = _stripped_length(text)
    if stripped_len < MIN_TEXT_LENGTH and not link_clean:
        return "rejected_too_short", f"stripped text length {stripped_len} below threshold {MIN_TEXT_LENGTH}, no link"

    return "passed", "passed all rules"


async def filter_pending_posts(batch_size: int = 500) -> dict:
    """Apply the filter to all raw_posts WHERE filter_status IS NULL.

    Processes in batches to avoid loading the whole table into memory.
    Returns a summary dict: {
        "total_evaluated": int,
        "passed": int,
        "rejected_empty": int,
        "rejected_url_only": int,
        "rejected_too_short": int,
    }
    """
    summary = {
        "total_evaluated": 0,
        "passed": 0,
        "rejected_empty": 0,
        "rejected_url_only": 0,
        "rejected_too_short": 0,
    }

    # link lives inside raw_json, not as a dedicated column — read it in Python.
    select_stmt = (
        select(RawPost.id, RawPost.post_text, RawPost.raw_json)
        .where(RawPost.filter_status.is_(None))
        .order_by(RawPost.scraped_at.asc())
        .limit(batch_size)
    )

    async with async_session() as session:
        while True:
            result = await session.execute(select_stmt)
            rows = result.all()
            if not rows:
                break

            # Each dict must include the PK ("id") plus the columns to set.
            # SQLAlchemy recognizes "id" as RawPost's primary key and emits an
            # UPDATE ... WHERE id=... per row, batched as executemany — the
            # canonical 2.0 "ORM bulk update by primary key" pattern.
            params = []
            for row in rows:
                raw_json = row.raw_json or {}
                link = raw_json.get("link")
                status, reason = evaluate(row.post_text, link)

                params.append(
                    {
                        "id": row.id,
                        "filter_status": status,
                        "filter_reason": reason,
                    }
                )
                summary["total_evaluated"] += 1
                summary[status] += 1

            if params:
                await session.execute(update(RawPost), params)
                await session.commit()

            logger.info(
                "Filtered batch of %d posts (total so far: %d)",
                len(rows),
                summary["total_evaluated"],
            )

            # A short final batch means the table is drained; avoid an extra
            # empty round-trip.
            if len(rows) < batch_size:
                break

    return summary
