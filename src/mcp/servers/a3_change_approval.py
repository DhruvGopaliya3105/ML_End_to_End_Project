"""A3 - Change Impact and Approval MCP (ADMIN, port 9203).

Previews and controls important system changes. Preview never executes;
approval is verified server-side; the requester must not approve their own
privileged action.
"""

from datetime import date

from src.database.connection import SessionLocal
from src.mcp.server_base import (
    ControlledError,
    build_server,
    mcp_tool,
    serve,
)
from src.models.appointment import Appointment
from src.models.change_request import ChangeApproval, ChangeRequest
from src.models.doctor import Doctor
from src.services import audit_log
from src.services.mcp_rbac import get_server

SERVER = get_server("change-approval")
mcp = build_server(SERVER)

_ACTIVE = ("CONFIRMED", "PENDING")


def _preview(db, change: dict) -> dict:
    change = dict(change or {})
    ctype = change.get("change_type")
    if ctype == "doctor_deactivation":
        doctor = db.get(Doctor, change.get("doctor_id"))
        if doctor is None:
            raise ControlledError("NOT_FOUND", "doctor not found")
        upcoming = (
            db.query(Appointment)
            .filter(Appointment.doctor_id == doctor.id,
                    Appointment.appointment_date >= date.today(),
                    Appointment.status.in_(_ACTIVE))
            .count()
        )
        return {
            "change_type": ctype,
            "target": f"doctors#{doctor.id}",
            "would_affect": {"upcoming_appointments": upcoming},
            "dependencies": ["appointments", "doctor_schedules", "doctor_slots"],
        }
    if ctype == "role_change":
        return {
            "change_type": ctype,
            "target": change.get("target"),
            "would_affect": {"note": "review the role-permission matrix before applying"},
            "dependencies": ["role_permissions", "rbac defaults"],
        }
    return {
        "change_type": ctype or "custom",
        "would_affect": {"note": "no specific impact model - review manually"},
        "dependencies": [],
    }


@mcp_tool(mcp, SERVER, "preview_change_impact")
def preview_change_impact(change: dict, principal: dict | None = None,
                          audit_correlation_id: str = "") -> dict:
    """Preview a change's impact WITHOUT executing it."""
    db = SessionLocal()
    try:
        impact = _preview(db, change)
        return {"executed": False, "impact": impact,
                "note": "Preview only - nothing was changed."}
    finally:
        db.close()


@mcp_tool(mcp, SERVER, "request_approval")
def request_approval(change: dict, principal: dict | None = None,
                     audit_correlation_id: str = "") -> dict:
    """Create a PENDING change request with its impact preview attached."""
    db = SessionLocal()
    try:
        change = dict(change or {})
        impact = _preview(db, change)
        cr = ChangeRequest(
            change_type=change.get("change_type", "custom"),
            description=change.get("description"),
            proposed_by=(principal or {}).get("email"),
            impact_preview=impact,
            rollback_plan=change.get("rollback_plan"),
        )
        db.add(cr)
        db.commit()
        audit_log.log_event(
            "change_approval", action="change_requested",
            actor=(principal or {}).get("email"),
            resource_type="change_request",
            resource_ref=f"change_requests#{cr.id}",
            result="success",
            extra={"change_type": cr.change_type, "status": cr.status},
        )
        return {"change_request_id": cr.id, "status": cr.status}
    finally:
        db.close()


@mcp_tool(mcp, SERVER, "verify_rollback_plan")
def verify_rollback_plan(change_request_id: int, principal: dict | None = None,
                         audit_correlation_id: str = "") -> dict:
    """Verify a change request has a feasible rollback plan."""
    db = SessionLocal()
    try:
        cr = db.get(ChangeRequest, change_request_id)
        if cr is None:
            raise ControlledError("NOT_FOUND", "change request not found")
        checks = {
            "has_rollback_plan": bool((cr.rollback_plan or "").strip()),
            "has_before_snapshot": cr.before_data is not None,
            "impact_previewed": cr.impact_preview is not None,
        }
        return {
            "change_request_id": cr.id,
            "rollback_feasible": all(checks.values()),
            "checks": checks,
        }
    finally:
        db.close()


@mcp_tool(mcp, SERVER, "get_change_history")
def get_change_history(limit: int = 50, principal: dict | None = None,
                       audit_correlation_id: str = "") -> dict:
    """Change requests with their approval decisions."""
    db = SessionLocal()
    try:
        rows = (
            db.query(ChangeRequest)
            .order_by(ChangeRequest.created_at.desc())
            .limit(limit)
            .all()
        )
        out = []
        for cr in rows:
            approvals = (
                db.query(ChangeApproval)
                .filter(ChangeApproval.change_request_id == cr.id)
                .all()
            )
            out.append({
                "ref": f"change_requests#{cr.id}",
                "change_type": cr.change_type,
                "status": cr.status,
                "proposed_by": cr.proposed_by,
                "created_at": cr.created_at.isoformat(),
                "approvals": [
                    {"approver": a.approver, "decision": a.decision,
                     "decided_at": a.decided_at.isoformat()}
                    for a in approvals
                ],
            })
        return {"change_requests": out}
    finally:
        db.close()


if __name__ == "__main__":
    serve(SERVER, mcp)
