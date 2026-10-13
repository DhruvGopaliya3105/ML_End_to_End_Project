"""Change requests and approvals - preview first, approve, then execute."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base


class ChangeRequest(Base):
    """A proposed system change with impact preview and before/after records."""

    __tablename__ = "change_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # doctor_deactivation | role_change | catalog_change | schedule_change | custom
    change_type: Mapped[str] = mapped_column(String(60), index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    proposed_by: Mapped[str | None] = mapped_column(String(150), index=True)
    # PENDING | APPROVED | REJECTED | EXECUTED | ROLLED_BACK
    status: Mapped[str] = mapped_column(String(16), default="PENDING", index=True, nullable=False)
    impact_preview: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    before_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    rollback_plan: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(150))


class ChangeApproval(Base):
    """One approval/rejection decision on a change request.

    Separation of duties: the requester must not approve their own privileged
    action - that is enforced by the gateway, not just by this table.
    """

    __tablename__ = "change_approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    change_request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("change_requests.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    approver: Mapped[str] = mapped_column(String(150), nullable=False)
    # APPROVED | REJECTED
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
