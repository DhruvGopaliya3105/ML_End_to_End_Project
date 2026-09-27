from datetime import date, datetime

from sqlalchemy import (
    Integer,
    Date,
    DateTime,
    Text,
    String,
    ForeignKey
)

from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base


class FollowUp(Base):

    __tablename__ = "follow_ups"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
    )

    patient_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(
            "users.id",
            ondelete="CASCADE"
        ),
        nullable=False
    )

    medical_record_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey(
            "medical_records.id",
            ondelete="SET NULL"
        ),
        nullable=True
    )

    doctor_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey(
            "doctors.id",
            ondelete="SET NULL"
        ),
        nullable=True
    )

    appointment_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey(
            "appointments.id",
            ondelete="SET NULL"
        ),
        nullable=True
    )

    follow_up_date: Mapped[date] = mapped_column(
        Date,
        nullable=False
    )

    reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    instructions: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="PENDING",
        nullable=False
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
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