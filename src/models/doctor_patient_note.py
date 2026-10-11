"""Notes a doctor keeps on a patient.

This is the part of a file that is not a prescription and not a formal medical
record: "patient asked about diet", "allergic to penicillin", "will not come
without a reminder", "family history", "needs the old report before the next
visit". Three flags make it usable in a real clinic:

* ``visibility`` - DOCTOR_ONLY (private) or PATIENT_VISIBLE (the patient can
  read it on their own history page), so a doctor can jot things down without
  leaking them.
* ``is_pinned``  - stays on top of the patient file (allergies, red flags).
* ``is_urgent``  - shows in the desk's "needs attention" count.

Only the doctor who wrote it (or a super user / admin) can edit or delete a
note; every write lands in ``pharmacy_audit_logs`` like the rest of the module.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text
)

from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base


class DoctorPatientNote(Base):
    """One clinical note about one patient, written by one doctor."""

    __tablename__ = "doctor_patient_notes"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
    )

    # who wrote it (a row in `users`, so the login behind it stays linked)
    doctor_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    doctor_name: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True
    )

    doctor_specialization: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True
    )

    # whose file it belongs to
    patient_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # NOTE | ADVISORY | ALLERGY | RED_FLAG | PAYMENT | FOLLOW_UP | VISIT
    note_type: Mapped[str] = mapped_column(
        String(20),
        default="NOTE",
        nullable=False,
        index=True
    )

    title: Mapped[str] = mapped_column(
        String(160),
        nullable=False
    )

    body: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    # DOCTOR_ONLY | PATIENT_VISIBLE
    visibility: Mapped[str] = mapped_column(
        String(20),
        default="DOCTOR_ONLY",
        nullable=False
    )

    is_pinned: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False
    )

    is_urgent: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False
    )

    # optional "come back on" date attached to the note
    follow_up_date: Mapped[datetime | None] = mapped_column(
        Date,
        nullable=True
    )

    # soft delete, so the audit trail can still explain what was removed
    status: Mapped[str] = mapped_column(
        String(20),
        default="ACTIVE",
        nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<DoctorPatientNote {self.id} patient={self.patient_id} "
            f"{self.note_type} '{(self.title or '')[:30]}'>"
        )
