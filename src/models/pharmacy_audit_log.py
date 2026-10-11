from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
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


class PharmacyAuditLog(Base):
    """Append-only trail of everything that touched the pharmacy.

    Who (user id + role + name), what (action + entity + id), when, from
    where (ip / user agent / path), and - for writes - the row before and
    after the change so the super user can prove what happened and decide
    whether a rollback is needed.

    Nothing in the app updates or deletes these rows on purpose.
    """

    __tablename__ = "pharmacy_audit_logs"

    __table_args__ = (
        Index(
            "ix_pharmacy_audit_created",
            "created_at"
        ),
        Index(
            "ix_pharmacy_audit_entity",
            "entity_type",
            "entity_id"
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
    )

    # INFO | WARN | CRITICAL
    severity: Mapped[str] = mapped_column(
        String(10),
        default="INFO",
        nullable=False
    )

    # e.g. "pharmacy.order.create", "pharmacy.medicine.update",
    # "pharmacy.snapshot.restore", "auth.login"
    action: Mapped[str] = mapped_column(
        String(80),
        index=True,
        nullable=False
    )

    # e.g. "medicine" | "order" | "cart" | "nearby_pharmacy" | "snapshot"
    entity_type: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True
    )

    entity_id: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True
    )

    # One line a human can read in the admin table
    description: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True
    )

    actor_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey(
            "users.id",
            ondelete="SET NULL"
        ),
        nullable=True,
        index=True
    )

    actor_name: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True
    )

    actor_role: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True
    )

    # JSON strings (Text everywhere, LONGTEXT on MySQL) - null on reads
    before_json: Mapped[str | None] = mapped_column(
        Text().with_variant(LONGTEXT, "mysql"),
        nullable=True
    )

    after_json: Mapped[str | None] = mapped_column(
        Text().with_variant(LONGTEXT, "mysql"),
        nullable=True
    )

    # Was a snapshot taken that can undo this action?
    rollback_available: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False
    )

    snapshot_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey(
            "pharmacy_snapshots.id",
            ondelete="SET NULL"
        ),
        nullable=True,
        index=True
    )

    ip_address: Mapped[str | None] = mapped_column(
        String(60),
        nullable=True
    )

    user_agent: Mapped[str | None] = mapped_column(
        String(300),
        nullable=True
    )

    request_path: Mapped[str | None] = mapped_column(
        String(300),
        nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )
