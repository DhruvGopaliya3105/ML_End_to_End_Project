from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint
)

from sqlalchemy.orm import (
    Mapped,
    mapped_column
)

from src.database.base import Base


class RolePermission(Base):
    """Role -> permission switch the super user can flip from the admin UI.

    The default matrix lives in ``src/security/rbac.py`` so the app stays
    correct on a fresh database. A row here *overrides* that default for one
    role, which is how you temporarily allow a pharmacist to edit prices, or
    freeze a role out of ordering, without touching code.

    SUPERUSER can never be locked out: ``pharmacy.*`` is always allowed for it
    even if someone inserts a deny row.
    """

    __tablename__ = "role_permissions"

    __table_args__ = (
        UniqueConstraint(
            "role",
            "permission",
            name="uq_role_permission"
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
    )

    # PATIENT | DOCTOR | PHARMACIST | STAFF | ADMIN | SUPERUSER
    role: Mapped[str] = mapped_column(
        String(20),
        index=True,
        nullable=False
    )

    # Permission key from rbac.PERMISIONS, e.g. "pharmacy.catalog.write"
    permission: Mapped[str] = mapped_column(
        String(80),
        nullable=False
    )

    is_allowed: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False
    )

    note: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True
    )

    updated_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey(
            "users.id",
            ondelete="SET NULL"
        ),
        nullable=True
    )

    updated_by_name: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )
