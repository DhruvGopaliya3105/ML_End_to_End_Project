from datetime import date, datetime

from sqlalchemy import (
    Integer,
    String,
    Text,
    Date,
    DateTime,
    ForeignKey
)

from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base


class Treatment(Base):

    __tablename__ = "treatments"

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

    treatment_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    start_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True
    )

    end_date: Mapped[date | None] = mapped_column(
        Date,
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