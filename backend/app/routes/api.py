"""HTTP API for the MCG Lead Engine dashboard.

HTTP Basic Auth on every endpoint (credentials from env). Exposes the leads
pipeline (list / detail / update) and the Run Scan controls (trigger + status
polling). The scan trigger schedules the full pipeline via BackgroundTasks and
relies on a partial unique index for single-scan-at-a-time enforcement.
"""

import os
import secrets
from typing import Any, Optional
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    status,
)
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db import async_session
from app.models import Lead, RawPost, ScanRun, TargetGroup
from app.pipeline import run_full_pipeline

router = APIRouter(prefix="/api")

security = HTTPBasic()

# Stages a lead can move through on the dashboard.
VALID_STAGES = {"new", "messaged", "replied", "engaged", "dead"}


def verify_credentials(
    credentials: HTTPBasicCredentials = Depends(security),
) -> str:
    """Verify against env-configured user/password pairs. Returns username on success."""
    users = {
        "marcus": os.environ.get("MARCUS_PASSWORD", ""),
        "andrew": os.environ.get("ANDREW_PASSWORD", ""),
    }
    username = credentials.username
    password = credentials.password
    expected = users.get(username, "")
    if not expected or not secrets.compare_digest(password, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return username


# --- Serializers ---------------------------------------------------------


def _serialize_lead(
    lead: Lead, post: RawPost, group_name: Optional[str]
) -> dict[str, Any]:
    """Flatten a lead plus its raw_post/group context into a JSON-ready dict."""
    return {
        "id": str(lead.id),
        "urgency_score": lead.urgency_score,
        "lead_type": lead.lead_type,
        "recommended_action": lead.recommended_action,
        "angle": lead.angle,
        "reasoning": lead.reasoning,
        "stage": lead.stage,
        "marcus_notes": lead.marcus_notes,
        "contact_email": lead.contact_email,
        "contact_phone": lead.contact_phone,
        "created_at": lead.created_at.isoformat() if lead.created_at else None,
        "updated_at": lead.updated_at.isoformat() if lead.updated_at else None,
        # raw_post context
        "raw_post_id": str(lead.raw_post_id),
        "post_text": post.post_text,
        "post_url": post.post_url,
        "author_name": post.author_name,
        "author_profile_url": post.author_profile_url,
        "group_name": group_name,
        "posted_at": post.posted_at.isoformat() if post.posted_at else None,
        "reactions_count": post.reactions_count,
        "comments_count": post.comments_count,
    }


def _serialize_scan(scan: ScanRun) -> dict[str, Any]:
    """Serialize a ScanRun row for the polling UI."""
    return {
        "id": str(scan.id),
        "triggered_by": scan.triggered_by,
        "status": scan.status,
        "stage": scan.stage,
        "progress_message": scan.progress_message,
        "groups_total": scan.groups_total,
        "groups_completed": scan.groups_completed,
        "posts_scraped": scan.posts_scraped,
        "posts_filtered": scan.posts_filtered,
        "posts_scored": scan.posts_scored,
        "leads_created": scan.leads_created,
        "error_message": scan.error_message,
        "started_at": scan.started_at.isoformat() if scan.started_at else None,
        "completed_at": (
            scan.completed_at.isoformat() if scan.completed_at else None
        ),
    }


# --- Request bodies ------------------------------------------------------


class LeadUpdate(BaseModel):
    """Partial update for a lead. Unset fields are left untouched."""

    stage: Optional[str] = None
    marcus_notes: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None


# --- Leads ---------------------------------------------------------------


@router.get("/leads")
async def list_leads(_user: str = Depends(verify_credentials)) -> list[dict]:
    """All leads, ranked by urgency_score DESC then created_at DESC."""
    async with async_session() as session:
        result = await session.execute(
            select(Lead, RawPost, TargetGroup.name)
            .join(RawPost, Lead.raw_post_id == RawPost.id)
            .join(TargetGroup, RawPost.group_id == TargetGroup.id)
            .order_by(Lead.urgency_score.desc(), Lead.created_at.desc())
        )
        rows = result.all()

    return [_serialize_lead(lead, post, name) for lead, post, name in rows]


async def _fetch_lead(lead_id: UUID) -> tuple[Lead, RawPost, Optional[str]]:
    """Load one lead with its raw_post and group name, or raise 404."""
    async with async_session() as session:
        result = await session.execute(
            select(Lead, RawPost, TargetGroup.name)
            .join(RawPost, Lead.raw_post_id == RawPost.id)
            .join(TargetGroup, RawPost.group_id == TargetGroup.id)
            .where(Lead.id == lead_id)
        )
        row = result.first()

    if row is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    return row  # type: ignore[return-value]


@router.get("/leads/{lead_id}")
async def get_lead(
    lead_id: UUID, _user: str = Depends(verify_credentials)
) -> dict:
    """A single lead with full raw_post + group context for the detail drawer."""
    lead, post, name = await _fetch_lead(lead_id)
    return _serialize_lead(lead, post, name)


@router.patch("/leads/{lead_id}")
async def update_lead(
    lead_id: UUID,
    patch: LeadUpdate,
    _user: str = Depends(verify_credentials),
) -> dict:
    """Update stage / notes / contact fields. Partial body; returns the lead."""
    fields = patch.model_dump(exclude_unset=True)

    if "stage" in fields and fields["stage"] not in VALID_STAGES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid stage. Must be one of: {sorted(VALID_STAGES)}",
        )

    async with async_session() as session:
        lead = await session.get(Lead, lead_id)
        if lead is None:
            raise HTTPException(status_code=404, detail="Lead not found")
        for key, value in fields.items():
            setattr(lead, key, value)
        await session.commit()

    lead, post, name = await _fetch_lead(lead_id)
    return _serialize_lead(lead, post, name)


# --- Scans ---------------------------------------------------------------


@router.post("/scans", status_code=status.HTTP_202_ACCEPTED)
async def trigger_scan(
    background_tasks: BackgroundTasks,
    user: str = Depends(verify_credentials),
) -> dict:
    """Start a scan. 409 if one is already running (partial unique index)."""
    scan = ScanRun(
        triggered_by=user,
        status="running",
        stage="scraping",
        progress_message="Starting scan...",
    )
    try:
        async with async_session() as session:
            session.add(scan)
            await session.commit()
            await session.refresh(scan)
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Scan already in progress.",
        )

    background_tasks.add_task(run_full_pipeline, scan.id)
    return {"scan_run_id": str(scan.id)}


@router.get("/scans/current")
async def current_scan(_user: str = Depends(verify_credentials)) -> dict:
    """The most recent scan run (running, completed, or failed). 404 if none."""
    async with async_session() as session:
        result = await session.execute(
            select(ScanRun).order_by(ScanRun.started_at.desc()).limit(1)
        )
        scan = result.scalar_one_or_none()

    if scan is None:
        raise HTTPException(status_code=404, detail="No scans have run yet")
    return _serialize_scan(scan)


@router.get("/scans/{scan_run_id}")
async def get_scan(
    scan_run_id: UUID, _user: str = Depends(verify_credentials)
) -> dict:
    """A specific scan run by ID."""
    async with async_session() as session:
        scan = await session.get(ScanRun, scan_run_id)

    if scan is None:
        raise HTTPException(status_code=404, detail="Scan not found")
    return _serialize_scan(scan)
