from datetime import datetime

from sqlalchemy import (
    Integer,
    Text,
    DateTime,
    ForeignKey
)

from sqlalchemy.orm import (
    Mapped,
    mapped_column
)

from src.database.base import Base


class Prescription(Base):

    __tablename__ = "prescriptions"


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


    doctor_id: Mapped[int | None] = mapped_column(

        Integer,

        ForeignKey(
            "doctors.id",
            ondelete="SET NULL"
        ),

        nullable=True

    )


    medical_record_id: Mapped[int | None] = mapped_column(

        Integer,

        ForeignKey(
            "medical_records.id",
            ondelete="SET NULL"
        ),

        nullable=True

    )


    treatment_id: Mapped[int | None] = mapped_column(

        Integer,

        ForeignKey(
            "treatments.id",
            ondelete="SET NULL"
        ),

        nullable=True

    )


    diagnosis: Mapped[str | None] = mapped_column(

        Text,

        nullable=True

    )


    doctor_instructions: Mapped[str | None] = mapped_column(

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