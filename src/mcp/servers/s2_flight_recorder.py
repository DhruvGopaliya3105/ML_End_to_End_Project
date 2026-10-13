"""S2 - Flight Recorder and Safe Recovery MCP (SYSTEM, port 9302).

Reconstructs failed workflows and coordinates safe recovery: verify the
trusted payment status before retrying, use idempotency keys so retries
never duplicate, and record every recovery result.
"""

from datetime import datetime

from src.database.connection import SessionLocal
from src.mcp.server_base import (
    ControlledError,
    build_server,
    mcp_tool,
    serve,
)
from src.models.appointment import Appointment
from src.models.workflow_event import RecoveryAttempt, WorkflowEvent
from src.services import audit_log
from src.services.mcp_rbac import get_server

SERVER = get_server("flight-recorder")
mcp = build_server(SERVER)


@mcp_tool(mcp, SERVER, "reconstruct_event_history")
def reconstruct_event_history(correlation_id: str, principal: dict | None = None,
                              audit_correlation_id: str = "") -> dict:
    """Replay all recorded events sharing one correlation id."""
    db = SessionLocal()
    try:
        events = (
            db.query(WorkflowEvent)
            .filter(WorkflowEvent.correlation_id == correlation_id)
            .order_by(WorkflowEvent.created_at)
            .all()
        )
        return {
            "correlation_id": correlation_id,
            "found": len(events),
            "events": [
                {"ref": f"workflow_events#{e.id}", "at": e.created_at.isoformat(),
                 "type": e.event_type, "workflow": e.workflow_type,
                 "resource": e.resource_ref, "payload": e.payload}
                for e in events
            ],
        }
    finally:
        db.close()


@mcp_tool(mcp, SERVER, "reconcile_failed_workflow")
def reconcile_failed_workflow(correlation_id: str, principal: dict | None = None,
                              audit_correlation_id: str = "") -> dict:
    """Reconcile an incomplete workflow (e.g. payment succeeded but the
    appointment stayed pending).

    Verifies the recorded payment status before retrying, uses an
    idempotency key so retries never duplicate, and records the result.
    Never marks success from an unverified client request.
    """
    db = SessionLocal()
    try:
        events = (
            db.query(WorkflowEvent)
            .filter(WorkflowEvent.correlation_id == correlation_id)
            .order_by(WorkflowEvent.created_at)
            .all()
        )
        if not events:
            raise ControlledError("NOT_FOUND", "no workflow events for this correlation id")
        recovered = []
        for ev in events:
            if ev.workflow_type != "APPOINTMENT" or not ev.resource_ref:
                continue
            try:
                appt_id = int(str(ev.resource_ref).split("#")[-1])
            except ValueError:
                continue
            appt = db.get(Appointment, appt_id)
            if appt is None:
                continue
            idem = f"recover-appointment-{appt.id}"
            existing = (
                db.query(RecoveryAttempt)
                .filter(RecoveryAttempt.idempotency_key == idem)
                .first()
            )
            if existing is not None and existing.status == "SUCCEEDED":
                recovered.append({"appointment_id": appt.id,
                                  "outcome": "already_recovered",
                                  "attempt_id": existing.id})
                continue
            if (appt.payment_status or "").upper() != "PAID":
                attempt = RecoveryAttempt(
                    workflow_event_id=ev.id, correlation_id=correlation_id,
                    incident_type="payment_not_verified", status="ESCALATED",
                    idempotency_key=idem, attempts=1,
                    result={"reason": f"payment_status={appt.payment_status}"},
                )
                db.add(attempt)
                db.commit()
                audit_log.log_event(
                    "workflow_recovery", action="reconcile", result="escalated",
                    resource_type="appointment", resource_ref=f"appointments#{appt.id}",
                    correlation_id=correlation_id,
                    extra={"reason": "payment not verified"},
                )
                recovered.append({"appointment_id": appt.id,
                                  "outcome": "escalated_for_review",
                                  "attempt_id": attempt.id})
                continue
            attempt = RecoveryAttempt(
                workflow_event_id=ev.id, correlation_id=correlation_id,
                incident_type="appointment_update_failed", idempotency_key=idem,
                attempts=1,
            )
            appt.status = "CONFIRMED"
            attempt.status = "SUCCEEDED"
            attempt.completed_at = datetime.utcnow()
            attempt.result = {
                "appointment_id": appt.id,
                "new_status": "CONFIRMED",
                "verified_payment": appt.payment_status,
            }
            db.add(attempt)
            db.add(WorkflowEvent(
                correlation_id=correlation_id, workflow_type="APPOINTMENT",
                resource_type="appointment",
                resource_ref=f"appointments#{appt.id}",
                event_type="RECOVERY", idempotency_key=idem,
                payload={"outcome": "confirmed_after_payment_verification"},
            ))
            db.commit()
            audit_log.log_event(
                "workflow_recovery", action="reconcile", result="success",
                resource_type="appointment", resource_ref=f"appointments#{appt.id}",
                correlation_id=correlation_id,
                extra={"attempt_id": attempt.id},
            )
            recovered.append({"appointment_id": appt.id, "outcome": "recovered",
                              "attempt_id": attempt.id})
        return {"correlation_id": correlation_id, "recovered": recovered}
    finally:
        db.close()


@mcp_tool(mcp, SERVER, "verify_recovery")
def verify_recovery(recovery_attempt_id: int, principal: dict | None = None,
                    audit_correlation_id: str = "") -> dict:
    """Verify the final state after a recovery attempt."""
    db = SessionLocal()
    try:
        attempt = db.get(RecoveryAttempt, recovery_attempt_id)
        if attempt is None:
            raise ControlledError("NOT_FOUND", "recovery attempt not found")
        verified = attempt.status == "SUCCEEDED"
        final_state = None
        if verified and (attempt.result or {}).get("appointment_id"):
            appt = db.get(Appointment, attempt.result["appointment_id"])
            final_state = appt.status if appt else None
            verified = verified and final_state == "CONFIRMED"
        return {
            "attempt_id": attempt.id,
            "status": attempt.status,
            "verified": verified,
            "final_state": final_state,
        }
    finally:
        db.close()


@mcp_tool(mcp, SERVER, "get_incident_timeline")
def get_incident_timeline(incident_id: int, principal: dict | None = None,
                          audit_correlation_id: str = "") -> dict:
    """Full incident timeline: the recovery attempt + related workflow events."""
    db = SessionLocal()
    try:
        attempt = db.get(RecoveryAttempt, incident_id)
        if attempt is None:
            raise ControlledError("NOT_FOUND", "recovery attempt not found")
        events = (
            db.query(WorkflowEvent)
            .filter(WorkflowEvent.correlation_id == attempt.correlation_id)
            .order_by(WorkflowEvent.created_at)
            .all()
        )
        return {
            "incident": {
                "ref": f"recovery_attempts#{attempt.id}",
                "type": attempt.incident_type,
                "status": attempt.status,
                "attempts": attempt.attempts,
                "result": attempt.result,
                "created_at": attempt.created_at.isoformat(),
                "completed_at": attempt.completed_at.isoformat() if attempt.completed_at else None,
            },
            "events": [
                {"ref": f"workflow_events#{e.id}", "at": e.created_at.isoformat(),
                 "type": e.event_type, "workflow": e.workflow_type,
                 "resource": e.resource_ref}
                for e in events
            ],
        }
    finally:
        db.close()


if __name__ == "__main__":
    serve(SERVER, mcp)
