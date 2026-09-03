"""ORM models for durable container-loading calculation audits."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base


class ContainerLoadingRun(Base):
    """Immutable audit record for every container-loading calculation."""

    __tablename__ = "container_loading_runs"
    __table_args__ = (Index("ix_container_loading_runs_owner_created", "owner_open_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_open_id: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued", server_default="queued")
    container_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    items_payload: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    results_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
