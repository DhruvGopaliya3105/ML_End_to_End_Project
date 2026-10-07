from datetime import datetime

from sqlalchemy import String, Integer, DateTime, Boolean, Text, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base


class Doctor(Base):
    __tablename__ = "doctors"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    email: Mapped[str] = mapped_column(
        String(150),
        unique=True,
        nullable=False,
        index=True
    )

    phone: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True
    )

    specialization: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    qualification: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True
    )

    experience_years: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True
    )

    languages: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True
    )

    consultation_fee: Mapped[float | None] = mapped_column(
        Numeric(10, 2),
        nullable=True
    )

    profile_photo: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True
    )

    bio: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
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