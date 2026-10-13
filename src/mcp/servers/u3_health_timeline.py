"""U3 - Longitudinal Health Timeline MCP (USER, port 9103, svc-u3-timeline)."""

from datetime import datetime, timedelta

from src.database.connection import SessionLocal
from src.mcp.server_base import (
    ControlledError,
    build_patient_timeline,
    build_server,
    mcp_tool,
    require_patient,
    serve,
)
from src.models.clinical_conflict import ClinicalConflict
from src.models.follow_up import FollowUp
from src.models.medical_record import MedicalRecord
from src.models.prescription import Prescription
from src.models.prescription_medicine import PrescriptionMedicine
from src.services.mcp_rbac import get_server

SERVER = get_server("health-timeline")
mcp = build_server(SERVER)


@mcp_tool(mcp, SERVER, "build_health_timeline")
def build_health_timeline(patient_id: int, principal: dict | None = None,
                          audit_correlation_id: str = "") -> dict:
    """Complete chronological patient journey from verified records."""
    db = SessionLocal()
    try:
        require_patient(db, principal, patient_id)
        timeline = build_patient_timeline(db, patient_id)
        return {
            "patient_id": patient_id,
            "timeline": timeline,
            "entries": len(timeline),
            "note": "Every entry carries its source record id and recorded timestamp.",
        }
    finally:
        db.close()


@mcp_tool(mcp, SERVER, "compare_visits")
def compare_visits(patient_id: int, principal: dict | None = None,
                   audit_correlation_id: str = "") -> dict:
    """Compare recorded visits (dates, doctors, diagnoses)."""
    db = SessionLocal()
    try:
        require_patient(db, principal, patient_id)
        records = (
            db.query(MedicalRecord)
            .filter(MedicalRecord.patient_id == patient_id)
            .order_by(MedicalRecord.visit_date)
            .all()
        )
        return {
            "patient_id": patient_id,
            "visits": [
                {"ref": f"medical_records#{r.id}", "date": str(r.visit_date),
                 "doctor_id": r.doctor_id, "diagnosis": r.diagnosis_notes}
                for r in records
            ],
        }
    finally:
        db.close()


@mcp_tool(mcp, SERVER, "detect_stale_records")
def detect_stale_records(patient_id: int, days: int = 180,
                         principal: dict | None = None,
                         audit_correlation_id: str = "") -> dict:
    """Identify stale records and unresolved data conflicts."""
    db = SessionLocal()
    try:
        require_patient(db, principal, patient_id)
        cutoff = datetime.utcnow() - timedelta(days=days)
        stale = []
        for p in db.query(Prescription).filter(Prescription.patient_id == patient_id).all():
            created = getattr(p, "created_at", None)
            if created and created < cutoff:
                stale.append({"ref": f"prescriptions#{p.id}",
                              "reason": f"prescription older than {days} days"})
        for fu in db.query(FollowUp).filter(FollowUp.patient_id == patient_id).all():
            if (fu.status or "").upper() not in ("DONE", "COMPLETED"):
                stale.append({"ref": f"follow_ups#{fu.id}",
                              "reason": f"follow-up from {fu.follow_up_date} not completed"})
        conflicts = (
            db.query(ClinicalConflict)
            .filter(ClinicalConflict.patient_id == patient_id,
                    ClinicalConflict.status != "RESOLVED")
            .all()
        )
        return {
            "patient_id": patient_id,
            "stale_records": stale,
            "unresolved_conflicts": [
                {"ref": f"clinical_conflicts#{c.id}", "type": c.conflict_type,
                 "status": c.status, "severity": c.severity}
                for c in conflicts
            ],
        }
    finally:
        db.close()


@mcp_tool(mcp, SERVER, "generate_verified_patient_summary")
def generate_verified_patient_summary(patient_id: int, principal: dict | None = None,
                                      audit_correlation_id: str = "") -> dict:
    """Patient-friendly summary built ONLY from verified records (downloadable)."""
    db = SessionLocal()
    try:
        patient = require_patient(db, principal, patient_id)
        timeline = build_patient_timeline(db, patient_id)
        meds = (
            db.query(PrescriptionMedicine.medicine_name)
            .join(Prescription, Prescription.id == PrescriptionMedicine.prescription_id)
            .filter(Prescription.patient_id == patient_id)
            .distinct()
            .all()
        )
        lines = [
            f"Health summary for {patient.name}",
            f"Compiled from recorded clinic data on {datetime.utcnow().date().isoformat()}.",
            "",
            f"Recorded events: {len(timeline)}",
            f"Recorded medicines: {', '.join(m[0] for m in meds) or 'none recorded'}",
            "",
            "This summary restates recorded clinic data - it is not a diagnosis.",
        ]
        return {
            "patient": patient.name,
            "generated_at": datetime.utcnow().isoformat(),
            "summary": "\n".join(lines),
            "timeline_entries": len(timeline),
            "source": "verified clinic records",
        }
    finally:
        db.close()


if __name__ == "__main__":
    serve(SERVER, mcp)
