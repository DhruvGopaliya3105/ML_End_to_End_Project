"""Clinical conflict cases - alerts for authorized clinicians, never auto-edits."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base


class ClinicalConflict(Base):
    """A detected conflict or safety concern in recorded clinical information.

    A conflict is an ALERT, not a confirmed medical conclusion. The system
    never changes prescriptions and never silently overwrites records - only
    authorized clinicians resolve conflicts through the review workflow.
    """

    __tablename__ = "clinical_conflicts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # ALLERGY_PRESCRIPTION | MEDICATION_DATE | MISSING_CONTEXT
    conflict_type: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    patient_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    description: Mapped[str | None] = mapped_column(Text)
    # LOW | MEDIUM | HIGH
    severity: Mapped[str] = mapped_column(String(12), default="MEDIUM", nullable=False)
    # OPEN | REVIEWING | RESOLVED
    status: Mapped[str] = mapped_column(String(16), default="OPEN", index=True, nullable=False)
    assigned_to_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(150))
    resolution_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
