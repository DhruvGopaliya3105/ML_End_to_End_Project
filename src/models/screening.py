from datetime import datetime

from sqlalchemy import (
    Integer,
    Text,
    String,
    DateTime,
    ForeignKey
)

from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base


class ScreeningHistory(Base):

    __tablename__ = "screening_history"

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

    symptoms: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )

    ai_response: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    care_category: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True
    )

    recommended_specialist: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True
    )

    severity: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )