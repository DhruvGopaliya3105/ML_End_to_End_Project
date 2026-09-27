from datetime import date, datetime

from sqlalchemy import (
    Integer,
    Date,
    Text,
    String,
    DateTime,
    ForeignKey
)

from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base


class MedicalRecord(Base):

    __tablename__ = "medical_records"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
    )

    patient_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )

    doctor_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("doctors.id", ondelete="SET NULL"),
        nullable=True
    )

    appointment_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("appointments.id", ondelete="SET NULL"),
        nullable=True
    )

    visit_date: Mapped[date] = mapped_column(
        Date,
        nullable=False
    )

    chief_complaint: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    symptoms: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    clinical_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    diagnosis_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    treatment_summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    medicines: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    doctor_instructions: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="ACTIVE",
        nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )