"""U1 - Care Gap Intelligence MCP (USER, port 9101, svc-u1-care-gap).

Detects missing steps in a patient's recorded healthcare journey and
creates review tasks. A care gap is an administrative observation - never a
clinical conclusion.
"""

from datetime import date

from src.database.connection import SessionLocal
from src.mcp.server_base import (
    ControlledError,
    build_patient_timeline,
    build_server,
    mcp_tool,
    require_patient,
    serve,
)
from src.models.appointment import Appointment
from src.models.care_gap import CareGap, CareReviewTask
from src.models.follow_up import FollowUp
from src.models.medical_record import MedicalRecord
from src.models.treatment import Treatment
from src.models.user import User
from src.services.mcp_rbac import get_server

SERVER = get_server("care-gap-intelligence")
mcp = build_server(SERVER)

_DONE = ("DONE", "COMPLETED")


def _detect_gaps_impl(db, patient_id: int) -> list[dict]:
    """Administrative gap detection over verified records only."""
    gaps: list[dict] = []
    today = date.today()

    for a in db.query(Appointment).filter(
        Appointment.patient_id == patient_id,
        Appointment.appointment_date < today,
        Appointment.status == "PENDING",
    ).all():
        gaps.append({
            "gap_type": "INCOMPLETE_WORKFLOW",
            "description": f"Appointment #{a.id} on {a.appointment_date} is still pending.",
            "severity": "MEDIUM",
            "source_ref": f"appointments#{a.id}",
        })

    follow_ups = db.query(FollowUp).filter(FollowUp.patient_id == patient_id).all()
    fu_dates = {fu.follow_up_date for fu in follow_ups}
    for rec in db.query(MedicalRecord).filter(MedicalRecord.patient_id == patient_id).all():
        if rec.doctor_instructions and rec.visit_date not in fu_dates:
            gaps.append({
                "gap_type": "MISSING_FOLLOWUP",
                "description": f"Visit on {rec.visit_date} has doctor instructions but no recorded follow-up.",
                "severity": "MEDIUM",
                "source_ref": f"medical_records#{rec.id}",
            })

    for fu in follow_ups:
        if fu.follow_up_date < today and (fu.status or "").upper() not in _DONE:
            gaps.append({
                "gap_type": "MISSING_FOLLOWUP",
                "description": f"Follow-up #{fu.id} was due {fu.follow_up_date} and is not marked done.",
                "severity": "HIGH",
                "source_ref": f"follow_ups#{fu.id}",
            })

    for tr in db.query(Treatment).filter(Treatment.patient_id == patient_id).all():
        if tr.end_date and tr.end_date < today and (tr.status or "").upper() not in _DONE:
            gaps.append({
                "gap_type": "INCOMPLETE_WORKFLOW",
                "description": f"Treatment '{tr.treatment_name}' ended {tr.end_date} but is still '{tr.status}'.",
                "severity": "LOW",
                "source_ref": f"treatments#{tr.id}",
            })
    return gaps


@mcp_tool(mcp, SERVER, "detect_care_gaps")
def detect_care_gaps(patient_id: int, principal: dict | None = None,
                    audit_correlation_id: str = "") -> dict:
    """Detect missing steps in a patient's recorded healthcare journey.

    Creates OPEN care-gap records for review (deduplicated) - a gap is an
    administrative observation, never a clinical conclusion.
    """
    db = SessionLocal()
    try:
        require_patient(db, principal, patient_id)
        gaps = _detect_gaps_impl(db, patient_id)
        created = 0
        for gap in gaps:
            exists = db.query(CareGap).filter(
                CareGap.patient_id == patient_id,
                CareGap.status == "OPEN",
                CareGap.description == gap["description"],
            ).first()
            if exists is None:
                db.add(CareGap(
                    patient_id=patient_id,
                    gap_type=gap["gap_type"],
                    description=gap["description"],
                    severity=gap["severity"],
                ))
                created += 1
        db.commit()
        return {
            "patient_id": patient_id,
            "gaps_found": len(gaps),
            "gaps_created": created,
            "gaps": gaps,
        }
    finally:
        db.close()


@mcp_tool(mcp, SERVER, "trace_missing_steps")
def trace_missing_steps(patient_id: int, principal: dict | None = None,
                        audit_correlation_id: str = "") -> dict:
    """Trace the recorded journey and list the missing steps."""
    db = SessionLocal()
    try:
        require_patient(db, principal, patient_id)
        return {
            "patient_id": patient_id,
            "timeline": build_patient_timeline(db, patient_id),
            "missing_steps": _detect_gaps_impl(db, patient_id),
        }
    finally:
        db.close()


@mcp_tool(mcp, SERVER, "get_care_timeline")
def get_care_timeline(patient_id: int, principal: dict | None = None,
                      audit_correlation_id: str = "") -> dict:
    """Chronological care timeline - each entry has its source record id and
    recorded timestamp; nothing is invented."""
    db = SessionLocal()
    try:
        require_patient(db, principal, patient_id)
        return {
            "patient_id": patient_id,
            "timeline": build_patient_timeline(db, patient_id),
        }
    finally:
        db.close()


@mcp_tool(mcp, SERVER, "create_care_review_task")
def create_care_review_task(gap_id: int, assigned_to_user_id: int | None = None,
                            principal: dict | None = None,
                            audit_correlation_id: str = "") -> dict:
    """Create a review task for a care gap, optionally assigned to a clinician."""
    db = SessionLocal()
    try:
        gap = db.get(CareGap, gap_id)
        if gap is None:
            raise ControlledError("NOT_FOUND", "care gap not found")
        assignee = db.get(User, assigned_to_user_id) if assigned_to_user_id else None
        task = CareReviewTask(
            care_gap_id=gap.id,
            assigned_to_user_id=assignee.id if assignee else None,
            assigned_to_name=assignee.name if assignee else None,
        )
        db.add(task)
        gap.status = "REVIEWING"
        db.commit()
        return {
            "created": True,
            "task_id": task.id,
            "gap_id": gap.id,
            "assigned_to": assignee.name if assignee else None,
        }
    finally:
        db.close()


if __name__ == "__main__":
    serve(SERVER, mcp)
