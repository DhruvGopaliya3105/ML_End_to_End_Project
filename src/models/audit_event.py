"""Audit and security events - the database mirror of the JSONL streams."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base


class AuditEvent(Base):
    """One row per audited action (mirrors the JSONL audit log streams).

    The JSONL files in ``logs/`` are the primary, append-only trail; these
    rows make the same events queryable from SQL for the admin Audit
    Explorer. Redaction rules are identical to ``audit_log._redact``.
    """

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    event_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(64), index=True)
    request_id: Mapped[str | None] = mapped_column(String(64), index=True)
    # email of the user, or the service identity for machine actors
    actor: Mapped[str | None] = mapped_column(String(150), index=True)
    role: Mapped[str | None] = mapped_column(String(20), index=True)
    mcp_server: Mapped[str | None] = mapped_column(String(60), index=True)
    tool: Mapped[str | None] = mapped_column(String(80), index=True)
    action: Mapped[str | None] = mapped_column(String(80), index=True)
    resource_type: Mapped[str | None] = mapped_column(String(60))
    resource_ref: Mapped[str | None] = mapped_column(String(120))
    # success | denied | error
    result: Mapped[str] = mapped_column(String(20), default="success", nullable=False)
    error_category: Mapped[str | None] = mapped_column(String(60))
    duration_ms: Mapped[float | None] = mapped_column(Float)
    policy_version: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class SecurityEvent(Base):
    """Auth failures, authorization denials, rate limits, privileged ops."""

    __tablename__ = "security_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    event_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(64), index=True)
    # may be anonymous (failed login) - never a password or token
    actor: Mapped[str | None] = mapped_column(String(150), index=True)
    role: Mapped[str | None] = mapped_column(String(20))
    # login_failure | access_denied | rate_limited | privileged_operation
    action: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(60))
    resource_ref: Mapped[str | None] = mapped_column(String(120))
    result: Mapped[str] = mapped_column(String(20), default="denied", nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
