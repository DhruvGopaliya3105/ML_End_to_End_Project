"""MCP server registry - one row per logical MCP server (exactly 10)."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base


class McpServer(Base):
    """The registry row for one logical MCP server.

    The canonical catalog (ports, service identities, tools, roles) lives in
    ``src/services/mcp_rbac.py``; ``seed_mcp_registry`` upserts it here so the
    FastAPI gateway, the admin page and health checks all read one table.
    """

    __tablename__ = "mcp_servers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # e.g. "care-gap-intelligence" - the gateway and RBAC key on this name
    name: Mapped[str] = mapped_column(String(60), unique=True, index=True, nullable=False)
    # U1..U5 | A1..A3 | S1..S2
    group_code: Mapped[str] = mapped_column(String(4), index=True, nullable=False)
    # USER | ADMIN | SYSTEM
    category: Mapped[str] = mapped_column(String(10), index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # streamable-HTTP endpoint, e.g. http://127.0.0.1:9101/mcp
    base_url: Mapped[str] = mapped_column(String(120), nullable=False)
    # distinct service identity for service-to-service authentication
    service_identity: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    # tool names this server exposes
    tools: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # roles allowed to call this server at all
    required_roles: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # ONLINE | OFFLINE | DEGRADED
    status: Mapped[str] = mapped_column(String(12), default="OFFLINE", nullable=False)
    last_health_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
