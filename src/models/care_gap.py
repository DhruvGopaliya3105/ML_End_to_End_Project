"""Care gaps and review tasks - administrative workflow gaps, not diagnoses."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base


class CareGap(Base):
    """A missing step detected in a patient's recorded healthcare journey.

    A gap is an administrative observation (a follow-up not recorded, a test
    result missing) - it is never a clinical conclusion by itself.
    """

    __tablename__ = "care_gaps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    patient_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # MISSING_FOLLOWUP | MISSING_REPORT | INCOMPLETE_WORKFLOW
    gap_type: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # LOW | MEDIUM | HIGH
    severity: Mapped[str] = mapped_column(String(12), default="MEDIUM", nullable=False)
    # OPEN | REVIEWING | RESOLVED
    status: Mapped[str] = mapped_column(String(16), default="OPEN", index=True, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(150))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CareReviewTask(Base):
    """A review task created for a care gap (assigned to a clinician)."""

    __tablename__ = "care_review_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    care_gap_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("care_gaps.id", ondelete="CASCADE"), index=True, nullable=False
    )
    assigned_to_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    assigned_to_name: Mapped[str | None] = mapped_column(String(120))
    # PENDING | IN_PROGRESS | DONE
    status: Mapped[str] = mapped_column(String(16), default="PENDING", index=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
