"""Shared factory for the 10 MCP servers.

Every server is independently identifiable and has:

* its own FastMCP instance + tool namespace (``build_server``),
* a ``health_check`` + ``server_info`` tool (the registry reads these),
* per-tool authorization + audit (``mcp_tool``),
* service-to-service auth on its HTTP port (``ServiceTokenAuthMiddleware``).

Tool functions keep their natural signature (patient_id, principal,
audit_correlation_id, ...) - the MCP schema is generated from it. The
wrapper adds: principal resolution, RBAC (deny by default), audit events
(mcp_tool_events stream + DB mirror), controlled errors and timing.
"""

from __future__ import annotations

import functools
import os
import time
from datetime import datetime

import uvicorn
from fastmcp import FastMCP

from src.database.connection import SessionLocal
from src.models.mcp_registry import McpServer
from src.models.user import User
from src.services import audit_log
from src.services.mcp_rbac import (
    check_tool_access,
    enforce_patient_scope,
    get_tool_scope,
    mirror_audit_event,
    record_security_event,
)

DEFAULT_SERVICE_TOKEN = "dev-mcp-service-token"


class ControlledError(Exception):
    """A tool-level controlled failure (ACCESS_DENIED, NOT_FOUND, ...)."""

    def __init__(self, status: str, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class ServiceTokenAuthMiddleware:
    """Service-to-service auth: every request needs the shared token.

    The FastAPI gateway sends ``X-MCP-Service-Token``; browsers never have
    it, so the internal MCP ports stay unreachable from the outside - even
    though they listen on localhost only.
    """

    def __init__(self, app, token: str):
        self.app = app
        self.token = token

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = {
                k.decode().lower(): v.decode() for k, v in scope.get("headers", [])
            }
            if headers.get("x-mcp-service-token") != self.token:
                audit_log.log_security_event(
                    action="service_auth_failure",
                    result="denied",
                    actor="anonymous-service",
                    resource_type="mcp_server",
                    resource_ref=str(scope.get("path", "")),
                    extra={"reason": "missing or invalid service token"},
                )
                body = b'{"error":"unauthorized","message":"Missing or invalid MCP service token."}'
                await send({
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode()),
                    ],
                })
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)


def _resolve_user(db, principal: dict | None) -> User | None:
    email = (principal or {}).get("email")
    if not email:
        return None
    return db.query(User).filter(User.email == email).first()


def require_patient(db, principal: dict | None, patient_id: int) -> User:
    """Resolve + authorize a patient scope; raises ControlledError otherwise."""
    user = _resolve_user(db, principal)
    if user is None or not enforce_patient_scope(db, user, patient_id):
        raise ControlledError(
            "ACCESS_DENIED",
            "Access denied: patient record outside your authorized scope.",
        )
    patient = db.get(User, int(patient_id))
    if patient is None:
        raise ControlledError("NOT_FOUND", "patient not found")
    return patient


def build_patient_timeline(db, patient_id: int) -> list[dict]:
    """Chronological journey from verified records.

    Every entry carries its source record reference and recorded timestamp -
    nothing is invented.
    """
    from src.models.appointment import Appointment
    from src.models.follow_up import FollowUp
    from src.models.medical_record import MedicalRecord
    from src.models.prescription import Prescription
    from src.models.treatment import Treatment

    events: list[dict] = []

    def at(value):
        return (value or datetime.utcnow()).isoformat()

    for a in db.query(Appointment).filter(Appointment.patient_id == patient_id).all():
        events.append({
            "at": at(getattr(a, "created_at", None)),
            "kind": "appointment",
            "ref": f"appointments#{a.id}",
            "summary": f"Appointment #{a.id} - {a.status} - {a.appointment_date}",
        })
    for r in db.query(MedicalRecord).filter(MedicalRecord.patient_id == patient_id).all():
        events.append({
            "at": at(getattr(r, "created_at", None)),
            "kind": "visit",
            "ref": f"medical_records#{r.id}",
            "summary": f"Visit on {r.visit_date} - {r.diagnosis_notes or 'no diagnosis recorded'}",
        })
    for p in db.query(Prescription).filter(Prescription.patient_id == patient_id).all():
        events.append({
            "at": at(getattr(p, "created_at", None)),
            "kind": "prescription",
            "ref": f"prescriptions#{p.id}",
            "summary": f"Prescription #{p.id} - {p.diagnosis or 'no diagnosis recorded'}",
        })
    for fu in db.query(FollowUp).filter(FollowUp.patient_id == patient_id).all():
        events.append({
            "at": at(getattr(fu, "created_at", None)),
            "kind": "follow_up",
            "ref": f"follow_ups#{fu.id}",
            "summary": f"Follow-up #{fu.id} - {fu.follow_up_date} - {fu.status}",
        })
    for tr in db.query(Treatment).filter(Treatment.patient_id == patient_id).all():
        events.append({
            "at": at(getattr(tr, "created_at", None)),
            "kind": "treatment",
            "ref": f"treatments#{tr.id}",
            "summary": f"Treatment '{tr.treatment_name}' - {tr.status}",
        })
    events.sort(key=lambda e: e["at"])
    return events


