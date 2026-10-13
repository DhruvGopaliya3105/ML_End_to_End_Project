"""Workflow events and recovery attempts - the flight recorder."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base


class WorkflowEvent(Base):
    """A significant workflow state transition (payment, appointment, order).

    Events sharing one ``correlation_id`` belong to the same workflow and are
    what the flight recorder replays to reconstruct a failed journey.
    ``idempotency_key`` makes retries safe - a replayed event with the same
    key is recognised instead of duplicated.
    """

    __tablename__ = "workflow_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    correlation_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    # PAYMENT | APPOINTMENT | ORDER
    workflow_type: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(60))
    resource_ref: Mapped[str | None] = mapped_column(String(120), index=True)
    # STATE_TRANSITION | FAILURE | RETRY | RECOVERY
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(80), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class RecoveryAttempt(Base):
    """One safe-recovery attempt for a failed workflow."""

    __tablename__ = "recovery_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    workflow_event_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("workflow_events.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    correlation_id: Mapped[str | None] = mapped_column(String(64), index=True)
    incident_type: Mapped[str] = mapped_column(String(60), nullable=False)
    # PENDING | IN_PROGRESS | SUCCEEDED | FAILED | ESCALATED
    status: Mapped[str] = mapped_column(String(16), default="PENDING", index=True, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(80), index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
