
from datetime import time, datetime

from sqlalchemy import (
    Integer,
    Time,
    Boolean,
    DateTime,
    ForeignKey
)

from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base


class DoctorSchedule(Base):

    __tablename__ = "doctor_schedules"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
    )

    doctor_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(
            "doctors.id",
            ondelete="CASCADE"
        ),
        nullable=False
    )

    # 0 = Monday
    # 1 = Tuesday
    # 2 = Wednesday
    # 3 = Thursday
    # 4 = Friday
    # 5 = Saturday
    # 6 = Sunday
    day_of_week: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    start_time: Mapped[time] = mapped_column(
        Time,
        nullable=False
    )

    end_time: Mapped[time] = mapped_column(
        Time,
        nullable=False
    )

    # Kitne minute ke gap par possible starting time generate hoga
    slot_interval_minutes: Mapped[int] = mapped_column(
        Integer,
        default=5,
        nullable=False
    )

    is_available: Mapped[bool] = mapped_column(
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