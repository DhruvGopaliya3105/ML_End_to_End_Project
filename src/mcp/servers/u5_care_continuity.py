"""U5 - Personal Care Continuity MCP (USER, port 9105, svc-u5-continuity).

Helps patients understand their recorded next steps. Never prescribes,
alters dosages, diagnoses or recommends stopping treatment.
"""

from src.database.connection import SessionLocal
from src.mcp.server_base import (
    build_server,
    mcp_tool,
    require_patient,
    serve,
)
from src.models.appointment import Appointment
from src.models.care_gap import CareGap
from src.models.follow_up import FollowUp
from src.models.notification import Notification
from src.models.treatment import Treatment
from src.services.mcp_rbac import get_server

SERVER = get_server("care-continuity")
mcp = build_server(SERVER)

_DONE = ("DONE", "COMPLETED")


@mcp_tool(mcp, SERVER, "get_pending_care_steps")
def get_pending_care_steps(patient_id: int, principal: dict | None = None,
                           audit_correlation_id: str = "") -> dict:
    """Pending follow-ups and incomplete administrative steps."""
    db = SessionLocal()
    try:
        require_patient(db, principal, patient_id)
        pending_followups = (
            db.query(FollowUp)
            .filter(FollowUp.patient_id == patient_id,
                    FollowUp.status.notin_(_DONE))
            .all()
        )
        open_gaps = (
            db.query(CareGap)
            .filter(CareGap.patient_id == patient_id, CareGap.status == "OPEN")
            .all()
        )
        active_treatments = (
            db.query(Treatment)
            .filter(Treatment.patient_id == patient_id,
                    Treatment.status.notin_(_DONE))
            .all()
        )
        return {
            "patient_id": patient_id,
            "pending_followups": [
                {"ref": f"follow_ups#{fu.id}", "due": str(fu.follow_up_date),
                 "status": fu.status, "reason": fu.reason}
                for fu in pending_followups
            ],
            "open_care_gaps": [
                {"ref": f"care_gaps#{g.id}", "type": g.gap_type,
                 "severity": g.severity, "description": g.description}
                for g in open_gaps
            ],
            "active_treatments": [
                {"ref": f"treatments#{t.id}", "name": t.treatment_name,
                 "status": t.status, "end_date": str(t.end_date) if t.end_date else None}
                for t in active_treatments
            ],
        }
    finally:
        db.close()


@mcp_tool(mcp, SERVER, "check_followup_status")
def check_followup_status(patient_id: int, principal: dict | None = None,
                          audit_correlation_id: str = "") -> dict:
    """Recorded follow-up status for the patient."""
    db = SessionLocal()
    try:
        require_patient(db, principal, patient_id)
        rows = (
            db.query(FollowUp)
            .filter(FollowUp.patient_id == patient_id)
            .order_by(FollowUp.follow_up_date)
            .all()
        )
        return {
            "patient_id": patient_id,
            "follow_ups": [
                {"ref": f"follow_ups#{fu.id}", "due": str(fu.follow_up_date),
                 "status": fu.status, "reason": fu.reason}
                for fu in rows
            ],
        }
    finally:
        db.close()


@mcp_tool(mcp, SERVER, "prepare_patient_summary")
def prepare_patient_summary(patient_id: int, principal: dict | None = None,
                            audit_correlation_id: str = "") -> dict:
    """Patient-friendly summary of recorded next steps (no clinical advice)."""
    db = SessionLocal()
    try:
        patient = require_patient(db, principal, patient_id)
        next_appt = (
            db.query(Appointment)
            .filter(Appointment.patient_id == patient_id,
                    Appointment.status.in_(("CONFIRMED", "PENDING")))
            .order_by(Appointment.appointment_date)
            .first()
        )
        pending = (
            db.query(FollowUp)
            .filter(FollowUp.patient_id == patient_id,
                    FollowUp.status.notin_(_DONE))
            .all()
        )
        lines = [f"Hi {patient.name}, here is what our records show:"]
        if next_appt is not None:
            lines.append(f"- Your next appointment is on {next_appt.appointment_date} ({next_appt.status}).")
        else:
            lines.append("- No upcoming appointment is recorded.")
        if pending:
            lines.append(f"- You have {len(pending)} follow-up(s) to complete.")
        else:
            lines.append("- No pending follow-ups are recorded.")
        lines.append("- This restates recorded clinic information only - it is not medical advice.")
        return {
            "patient": patient.name,
            "summary": "\n".join(lines),
            "pending_followups": len(pending),
            "next_appointment": str(next_appt.appointment_date) if next_appt else None,
        }
    finally:
        db.close()


@mcp_tool(mcp, SERVER, "request_missing_information")
def request_missing_information(patient_id: int, missing: str,
                                principal: dict | None = None,
                                audit_correlation_id: str = "") -> dict:
    """Record a clarification request and notify the patient (no clinical advice)."""
    db = SessionLocal()
    try:
        patient = require_patient(db, principal, patient_id)
        db.add(Notification(
            user_id=patient.id,
            title="Information needed",
            message=f"Please provide: {missing}",
            notification_type="CARE_CONTINUITY",
        ))
        db.commit()
        return {
            "requested": True,
            "patient": patient.name,
            "missing": missing,
            "note": "A notification was recorded for the patient.",
        }
    finally:
        db.close()


if __name__ == "__main__":
    serve(SERVER, mcp)
