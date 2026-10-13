"""MCP gateway - the only door between browsers and the 10 MCP servers.

Every browser request passes through FastAPI. The gateway:

* authenticates against the server-side session and authorizes with
  ``check_tool_access`` (defense in depth - every MCP server re-checks),
* propagates the verified principal + correlation ID to the tool,
* enforces timeouts and maps failures to controlled statuses,
* logs every call to ``mcp_gateway_audit`` and mirrors it to the DB.

Controlled statuses: NOT_FOUND, ACCESS_DENIED, CONFLICT,
SOURCE_UNAVAILABLE, INTERNAL_ERROR. Never a stack trace, never fake data.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from sqlalchemy.orm import Session

from src.models.mcp_registry import McpServer
from src.models.user import User
from src.security.rbac import user_role
from src.services import audit_log
from src.services.audit_context import get_correlation_id
from src.services.mcp_rbac import (
    SERVER_CATALOG,
    check_tool_access,
    get_server,
    mirror_audit_event,
    record_security_event,
)

MCP_CALL_TIMEOUT = float(os.environ.get("MCP_CALL_TIMEOUT", "15"))
MCP_HEALTH_TIMEOUT = float(os.environ.get("MCP_HEALTH_TIMEOUT", "5"))
SERVICE_TOKEN = os.environ.get("MCP_SERVICE_TOKEN", "dev-mcp-service-token")


def _client_for(entry: dict) -> Client:
    url = entry.get("base_url") or f"http://127.0.0.1:{entry['port']}/mcp"
    return Client(StreamableHttpTransport(
        url,
        headers={"X-MCP-Service-Token": SERVICE_TOKEN},
    ))


def _principal_for(user: User | None) -> dict:
    return {
        "email": getattr(user, "email", None),
        "role": user_role(user) if user else None,
        "user_id": getattr(user, "id", None),
    }


def _result_data(res) -> dict:
    data = getattr(res, "data", None)
    if data is not None:
        return data
    return json.loads(res.content[0].text)


async def call_tool(
    db: Session,
    user: User | None,
    server_name: str,
    tool_name: str,
    params: dict | None = None,
) -> dict:
    """Call one MCP tool with the verified principal. Controlled errors only."""
    params = dict(params or {})
    principal = _principal_for(user)

    entry = get_server(server_name)
    if entry is None:
        return {"success": False, "status": "NOT_FOUND",
                "error": f"Unknown MCP server: {server_name}"}
    if tool_name not in entry["tools"]:
        return {"success": False, "status": "NOT_FOUND",
                "error": f"Unknown tool '{tool_name}' on server '{server_name}'"}

    # defense in depth: authorize at the gateway too (the server re-checks)
    allowed, reason = check_tool_access(
        db, user, server_name, tool_name,
        patient_id=params.get("patient_id"),
    )
    if not allowed:
        record_security_event(
            db, action="access_denied", actor=principal["email"],
            role=principal["role"], resource_type="mcp_tool",
            resource_ref=f"{server_name}.{tool_name}",
            details={"reason": reason, "via": "gateway"},
        )
        audit_log.log_event(
            "mcp_gateway_audit", mcp_server=server_name, tool=tool_name,
            action="gateway_call", result="denied", actor=principal["email"],
            role=principal["role"], error_category="ACCESS_DENIED",
        )
        return {"success": False, "status": "ACCESS_DENIED", "error": reason}

    started = time.perf_counter()
    payload = {
        **params,
        "principal": principal,
        "audit_correlation_id": get_correlation_id(),
    }
    try:
        async with _client_for(entry) as client:
            res = await asyncio.wait_for(
                client.call_tool(tool_name, payload),
                timeout=MCP_CALL_TIMEOUT,
            )
        data = _result_data(res)
    except asyncio.TimeoutError:
        audit_log.log_event(
            "mcp_gateway_audit", mcp_server=server_name, tool=tool_name,
            action="gateway_call", result="error", actor=principal["email"],
            role=principal["role"], error_category="TIMEOUT",
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )
        return {"success": False, "status": "SOURCE_UNAVAILABLE",
                "error": "The MCP service did not respond in time."}
    except Exception as exc:
        audit_log.log_event(
            "mcp_gateway_audit", mcp_server=server_name, tool=tool_name,
            action="gateway_call", result="error", actor=principal["email"],
            role=principal["role"], error_category=type(exc).__name__,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )
        return {"success": False, "status": "SOURCE_UNAVAILABLE",
                "error": "The MCP service is unavailable right now.",
                "error_category": type(exc).__name__}

    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    ok = bool(data.get("success", True))
    record = audit_log.log_event(
        "mcp_gateway_audit", mcp_server=server_name, tool=tool_name,
        action="gateway_call",
        result="success" if ok else (data.get("status") or "error"),
        actor=principal["email"], role=principal["role"],
        duration_ms=duration_ms,
    )
    mirror_audit_event(db, record)
    return data


async def _ping(entry: dict) -> tuple[str, str | None]:
    try:
        async with _client_for(entry) as client:
            res = await asyncio.wait_for(
                client.call_tool("health_check", {}),
                timeout=MCP_HEALTH_TIMEOUT,
            )
            health = _result_data(res)
            return ("ONLINE" if health.get("status") == "online" else "DEGRADED"), None
    except Exception as exc:
        return "OFFLINE", type(exc).__name__


async def refresh_health(db: Session) -> list[dict]:
    """Ping every server's health_check (concurrently) and update the registry."""
    results = await asyncio.gather(*(_ping(entry) for entry in SERVER_CATALOG))
    out = []
    for entry, (status, last_error) in zip(SERVER_CATALOG, results):
        try:
            row = db.query(McpServer).filter(McpServer.name == entry["name"]).first()
            if row is not None:
                row.status = status
                row.last_health_at = datetime.utcnow()
                row.last_error = last_error
                db.commit()
        except Exception:
            db.rollback()
        out.append({
            "name": entry["name"],
            "group": entry["group"],
            "category": entry["category"],
            "port": entry["port"],
            "service_identity": entry["service_identity"],
            "tools": entry["tools"],
            "required_roles": entry["required_roles"],
            "status": status,
            "last_error": last_error,
            "checked_at": datetime.utcnow().isoformat(),
        })
    return out
