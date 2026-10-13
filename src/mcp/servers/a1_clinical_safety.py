"""A1 - Clinical Contradiction and Safety MCP (ADMIN, port 9201).

Detects conflicts in recorded clinical information and routes them to
authorized clinicians. A detected conflict is an alert, not a confirmed
medical conclusion - the system never changes prescriptions.
"""

from src.database.connection import SessionLocal
from src.mcp.server_base import (
    ControlledError,
    build_server,
    mcp_tool,
    require_patient,
    serve,
)
from src.models.clinical_conflict import ClinicalConflict
from src.models.notification import Notification
from src.models.prescription import Prescription
from src.models.prescription_medicine import PrescriptionMedicine
from src.models.user import User
from src.services import audit_log
from src.services.mcp_rbac import get_server

SERVER = get_server("clinical-safety")
mcp = build_server(SERVER)


def _detect_conflicts_impl(db, patient_id: int | None) -> list[dict]:
    conflicts: list[dict] = []
    rx_query = db.query(Prescription)
    if patient_id is not None:
        rx_query = rx_query.filter(Prescription.patient_id == patient_id)
    prescriptions = rx_query.all()

    by_medicine: dict[tuple, list] = {}
    for p in prescriptions:
        for pm in db.query(PrescriptionMedicine).filter(
            PrescriptionMedicine.prescription_id == p.id
        ).all():
            key = (p.patient_id, (pm.medicine_name or "").strip().lower())
            by_medicine.setdefault(key, []).append(pm)

    for (pid, med), rows in by_medicine.items():
        regimens = {(pm.dosage, pm.frequency) for pm in rows}
        if len(regimens) > 1:
            conflicts.append({
                "conflict_type": "MEDICATION_DATE",
                "patient_id": pid,
                "description": f"'{med}' is recorded with different dosage/frequency across {len(rows)} prescriptions.",
                "severity": "HIGH",
            })

    for p in prescriptions:
        if not (p.diagnosis or "").strip():
            conflicts.append({
                "conflict_type": "MISSING_CONTEXT",
                "patient_id": p.patient_id,
                "description": f"Prescription #{p.id} has no recorded diagnosis.",
                "severity": "MEDIUM",
            })
    return conflicts


@mcp_tool(mcp, SERVER, "detect_record_conflicts")
def detect_record_conflicts(patient_id: int | None = None,
                            principal: dict | None = None,
                            audit_correlation_id: str = "") -> dict:
    """Detect conflicts in recorded clinical info (alerts, not conclusions).

    With patient_id: that patient's records (authorized scope). Without:
    an admin-level scan across all recorded prescriptions.
    """
    db = SessionLocal()
    try:
        if patient_id is not None:
            require_patient(db, principal, patient_id)
        conflicts = _detect_conflicts_impl(db, patient_id)
        created = 0
        for c in conflicts:
            exists = db.query(ClinicalConflict).filter(
                ClinicalConflict.status == "OPEN",
                ClinicalConflict.description == c["description"],
            ).first()
            if exists is None:
                db.add(ClinicalConflict(
                    conflict_type=c["conflict_type"],
                    patient_id=c["patient_id"],
                    description=c["description"],
                    severity=c["severity"],
                ))
                created += 1
        db.commit()
        return {
            "scanned_patient": patient_id,
            "conflicts_found": len(conflicts),
            "conflicts_created": created,
            "conflicts": conflicts,
        }
    finally:
        db.close()


@mcp_tool(mcp, SERVER, "flag_safety_concerns")
def flag_safety_concerns(conflict_id: int, severity: str = "HIGH",
                         principal: dict | None = None,
                         audit_correlation_id: str = "") -> dict:
    """Flag or re-grade a conflict's severity (moves it to REVIEWING)."""
    db = SessionLocal()
    try:
        conflict = db.get(ClinicalConflict, conflict_id)
        if conflict is None:
            raise ControlledError("NOT_FOUND", "conflict not found")
        conflict.severity = severity.upper()
        conflict.status = "REVIEWING"
        db.commit()
        return {"flagged": True, "conflict_id": conflict.id, "severity": conflict.severity}
    finally:
        db.close()


@mcp_tool(mcp, SERVER, "request_clinical_review")
def request_clinical_review(conflict_id: int, doctor_user_id: int,
                            principal: dict | None = None,
                            audit_correlation_id: str = "") -> dict:
    """Assign a conflict to a doctor and notify them (clinicians approve changes)."""
    db = SessionLocal()
    try:
        conflict = db.get(ClinicalConflict, conflict_id)
        if conflict is None:
            raise ControlledError("NOT_FOUND", "conflict not found")
        doctor = db.get(User, doctor_user_id)
        if doctor is None:
            raise ControlledError("NOT_FOUND", "doctor user not found")
        conflict.assigned_to_user_id = doctor.id
        conflict.status = "REVIEWING"
        db.add(Notification(
            user_id=doctor.id,
            title="Clinical review requested",
            message=f"Please review conflict #{conflict.id}: {conflict.description}",
            notification_type="CLINICAL_REVIEW",
        ))
        db.commit()
        audit_log.log_event(
            "clinical_review", action="review_requested",
            actor=(principal or {}).get("email"),
            resource_type="clinical_conflict",
            resource_ref=f"clinical_conflicts#{conflict.id}",
            result="success",
            extra={"assigned_to": doctor.email, "severity": conflict.severity},
        )
        return {"requested": True, "conflict_id": conflict.id, "assigned_to": doctor.email}
    finally:
        db.close()


@mcp_tool(mcp, SERVER, "get_conflict_resolution_history")
def get_conflict_resolution_history(conflict_id: int | None = None,
                                    principal: dict | None = None,
                                    audit_correlation_id: str = "") -> dict:
    """Conflict history with resolution status (one conflict or all)."""
    db = SessionLocal()
    try:
        query = db.query(ClinicalConflict)
        if conflict_id is not None:
            query = query.filter(ClinicalConflict.id == conflict_id)
        rows = query.order_by(ClinicalConflict.detected_at.desc()).all()
        return {
            "conflicts": [
                {"ref": f"clinical_conflicts#{c.id}", "type": c.conflict_type,
                 "patient_id": c.patient_id, "severity": c.severity,
                 "status": c.status, "detected_at": c.detected_at.isoformat(),
                 "resolved_at": c.resolved_at.isoformat() if c.resolved_at else None,
                 "resolved_by": c.resolved_by, "notes": c.resolution_notes}
                for c in rows
            ]
        }
    finally:
        db.close()


if __name__ == "__main__":
    serve(SERVER, mcp)
