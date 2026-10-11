from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text
)

from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import (
    Mapped,
    mapped_column
)

from src.database.base import Base


class PharmacySnapshot(Base):
    """A point-in-time copy of the pharmacy tables, for controlled rollback.

    How the super user is meant to use it
    -------------------------------------
    * Before any bulk edit (price update, stock import, catalog delete) the
      app takes an automatic snapshot with trigger = AUTO_PRE_BULK.
    * A restore is a two step operation: `preview` first (returns exactly which
      rows would change, nothing is written), then `restore` with the checksum
      echoed back. That stops an accidental click from overwriting the catalog.
    * Before restoring, the current state is snapshotted as PRE_RESTORE, so a
      bad restore can itself be undone.
    * `is_pinned` snapshots are never removed by the "prune old snapshots"
      cleanup.
    """

    __tablename__ = "pharmacy_snapshots"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
    )

    label: Mapped[str] = mapped_column(
        String(160),
        nullable=False
    )

    description: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True
    )

    # PHARMACY (all pharmacy tables) | CATALOG (medicines + diseases)
    # | STOCK (stock numbers only) | ORDERS (orders + items)
    scope: Mapped[str] = mapped_column(
        String(30),
        default="PHARMACY",
        nullable=False
    )

    # JSON: {"medicines": [...], "pharmacy_orders": [...], ...}
    payload_json: Mapped[str] = mapped_column(
        Text().with_variant(LONGTEXT, "mysql"),
        nullable=False
    )

    # JSON: {"medicines": 148, "pharmacy_orders": 12}
    row_counts_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    tables_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    row_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False
    )

    size_bytes: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False
    )

    # sha256 of payload_json - must be sent back to confirm a restore
    checksum: Mapped[str] = mapped_column(
        String(64),
        nullable=False
    )

    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey(
            "users.id",
            ondelete="SET NULL"
        ),
        nullable=True,
        index=True
    )

    created_by_name: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True
    )

    created_by_role: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True
    )

    # MANUAL | AUTO_PRE_BULK | PRE_RESTORE | PRE_DELETE
    trigger: Mapped[str] = mapped_column(
        String(20),
        default="MANUAL",
        nullable=False
    )

    # Pinned snapshots survive cleanup; also used to mark a "good state"
    is_pinned: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False
    )

    restore_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False
    )

    last_restored_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )

    last_restored_by: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        index=True
    )
