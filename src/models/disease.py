from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Integer,
    String,
    Text
)

from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship
)

from src.database.base import Base


class Disease(Base):
    """Disease / symptom category used to filter the pharmacy catalog.

    /pharmacy?disease=diabetes shows every medicine linked to this row
    through `src/models/medicine_disease.py`.
    """

    __tablename__ = "diseases"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
    )

    # Display name, e.g. "Diabetes"
    name: Mapped[str] = mapped_column(
        String(120),
        unique=True,
        index=True,
        nullable=False
    )

    # URL friendly key, e.g. "diabetes"
    slug: Mapped[str] = mapped_column(
        String(120),
        unique=True,
        index=True,
        nullable=False
    )

    # Grouping header shown above the chips, e.g. "Chronic Care"
    group_name: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    # Small emoji used on the category chips
    icon: Mapped[str | None] = mapped_column(
        String(16),
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

    # Link rows (use `.medicine` on each link to get the product itself).
    # Filtering by disease is done with a JOIN in pharmacy_catalog_service.
    links: Mapped[list["MedicineDisease"]] = relationship(  # noqa: F821
        back_populates="disease",
        cascade="all, delete-orphan"
    )
