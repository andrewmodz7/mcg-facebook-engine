"""End-to-end pipeline: scrape → filter → score, with progress tracking.

Used by the Run Scan button. Updates a ScanRun row throughout execution
so the UI can poll for status. Catches exceptions per stage so a failure
in one phase doesn't lose progress in earlier phases.
"""

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select, update

from app.agents import score_pending_posts
from app.db import async_session
from app.filters import filter_pending_posts
from app.models import ScanRun, TargetGroup
from app.scrapers import scrape_group

logger = logging.getLogger(__name__)


async def _update_scan(scan_run_id: UUID, **fields: Any) -> None:
    """Patch a ScanRun row in its own short-lived session/transaction.

    Each progress write commits independently so a poll always sees the
    latest state, and a later-stage crash never rolls back earlier progress.
    """
    async with async_session() as session:
        await session.execute(
            update(ScanRun).where(ScanRun.id == scan_run_id).values(**fields)
        )
        await session.commit()


async def run_full_pipeline(scan_run_id: UUID) -> None:
    """Execute the full pipeline, updating the ScanRun row as it progresses.

    Stages:
    1. Scrape all active target_groups (per-group progress tracking)
    2. Filter pending raw_posts (calls filter_pending_posts)
    3. Score pending raw_posts (calls score_pending_posts)

    On success: status='completed', stage='done', completed_at=now.
    On any exception: status='failed', error_message=str(exc), completed_at=now.
    """
    try:
        # --- Stage 1: scrape -------------------------------------------------
        # Inlined over scrape_group (rather than scrape_all_active_groups) so we
        # can update the scan_run row between each group for live progress.
        async with async_session() as session:
            result = await session.execute(
                select(TargetGroup).where(TargetGroup.is_active.is_(True))
            )
            groups = result.scalars().all()

        await _update_scan(
            scan_run_id,
            stage="scraping",
            groups_total=len(groups),
            groups_completed=0,
            progress_message=f"Scraping {len(groups)} active group(s)...",
        )

        posts_scraped = 0
        for i, group in enumerate(groups, start=1):
            await _update_scan(
                scan_run_id,
                progress_message=(
                    f"Scraping group {i} of {len(groups)}: "
                    f"{group.name or group.facebook_id}"
                ),
            )
            summary = await scrape_group(group)
            posts_scraped += summary["posts_inserted"]
            await _update_scan(
                scan_run_id,
                groups_completed=i,
                posts_scraped=posts_scraped,
            )

        # --- Stage 2: filter -------------------------------------------------
        await _update_scan(
            scan_run_id,
            stage="filtering",
            progress_message="Filtering newly scraped posts...",
        )
        filter_summary = await filter_pending_posts()
        await _update_scan(
            scan_run_id,
            posts_filtered=filter_summary["total_evaluated"],
            progress_message=(
                f"Filtered {filter_summary['total_evaluated']} post(s): "
                f"{filter_summary['passed']} passed"
            ),
        )

        # --- Stage 3: score --------------------------------------------------
        await _update_scan(
            scan_run_id,
            stage="scoring",
            progress_message="Scoring filtered posts with the AI agent...",
        )
        score_summary = await score_pending_posts()
        await _update_scan(
            scan_run_id,
            posts_scored=score_summary["total_evaluated"],
            leads_created=score_summary["is_lead"],
            progress_message=(
                f"Scored {score_summary['total_evaluated']} post(s): "
                f"{score_summary['is_lead']} new lead(s)"
            ),
        )

        # --- Done ------------------------------------------------------------
        await _update_scan(
            scan_run_id,
            status="completed",
            stage="done",
            completed_at=datetime.now(timezone.utc),
            progress_message=(
                f"Scan complete — {score_summary['is_lead']} new lead(s) "
                f"from {posts_scraped} new post(s)."
            ),
        )

    except Exception as exc:  # noqa: BLE001 — record any failure for the UI
        logger.exception("Pipeline failed for scan_run %s", scan_run_id)
        await _update_scan(
            scan_run_id,
            status="failed",
            error_message=str(exc)[:1000],
            completed_at=datetime.now(timezone.utc),
        )
