from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text
)

from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship
)

from src.database.base import Base


class PharmacyOrder(Base):
    """A confirmed or pending medicine purchase.

    Status flow
    -----------
    PENDING_PAYMENT -> CONFIRMED        (online payment verified)
    PENDING_PAYMENT -> CANCELLED        (patient gave up / payment failed)
    CONFIRMED      -> DELIVERED/HANDED_OVER (staff marks it in admin)
    CONFIRMED      -> CANCELLED|REFUNDED (stock is given back once)

    Payment
    -------
    payment_method  CASH   -> patient pays at the counter, payment_status
                              stays PENDING until staff marks it PAID
    payment_method  ONLINE -> simulated UPI/QR by default; if RAZORPAY_KEY_ID
                              is set in .env the same flow verifies the
                              gateway signature instead of trusting the browser
    """

    __tablename__ = "pharmacy_orders"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
    )

    # Human readable slip number, e.g. PH-20261007-0007
    order_no: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        index=True,
        nullable=False
    )

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(
            "users.id",
            ondelete="CASCADE"
        ),
        nullable=False,
        index=True
    )

    # CATALOG (patient searched) | PRESCRIPTION (came from a doctor)
    order_type: Mapped[str] = mapped_column(
        String(20),
        default="CATALOG",
        nullable=False
    )

    prescription_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey(
            "prescriptions.id",
            ondelete="SET NULL"
        ),
        nullable=True,
        index=True
    )

    # PENDING_PAYMENT | CONFIRMED | CANCELLED | REFUNDED
    status: Mapped[str] = mapped_column(
        String(30),
        default="PENDING_PAYMENT",
        nullable=False,
        index=True
    )

    # CASH | ONLINE
    payment_method: Mapped[str] = mapped_column(
        String(20),
        default="CASH",
        nullable=False
    )

    # PENDING | PAID | FAILED | REFUNDED
    payment_status: Mapped[str] = mapped_column(
        String(20),
        default="PENDING",
        nullable=False
    )

    subtotal: Mapped[float] = mapped_column(
        Numeric(10, 2),
        default=0,
        nullable=False
    )

    delivery_fee: Mapped[float] = mapped_column(
        Numeric(10, 2),
        default=0,
        nullable=False
    )

    total: Mapped[float] = mapped_column(
        Numeric(10, 2),
        default=0,
        nullable=False
    )

    # PICKUP (at counter) | DELIVERY (to address)
    delivery_type: Mapped[str] = mapped_column(
        String(20),
        default="PICKUP",
        nullable=False
    )

    address: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True
    )

    phone: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    # Emergency order -> staff sees it flagged in the admin queue
    is_emergency: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False
    )

    # Payment references (safe to store, these are not secrets)
    transaction_id: Mapped[str | None] = mapped_column(
        String(80),
        nullable=True
    )

    payment_reference: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True
    )

    # SIMULATED | RAZORPAY | CASH_COUNTER
    payment_provider: Mapped[str] = mapped_column(
        String(30),
        default="SIMULATED",
        nullable=False
    )

    # Stock has been moved for this order (guards double decrement / double
    # restock when a request is retried or a rollback is replayed)
    stock_adjusted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False
    )

    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )

    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )

    cancel_reason: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True
    )

    handed_over_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )

    # Snapshot taken automatically before any bulk admin write touched this row
    snapshot_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey(
            "pharmacy_snapshots.id",
            ondelete="SET NULL"
        ),
        nullable=True,
        index=True
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

    user: Mapped["User"] = relationship(  # noqa: F821
        "User",
        lazy="joined"
    )

    items: Mapped[list["PharmacyOrderItem"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        lazy="selectin"
    )

    @property
    def item_count(self) -> int:
        return sum(int(item.quantity or 0) for item in self.items)


class PharmacyOrderItem(Base):
    """Snapshot of one medicine line inside an order.

    The name / price / image are copied here on purpose: an order from last
    month must still print exactly what the patient paid, even after the
    catalog is edited or (by the super user) restored from an old snapshot.
    """

    __tablename__ = "pharmacy_order_items"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
    )

    order_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(
            "pharmacy_orders.id",
            ondelete="CASCADE"
        ),
        nullable=False,
        index=True
    )

    medicine_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey(
            "medicines.id",
            ondelete="SET NULL"
        ),
        nullable=True,
        index=True
    )

    medicine_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False
    )

    generic_name: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True
    )

    form: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True
    )

    strength: Mapped[str | None] = mapped_column(
        String(60),
        nullable=True
    )

    pack_size: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True
    )

    image_path: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True
    )

    quantity: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False
    )

    unit_price: Mapped[float] = mapped_column(
        Numeric(10, 2),
        default=0,
        nullable=False
    )

    line_total: Mapped[float] = mapped_column(
        Numeric(10, 2),
        default=0,
        nullable=False
    )

    source: Mapped[str] = mapped_column(
        String(20),
        default="CATALOG",
        nullable=False
    )

    prescription_medicine_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey(
            "prescription_medicines.id",
            ondelete="SET NULL"
        ),
        nullable=True
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

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )

    order: Mapped[PharmacyOrder] = relationship(
        back_populates="items"
    )

    medicine: Mapped["Medicine"] = relationship("Medicine")  # noqa: F821
