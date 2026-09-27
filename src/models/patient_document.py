from datetime import datetime

from sqlalchemy import (
    Integer,
    String,
    BigInteger,
    DateTime,
    ForeignKey
)

from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base


class PatientDocument(Base):

    __tablename__ = "patient_documents"

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

    document_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    document_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True
    )

    file_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False
    )

    file_size: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True
    )

    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="ACTIVE",
        nullable=False
    )