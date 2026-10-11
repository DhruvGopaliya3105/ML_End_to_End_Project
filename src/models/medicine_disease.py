from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    UniqueConstraint
)

from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship
)

from src.database.base import Base


class MedicineDisease(Base):
    """Links one medicine to one disease it is used for.

    A medicine can treat several diseases (Paracetamol -> Fever and Headache),
    and one disease can have many medicines, so this is the many-to-many table.
    """

    __tablename__ = "medicine_diseases"

    __table_args__ = (
        UniqueConstraint(
            "medicine_id",
            "disease_id",
            name="uq_medicine_disease"
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
    )

    medicine_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(
            "medicines.id",
            ondelete="CASCADE"
        ),
        nullable=False,
        index=True
    )

    disease_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(
            "diseases.id",
            ondelete="CASCADE"
        ),
        nullable=False,
        index=True
    )

    # First match shown on the card
    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )

    medicine: Mapped["Medicine"] = relationship(  # noqa: F821
        back_populates="diseases"
    )

    disease: Mapped["Disease"] = relationship(  # noqa: F821
        back_populates="links"
    )
