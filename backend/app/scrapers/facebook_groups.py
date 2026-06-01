"""Facebook Groups scraper orchestration.

For each active target group, calls the Apify Facebook Groups actor, maps the
returned posts onto the ``raw_posts`` schema, dedupes against rows already in
the database (keyed on ``facebook_post_id``), and inserts the new ones.

Public entry points:
- ``scrape_group(group)`` — scrape a single group and return a summary dict.
- ``scrape_all_active_groups()`` — scrape every active group sequentially.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from app.db import async_session
from app.models import RawPost, TargetGroup
from app.scrapers.apify_client import run_actor_sync
from app.scrapers.config import APIFY_ACTOR_ID, POSTS_PER_RUN, SORT_ORDER

logger = logging.getLogger(__name__)


def _parse_posted_at(value: object) -> Optional[datetime]:
    """Parse an Apify timestamp into a timezone-aware datetime, or None.

    Apify versions return either an ISO-8601 string (sometimes ``Z``-suffixed)
    or a Unix epoch number. Anything unparseable yields None.
    """
    if value is None:
        return None

    # Numeric epoch seconds.
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)

    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        # ISO-8601, normalizing a trailing Z to an explicit UTC offset.
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            pass
        # Epoch seconds encoded as a string.
        try:
            return datetime.fromtimestamp(float(s), tz=timezone.utc)
        except (ValueError, OverflowError):
            return None

    return None


def _map_post(post: dict, group_id: object) -> Optional[dict]:
    """Map one Apify post object onto a ``raw_posts`` insert dict.

    Returns None (and logs a warning) for posts that should be skipped:
    a missing ``facebook_post_id`` or a missing ``post_url``. Empty post text
    is allowed — image-only posts sometimes return an empty caption.
    """
    # ``legacyId`` is the clean numeric post ID; ``id`` is the opaque fallback.
    facebook_post_id = post.get("legacyId") or post.get("id")
    if not facebook_post_id:
        logger.warning(
            "Skipping post with no resolvable facebook_post_id: %r",
            post.get("url"),
        )
        return None

    post_url = post.get("url")
    if not post_url:
        logger.warning("Skipping post %s with no url", facebook_post_id)
        return None

    user = post.get("user") or {}
    user_id = user.get("id")
    author_profile_url = (
        f"https://www.facebook.com/{user_id}" if user_id else None
    )

    return {
        "group_id": group_id,
        "facebook_post_id": facebook_post_id,
        "author_name": user.get("name"),
        "author_profile_url": author_profile_url,
        "author_facebook_id": user_id,
        "post_text": post.get("text") or "",
        "post_url": post_url,
        "posted_at": _parse_posted_at(post.get("time")),
        "reactions_count": post.get("topReactionsCount")
        or post.get("likesCount")
        or 0,
        "comments_count": post.get("commentsCount") or 0,
        "raw_json": post,
    }


async def scrape_group(group: TargetGroup) -> dict:
    """Scrape one group, dedupe, and insert new raw_posts.

    On success, also stamps ``last_scraped_at``. On any error, captures the
    message in the returned summary and leaves ``last_scraped_at`` untouched.
    """
    summary: dict = {
        "group_id": str(group.id),
        "facebook_id": group.facebook_id,
        "posts_returned": 0,
        "posts_inserted": 0,
        "posts_skipped": 0,
        "error": None,
    }

    payload = {
        "startUrls": [{"url": group.url}],
        "resultsLimit": POSTS_PER_RUN,
        # The actor's sort-order field is "viewOption". If a future actor
        # version renames it the run still returns posts (unknown fields are
        # ignored), so this is best-effort rather than required.
        "viewOption": SORT_ORDER,
    }

    try:
        posts = await run_actor_sync(APIFY_ACTOR_ID, payload)
        summary["posts_returned"] = len(posts)

        # The actor reports the real group title; use it to self-heal the
        # generic placeholder names we seeded with.
        group_title = posts[0].get("groupTitle") if posts else None

        inserted = 0
        skipped = 0

        async with async_session() as session:
            for post in posts:
                values = _map_post(post, group.id)
                if values is None:
                    skipped += 1
                    continue

                stmt = (
                    insert(RawPost)
                    .values(**values)
                    .on_conflict_do_nothing(
                        index_elements=["facebook_post_id"]
                    )
                    .returning(RawPost.id)
                )
                result = await session.execute(stmt)
                if result.scalar_one_or_none() is not None:
                    inserted += 1
                else:
                    skipped += 1

            # Stamp last_scraped_at only on a successful run, and refresh the
            # group name from the actor's reported title when we have one.
            group_values: dict = {"last_scraped_at": datetime.now(timezone.utc)}
            if group_title:
                group_values["name"] = group_title
            await session.execute(
                update(TargetGroup)
                .where(TargetGroup.id == group.id)
                .values(**group_values)
            )
            await session.commit()

        summary["posts_inserted"] = inserted
        summary["posts_skipped"] = skipped

    except Exception as exc:  # noqa: BLE001 — isolate one group's failure
        logger.exception(
            "Failed to scrape group %s (%s)", group.facebook_id, group.url
        )
        summary["error"] = str(exc)

    return summary


async def scrape_all_active_groups() -> list[dict]:
    """Scrape every active group sequentially and return per-group summaries.

    Sequential by design: Apify rate-limits runs and serial execution keeps
    failure isolation clear (one group's error never affects another's).
    """
    async with async_session() as session:
        result = await session.execute(
            select(TargetGroup).where(TargetGroup.is_active.is_(True))
        )
        groups = result.scalars().all()

    summaries: list[dict] = []
    for group in groups:
        summaries.append(await scrape_group(group))

    return summaries