def build_server(entry: dict) -> FastMCP:
    """Create one MCP server: identity + health_check + server_info tools."""
    mcp = FastMCP(name=entry["name"], instructions=entry["description"])

    @mcp.tool()
    def health_check() -> dict:
        """Liveness + identity for this MCP server (the registry reads this)."""
        db = SessionLocal()
        try:
            row = db.query(McpServer).filter(McpServer.name == entry["name"]).first()
            if row is not None:
                row.status = "ONLINE"
                row.last_health_at = datetime.utcnow()
                row.last_error = None
                db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()
        return {
            "server": entry["name"],
            "group": entry["group"],
            "category": entry["category"],
            "service_identity": entry["service_identity"],
            "status": "online",
            "tools": entry["tools"],
            "checked_at": datetime.utcnow().isoformat(),
        }

    @mcp.tool()
    def server_info() -> dict:
        """Permission requirements and audit context for this server."""
        return {
            "server": entry["name"],
            "category": entry["category"],
            "required_roles": entry["required_roles"],
            "tools": entry["tools"],
            "scope": get_tool_scope(entry["name"]),
            "audit_stream": "mcp_tool_events",
            "health_tool": "health_check",
        }

    return mcp


def _invoke_tool(entry: dict, tool_name: str, fn, args, kwargs) -> dict:
    """RBAC + audit + controlled errors around one tool call."""
    kwargs = dict(kwargs)
    # peek (not pop): the tool impl also receives principal +
    # audit_correlation_id - the wrapper only reads them for RBAC/audit
    principal = kwargs.get("principal") or {}
    audit_correlation_id = kwargs.get("audit_correlation_id") or ""
    started = time.perf_counter()
    server_name = entry["name"]
    actor = principal.get("email")
    role = principal.get("role")

    db = SessionLocal()
    try:
        user = _resolve_user(db, principal)
        allowed, reason = check_tool_access(
            db, user, server_name, tool_name,
            patient_id=kwargs.get("patient_id"),
        )
        if not allowed:
            record_security_event(
                db, action="access_denied", actor=actor, role=role,
                resource_type="mcp_tool",
                resource_ref=f"{server_name}.{tool_name}",
                details={"reason": reason},
            )
            audit_log.log_event(
                "mcp_tool_events", mcp_server=server_name, tool=tool_name,
                action="tool_call", result="denied", actor=actor, role=role,
                correlation_id=audit_correlation_id or None,
                error_category="ACCESS_DENIED",
            )
            return {"success": False, "status": "ACCESS_DENIED", "error": reason}

        try:
            result = fn(*args, **kwargs)
        except ControlledError as exc:
            audit_log.log_event(
                "mcp_tool_events", mcp_server=server_name, tool=tool_name,
                action="tool_call", result="denied", actor=actor, role=role,
                correlation_id=audit_correlation_id or None,
                error_category=exc.status,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )
            return {"success": False, "status": exc.status, "error": exc.message}
        except Exception as exc:  # controlled failure - never a stack trace
            audit_log.log_event(
                "mcp_tool_events", mcp_server=server_name, tool=tool_name,
                action="tool_call", result="error", actor=actor, role=role,
                correlation_id=audit_correlation_id or None,
                error_category=type(exc).__name__,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )
            return {
                "success": False, "status": "INTERNAL_ERROR",
                "error": "Internal error", "error_category": type(exc).__name__,
            }

        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        record = audit_log.log_event(
            "mcp_tool_events", mcp_server=server_name, tool=tool_name,
            action="tool_call", result="success", actor=actor, role=role,
            correlation_id=audit_correlation_id or None, duration_ms=duration_ms,
        )
        mirror_audit_event(db, record)
        if isinstance(result, dict):
            return {"success": True, **result}
        return {"success": True, "result": result}
    finally:
        db.close()


def mcp_tool(mcp: FastMCP, entry: dict, tool_name: str):
    """Decorator: register fn as an MCP tool with RBAC + audit + control.

    The tool's own signature is preserved for the MCP schema (functools.wraps
    keeps __wrapped__, which inspect.signature follows).
    """

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            return _invoke_tool(entry, tool_name, fn, args, kwargs)

        return mcp.tool(name=tool_name, description=(fn.__doc__ or "").strip())(wrapper)

    return decorator


def serve(entry: dict, mcp: FastMCP) -> None:
    """Run one server on its own port behind service-token auth (blocking).

    Servers bind 127.0.0.1 on purpose: they are internal services and must
    never be exposed to browsers - the FastAPI gateway is the only door.
    """
    app = mcp.http_app()
    token = os.environ.get("MCP_SERVICE_TOKEN", DEFAULT_SERVICE_TOKEN)
    app = ServiceTokenAuthMiddleware(app, token)
    audit_log.log_event(
        "application", action="mcp_server_start",
        extra={"server": entry["name"], "port": entry["port"],
               "service_identity": entry["service_identity"]},
    )
    uvicorn.run(app, host="127.0.0.1", port=entry["port"], log_level="warning")
