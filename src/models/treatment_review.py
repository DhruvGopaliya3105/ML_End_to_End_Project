from datetime import datetime

from sqlalchemy import (
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey
)

from sqlalchemy.orm import (
    Mapped,
    mapped_column
)

from src.database.base import Base


class TreatmentReview(Base):

    __tablename__ = "treatment_reviews"

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

    treatment_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey(
            "treatments.id",
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

    outcome: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    current_condition: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    experience: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    follow_up_preference: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    change_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    rating: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True
    )

    comment: Mapped[str | None] = mapped_column(
        Text,
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