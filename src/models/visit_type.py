from datetime import datetime

from sqlalchemy import (
    Integer,
    String,
    Boolean,
    DateTime
)

from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base


class VisitType(Base):

    __tablename__ = "visit_types"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
    )

    name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False
    )

    min_duration_minutes: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    max_duration_minutes: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    default_duration_minutes: Mapped[int] = mapped_column(
        Integer,
        nullable=False
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