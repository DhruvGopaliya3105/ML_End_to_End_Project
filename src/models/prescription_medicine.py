from datetime import datetime

from sqlalchemy import (
    Integer,
    String,
    DateTime,
    ForeignKey
)

from sqlalchemy.orm import (
    Mapped,
    mapped_column
)

from src.database.base import Base


class PrescriptionMedicine(Base):

    __tablename__ = "prescription_medicines"


    id: Mapped[int] = mapped_column(

        Integer,

        primary_key=True,

        index=True

    )


    prescription_id: Mapped[int] = mapped_column(

        Integer,

        ForeignKey(
            "prescriptions.id",
            ondelete="CASCADE"
        ),

        nullable=False

    )


    medicine_name: Mapped[str] = mapped_column(

        String(200),

        nullable=False

    )


    dosage: Mapped[str | None] = mapped_column(

        String(100),

        nullable=True

    )


    frequency: Mapped[str | None] = mapped_column(

        String(100),

        nullable=True

    )


    duration: Mapped[str | None] = mapped_column(

        String(100),

        nullable=True

    )


    instructions: Mapped[str | None] = mapped_column(

        String(500),

        nullable=True

    )


    created_at: Mapped[datetime] = mapped_column(

        DateTime,

        default=datetime.utcnow

    )