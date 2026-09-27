from datetime import date, time, datetime

from sqlalchemy import (
    Integer,
    Date,
    Time,
    String,
    Text,
    DateTime,
    ForeignKey,
    Numeric
)

from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship
)

from src.database.base import Base


class Appointment(Base):

    __tablename__ = "appointments"

    # ==========================================
    # PRIMARY KEY
    # ==========================================

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
    )

    # ==========================================
    # PATIENT
    # ==========================================

    patient_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(
            "users.id",
            ondelete="CASCADE"
        ),
        nullable=False
    )

    # ==========================================
    # DOCTOR
    # ==========================================

    doctor_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(
            "doctors.id",
            ondelete="CASCADE"
        ),
        nullable=False
    )

    # ==========================================
    # SLOT
    # ==========================================

    slot_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey(
            "doctor_slots.id",
            ondelete="SET NULL"
        ),
        nullable=True
    )

    # ==========================================
    # APPOINTMENT DATE
    # ==========================================

    appointment_date: Mapped[date] = mapped_column(
        Date,
        nullable=False
    )

    # ==========================================
    # START TIME
    # ==========================================

    start_time: Mapped[time] = mapped_column(
        Time,
        nullable=False
    )

    # ==========================================
    # END TIME
    # ==========================================

    end_time: Mapped[time] = mapped_column(
        Time,
        nullable=False
    )

    # ==========================================
    # VISIT TYPE
    # ==========================================

    visit_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True
    )

    # ==========================================
    # DURATION
    # ==========================================

    duration_minutes: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True
    )

    # ==========================================
    # STATUS
    # ==========================================

    status: Mapped[str] = mapped_column(
        String(40),
        default="BOOKED",
        nullable=False
    )

    # ==========================================
    # REASON
    # ==========================================

    reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    # ==========================================
    # PAYMENT METHOD
    # ==========================================

    payment_method: Mapped[str] = mapped_column(
        String(30),
        default="CASH",
        nullable=False
    )

    # ==========================================
    # PAYMENT STATUS
    # ==========================================

    payment_status: Mapped[str] = mapped_column(
        String(30),
        default="PENDING",
        nullable=False
    )

    # ==========================================
    # PAYMENT AMOUNT
    # ==========================================

    payment_amount: Mapped[float | None] = mapped_column(
        Numeric(10, 2),
        nullable=True
    )

    # ==========================================
    # REFUND STATUS
    # ==========================================

    refund_status: Mapped[str] = mapped_column(
        String(30),
        default="NOT_REQUIRED",
        nullable=False
    )

    # ==========================================
    # REFUND AMOUNT
    # ==========================================

    refund_amount: Mapped[float | None] = mapped_column(
        Numeric(10, 2),
        nullable=True
    )

    # ==========================================
    # REFUND METHOD
    # ==========================================

    refund_method: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True
    )

    # ==========================================
    # REFUND REASON
    # ==========================================

    refund_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    # ==========================================
    # REFUND TIME
    # ==========================================

    refund_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )

    # ==========================================
    # DOCTOR CANCEL REASON
    # ==========================================

    doctor_cancel_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    # ==========================================
    # CANCELLED BY
    # ==========================================

    cancelled_by: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True
    )

    # ==========================================
    # CANCELLED TIME
    # ==========================================

    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )

    # ==========================================
    # CREATED
    # ==========================================

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )

    # ==========================================
    # UPDATED
    # ==========================================

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    # ==========================================
    # DOCTOR RELATIONSHIP
    # ==========================================

    doctor = relationship(
        "Doctor",
        lazy="joined"
    )