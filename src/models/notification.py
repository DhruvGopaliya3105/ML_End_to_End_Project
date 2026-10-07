from datetime import datetime

from sqlalchemy import (
    Integer,
    String,
    Text,
    Boolean,
    DateTime,
    ForeignKey
)

from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base


class Notification(Base):

    __tablename__ = "notifications"

    # ==========================================
    # PRIMARY KEY
    # ==========================================

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
    )

    # ==========================================
    # USER ID
    # ==========================================

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(
            "users.id",
            ondelete="CASCADE"
        ),
        nullable=False
    )

    # ==========================================
    # APPOINTMENT ID
    # ==========================================

    appointment_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey(
            "appointments.id",
            ondelete="SET NULL"
        ),
        nullable=True
    )

    # ==========================================
    # TITLE
    # ==========================================

    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False
    )

    # ==========================================
    # MESSAGE
    # ==========================================

    message: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )

    # ==========================================
    # NOTIFICATION TYPE
    # ==========================================

    notification_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False
    )

    # ==========================================
    # READ / UNREAD
    # ==========================================

    is_read: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False
    )

    # ==========================================
    # CREATED AT
    # ==========================================

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )