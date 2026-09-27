from datetime import date, time, datetime

from sqlalchemy import Integer, Date, Time, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base


class DoctorSlot(Base):
    __tablename__ = "doctor_slots"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
    )

    doctor_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("doctors.id", ondelete="CASCADE"),
        nullable=False
    )

    slot_date: Mapped[date] = mapped_column(
        Date,
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

    is_available: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )