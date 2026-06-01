"""SQLAlchemy 2.0 ORM models for the v1 schema.

Four tables:
- target_groups: the Facebook groups we scrape.
- raw_posts: every post returned from Apify, stored untouched with an audit trail.
- leads: posts that survived the AI scoring agent, promoted with rank and action.
- scan_runs: one row per Run Scan job, tracking pipeline progress for the UI.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    false,
    text,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from sqlalchemy.types import DateTime

from app.db import Base


class TargetGroup(Base):
    """A Facebook group we scrape for leads."""

    __tablename__ = "target_groups"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    facebook_id: Mapped[str] = mapped_column(
        String, unique=True, index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=true()
    )
    last_scraped_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    posts: Mapped[list["RawPost"]] = relationship(
        "RawPost", back_populates="group"
    )


class RawPost(Base):
    """A raw post from Apify, stored untouched with its full JSON payload."""

    __tablename__ = "raw_posts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("target_groups.id"),
        nullable=False,
        index=True,
    )
    facebook_post_id: Mapped[str] = mapped_column(
        String, unique=True, index=True, nullable=False
    )
    author_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    author_profile_url: Mapped[Optional[str]] = mapped_column(
        String, nullable=True
    )
    author_facebook_id: Mapped[Optional[str]] = mapped_column(
        String, nullable=True, index=True
    )
    post_text: Mapped[str] = mapped_column(Text, nullable=False)
    post_url: Mapped[str] = mapped_column(String, nullable=False)
    posted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reactions_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0")
    )
    comments_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0")
    )
    raw_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    processed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), index=True
    )
    # First-pass deterministic filter state. NULL means "not yet filtered",
    # which is how the filter picks up new rows. The allowed values
    # ("passed", "rejected_empty", "rejected_url_only", "rejected_too_short")
    # are validated at the application layer, not as a Postgres ENUM.
    filter_status: Mapped[Optional[str]] = mapped_column(
        String, nullable=True, index=True
    )
    filter_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # AI scoring agent state. NULL means "not yet scored". The allowed values
    # ("scored_is_lead", "scored_not_a_lead", "score_error") are validated at
    # the application layer, not as a Postgres ENUM. score_reasoning holds the
    # agent's rationale for both leads and non-leads as an audit trail.
    score_status: Mapped[Optional[str]] = mapped_column(
        String, nullable=True, index=True
    )
    score_reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    group: Mapped["TargetGroup"] = relationship(
        "TargetGroup", back_populates="posts"
    )
    lead: Mapped[Optional["Lead"]] = relationship(
        "Lead", back_populates="raw_post", uselist=False
    )


class Lead(Base):
    """A scored lead promoted from a raw post by the AI scoring agent."""

    __tablename__ = "leads"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    raw_post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("raw_posts.id"),
        unique=True,
        nullable=False,
    )
    urgency_score: Mapped[int] = mapped_column(
        Integer, nullable=False, index=True
    )
    lead_type: Mapped[str] = mapped_column(String, nullable=False)
    recommended_action: Mapped[str] = mapped_column(String, nullable=False)
    suggested_comment: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    suggested_dm: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # The agent's strategic reasoning for HOW Marcus could open this
    # conversation — the path to a hard money loan, direct or indirect. The
    # most important field for Marcus's dashboard.
    angle: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    stage: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="new",
        server_default=text("'new'"),
        index=True,
    )
    marcus_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    contact_email: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    contact_phone: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    raw_post: Mapped["RawPost"] = relationship(
        "RawPost", back_populates="lead"
    )


class ScanRun(Base):
    """One Run Scan job: scrape -> filter -> score, with progress tracking.

    The UI polls the latest row to render the Run Scan button's progress.
    A partial unique index on ``status='running'`` enforces single-scan-at-a-
    time at the DB level: a second concurrent insert with status='running'
    raises IntegrityError, which the API layer turns into a 409.
    """

    __tablename__ = "scan_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    triggered_by: Mapped[str] = mapped_column(String, nullable=False)
    # One of "running", "completed", "failed" — validated at the app layer.
    status: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # One of "scraping", "filtering", "scoring", "done" — updated as we go.
    stage: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    progress_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    groups_total: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0")
    )
    groups_completed: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0")
    )
    posts_scraped: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0")
    )
    posts_filtered: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0")
    )
    posts_scored: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0")
    )
    leads_created: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0")
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        # At most one running scan at a time. Partial index so completed/failed
        # rows don't collide.
        Index(
            "ix_scan_runs_single_running",
            "status",
            unique=True,
            postgresql_where=text("status = 'running'"),
        ),
    )
