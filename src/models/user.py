from datetime import datetime

from sqlalchemy import String, Integer, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base


class User(Base):

    __tablename__ = "users"

    # Primary Key
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
    )

    # User name
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    # Email
    email: Mapped[str] = mapped_column(
        String(150),
        unique=True,
        index=True,
        nullable=False
    )

    # Phone
    phone: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True
    )

    # Hashed password
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    # Age
    age: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True
    )

    # Gender
    gender: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True
    )

    # Profile photo path
    profile_photo: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True
    )

    # User role
    role: Mapped[str] = mapped_column(
        String(20),
        default="PATIENT",
        nullable=False
    )

    # Account active/inactive
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False
    )

    # Account creation time
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )

    # Last update time
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )