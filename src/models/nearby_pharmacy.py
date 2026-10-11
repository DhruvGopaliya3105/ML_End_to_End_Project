from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
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


class NearbyPharmacy(Base):
    """A chemist shop around the clinic.

    Two kinds of rows live here:

    1. `is_partner = True`  -> our own tie-up, stock numbers are real because
       `NearbyPharmacyStock` is maintained by the super user. These are what
       the emergency "buy it next door" list shows first.
    2. `is_partner = False` -> shops imported from the Google Places API
       (24x7, ratings, phone, map link). Imported rows are kept so the same
       search is instant (and works offline) the next time.

    Either way the patient gets a Call button and a Google Maps route link.
    """

    __tablename__ = "nearby_pharmacies"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
    )

    name: Mapped[str] = mapped_column(
        String(200),
        index=True,
        nullable=False
    )

    address: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True
    )

    area: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True
    )

    city: Mapped[str] = mapped_column(
        String(120),
        default="Jaipur",
        nullable=False
    )

    pincode: Mapped[str | None] = mapped_column(
        String(12),
        nullable=True
    )

    phone: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True
    )

    whatsapp: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True
    )

    latitude: Mapped[float | None] = mapped_column(
        Float,
        nullable=True
    )

    longitude: Mapped[float | None] = mapped_column(
        Float,
        nullable=True
    )

    # Radius we advertise to the patient, filled in by the app when it
    # calculates distance from the clinic/patient coordinates
    distance_km: Mapped[float | None] = mapped_column(
        Float,
        nullable=True
    )

    open_24x7: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False
    )

    # "10:00 AM - 11:00 PM" style text from Google / the shop owner
    opening_hours: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True
    )

    rating: Mapped[float | None] = mapped_column(
        Float,
        nullable=True
    )

    is_partner: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False
    )

    # Google Maps place id, prevents importing the same shop twice
    google_place_id: Mapped[str | None] = mapped_column(
        String(120),
        unique=True,
        nullable=True
    )

    # OFFLINE / IN_SYNC / STALE  (set by the import job)
    sync_status: Mapped[str] = mapped_column(
        String(20),
        default="MANUAL",
        nullable=False
    )

    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )

    notes: Mapped[str | None] = mapped_column(
        String(500),
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

    stocks: Mapped[list["NearbyPharmacyStock"]] = relationship(
        back_populates="pharmacy",
        cascade="all, delete-orphan",
        lazy="selectin"
    )

    @property
    def maps_link(self) -> str:
        """Google Maps directions link (works even without an API key)."""

        if self.latitude is not None and self.longitude is not None:
            return (
                "https://www.google.com/maps/dir/?api=1"
                f"&destination={self.latitude},{self.longitude}"
            )

        from urllib.parse import quote

        return (
            "https://www.google.com/maps/search/?api=1"
            f"&query={quote(self.name + ' ' + (self.address or ''))}"
        )

    @property
    def tel_link(self) -> str | None:
        if not self.phone:
            return None
        digits = "".join(ch for ch in self.phone if ch.isdigit() or ch == "+")
        return f"tel:{digits}" if digits else None


class NearbyPharmacyStock(Base):
    """"Does this shop have this tablet right now?" - kept in SQL.

    This is what makes the emergency fallback work with no Google key and no
    internet: the super user maintains partner stock, the patient sees it.
    """

    __tablename__ = "nearby_pharmacy_stocks"

    __table_args__ = (
        UniqueConstraint(
            "pharmacy_id",
            "medicine_id",
            name="uq_nearby_pharmacy_medicine"
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
    )

    pharmacy_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(
            "nearby_pharmacies.id",
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

    # Free text for shops that stock a medicine we do not sell
    medicine_label: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True
    )

    stock: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False
    )

    price: Mapped[float | None] = mapped_column(
        Numeric(10, 2),
        nullable=True
    )

    # How the app should treat this row: VERIFIED (owner reported) or
    # ESTIMATED (auto filled from Google review text, never shown as a promise)
    trust: Mapped[str] = mapped_column(
        String(20),
        default="VERIFIED",
        nullable=False
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    pharmacy: Mapped[NearbyPharmacy] = relationship(
        back_populates="stocks"
    )

    medicine: Mapped["Medicine"] = relationship("Medicine")  # noqa: F821
