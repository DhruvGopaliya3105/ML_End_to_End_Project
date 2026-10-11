from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
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


class Medicine(Base):
    """One product in the pharmacy catalog (tablet, capsule, syrup ...).

    `price` is what the patient pays, `mrp` is printed on the strip and is only
    used to show the "you save X%" badge. Stock is the number of packs this
    app can sell; it is decreased when an order is confirmed and given back
    when an order is cancelled or refunded.
    """

    __tablename__ = "medicines"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
    )

    # Shop code, unique. Auto generated as MED-0001 when left empty.
    sku: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        index=True,
        nullable=False
    )

    # Product name as printed, e.g. "Dolo 650 Tablet"
    name: Mapped[str] = mapped_column(
        String(200),
        index=True,
        nullable=False
    )

    # Salt / composition, e.g. "Paracetamol 650 mg"
    generic_name: Mapped[str | None] = mapped_column(
        String(200),
        index=True,
        nullable=True
    )

    brand: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True
    )

    # TABLET | CAPSULE | SYRUP | DROPS | INJECTION | OINTMENT | SPRAY |
    # POWDER | Sachet | DEVICE
    form: Mapped[str] = mapped_column(
        String(40),
        default="TABLET",
        nullable=False
    )

    # e.g. "650 mg"
    strength: Mapped[str | None] = mapped_column(
        String(60),
        nullable=True
    )

    # e.g. "Strip of 15 tablets" / "200 ml bottle"
    pack_size: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True
    )

    # Selling price per pack
    price: Mapped[float] = mapped_column(
        Numeric(10, 2),
        default=0,
        nullable=False
    )

    # Maximum retail price per pack
    mrp: Mapped[float | None] = mapped_column(
        Numeric(10, 2),
        nullable=True
    )

    # Packs available in our pharmacy
    stock: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False
    )

    # Below this number the super user is warned on the admin dashboard
    low_stock_alert: Mapped[int] = mapped_column(
        Integer,
        default=10,
        nullable=False
    )

    # True -> patient must have a prescription entry for it before buying
    requires_prescription: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False
    )

    # Schedule H/H1 style warning text
    warning: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True
    )

    # Relative path under /static (e.g. "images/pharmacy/tablet.png")
    image_path: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True
    )

    # Optional full URL to a real product photo, wins over image_path
    image_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    # How to take it, e.g. "After food, twice a day for 5 days"
    dosage_info: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    side_effects: Mapped[str | None] = mapped_column(
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

    diseases: Mapped[list["MedicineDisease"]] = relationship(  # noqa: F821
        back_populates="medicine",
        cascade="all, delete-orphan"
    )

    @property
    def available(self) -> bool:
        return self.is_active and (self.stock or 0) > 0

    @property
    def display_image(self) -> str:
        """Absolute URL the template should use for the product photo."""

        if self.image_url:
            return self.image_url

        if self.image_path:
            path = self.image_path
            if not path.startswith("/"):
                path = f"/static/{path.lstrip('/')}"
            return path

        return "/static/images/pharmacy/not-found.svg"
