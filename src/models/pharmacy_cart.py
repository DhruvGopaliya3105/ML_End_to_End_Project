from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint
)

from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship
)

from src.database.base import Base


class PharmacyCartItem(Base):
    """One line in a logged-in user's pharmacy cart.

    The cart is stored in SQL (not in the browser) so the same cart survives a
    logout/login, works on the phone and can be audited by the super user.

    `source` is either:
      CATALOG      -> the patient searched the pharmacy themselves
      PRESCRIPTION -> the line came from a doctor's prescription entry
    """

    __tablename__ = "pharmacy_cart_items"

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "medicine_id",
            "source",
            name="uq_cart_user_medicine_source"
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
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

    medicine_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey(
            "medicines.id",
            ondelete="CASCADE"
        ),
        nullable=True,
        index=True
    )

    quantity: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False
    )

    # Price copied at the moment of adding, so a later price change cannot
    # silently alter a cart the patient already looked at.
    unit_price: Mapped[float] = mapped_column(
        Numeric(10, 2),
        default=0,
        nullable=False
    )

    source: Mapped[str] = mapped_column(
        String(20),
        default="CATALOG",
        nullable=False
    )

    # Set when the line came from a prescription
    prescription_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey(
            "prescriptions.id",
            ondelete="SET NULL"
        ),
        nullable=True,
        index=True
    )

    prescription_medicine_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey(
            "prescription_medicines.id",
            ondelete="SET NULL"
        ),
        nullable=True,
        index=True
    )

    # Doctor's notes copied into the cart line (printed on the invoice)
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

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    medicine: Mapped["Medicine"] = relationship(  # noqa: F821
        "Medicine",
        lazy="joined"
    )

    @property
    def line_total(self) -> float:
        return round(float(self.unit_price or 0) * int(self.quantity or 0), 2)
