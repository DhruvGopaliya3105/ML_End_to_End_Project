"""Deterministic evidence validation before any medical chatbot answer.

Flow (per the platform specification):

1. authenticate    - the caller passes the server-side session user
2. authorize       - patient-scoped claims are checked against the principal
3. retrieve        - evidence comes only from permitted database records
4. check support   - does the retrieved evidence actually support the claim?
5. identify gaps   - missing or contradictory information
6. constrained answer with evidence references
7. block unsupported medical or patient-specific claims
8. record the outcome (DB rows + ai_evidence_audit.log)
9. return the answer or a controlled refusal

A database failure is NEVER interpreted as "record does not exist" - it is
reported as SOURCE_UNAVAILABLE. The language model never creates facts; it
can only restate what these resolvers verified.
"""

from __future__ import annotations

import re
import uuid

from sqlalchemy import or_
from sqlalchemy.orm import Session

from src.models.ai_evidence import AiClaim, AiEvidence, AiRequest
from src.models.appointment import Appointment
from src.models.disease import Disease
from src.models.doctor import Doctor
from src.models.doctor_schedule import DoctorSchedule
from src.models.follow_up import FollowUp
from src.models.medicine import Medicine
from src.models.medicine_disease import MedicineDisease
from src.models.prescription import Prescription
from src.models.prescription_medicine import PrescriptionMedicine
from src.models.user import User
from src.security.rbac import user_role
from src.services import audit_log
from src.services.mcp_rbac import enforce_patient_scope

STATUS_VERIFIED = "VERIFIED"
STATUS_INCOMPLETE = "INCOMPLETE"
STATUS_CONFLICTED = "CONFLICTED"
STATUS_NOT_FOUND = "NOT_FOUND"
STATUS_SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
STATUS_ACCESS_DENIED = "ACCESS_DENIED"

REFUSAL_TEXT = "Verified information is not available in the current records."


# ============================================================
# EVIDENCE RESOLVERS - one per claim kind
# ============================================================
# Each resolver returns a list of evidence dicts:
#   {"source_type", "source_ref", "source_version", "snippet", "supports_claim"}
# supports_claim: True (supports), False (contradicts) or None (neutral).
# An empty list means: no verified record exists for this claim.

def _ev(source_ref: str, snippet: str, supports=None, source_version: str = "live") -> dict:
    return {
        "source_type": "DATABASE",
        "source_ref": source_ref,
        "source_version": source_version,
        "snippet": snippet,
        "supports_claim": supports,
    }


def _find_medicines(db: Session, name: str):
    return (
        db.query(Medicine)
        .filter(
            Medicine.is_active.is_(True),
            or_(Medicine.name.ilike(f"%{name}%"), Medicine.generic_name.ilike(f"%{name}%")),
        )
        .all()
    )


def _resolve_medicine_price(db: Session, claim: dict) -> list[dict]:
    name = (claim.get("medicine") or "").strip()
    expected = claim.get("price")
    if not name:
        return []
    out = []
    for med in _find_medicines(db, name):
        price = float(med.price or 0)
        supports = None
        if expected is not None:
            supports = abs(price - float(expected)) < 0.01
        out.append(_ev(
            f"medicines#{med.id}",
            f"{med.name} - Rs {price:.2f} (stock {int(med.stock or 0)} packs)",
            supports,
        ))
    return out


def _resolve_medicine_stock(db: Session, claim: dict) -> list[dict]:
    name = (claim.get("medicine") or "").strip()
    expected = claim.get("in_stock")
    if not name:
        return []
    out = []
    for med in _find_medicines(db, name):
        in_stock = int(med.stock or 0) > 0
        supports = None if expected is None else bool(in_stock == bool(expected))
        out.append(_ev(
            f"medicines#{med.id}",
            f"{med.name} - stock {int(med.stock or 0)} packs",
            supports,
        ))
    return out


def _resolve_medicine_for_disease(db: Session, claim: dict) -> list[dict]:
    disease_name = (claim.get("disease") or "").strip()
    med_name = (claim.get("medicine") or "").strip()
    if not disease_name or not med_name:
        return []
    disease = (
        db.query(Disease)
        .filter(or_(Disease.name.ilike(f"%{disease_name}%"),
                   Disease.slug.ilike(f"%{disease_name}%")))
        .first()
    )
    if disease is None:
        return []
    med = _find_medicines(db, med_name)
    if not med:
        return []
    med = med[0]
    link = (
        db.query(MedicineDisease)
        .filter(
            MedicineDisease.disease_id == disease.id,
            MedicineDisease.medicine_id == med.id,
        )
        .first()
    )
    return [_ev(
        f"diseases#{disease.id}+medicines#{med.id}",
        f"{med.name} is linked to {disease.name}" if link
        else f"{med.name} is NOT linked to {disease.name}",
        link is not None,
    )]


def _resolve_doctor_fee(db: Session, claim: dict) -> list[dict]:
    spec = (claim.get("specialization") or claim.get("doctor") or "").strip()
    expected = claim.get("fee")
    if not spec:
        return []
    docs = (
        db.query(Doctor)
        .filter(
            Doctor.is_active.is_(True),
            or_(Doctor.name.ilike(f"%{spec}%"),
                Doctor.specialization.ilike(f"%{spec}%")),
        )
        .all()
    )
    out = []
    for doc in docs:
        fee = float(doc.consultation_fee) if doc.consultation_fee else None
        supports = None
        if expected is not None and fee is not None:
            supports = abs(fee - float(expected)) < 0.01
        out.append(_ev(
            f"doctors#{doc.id}",
            f"Dr. {doc.name} - {doc.specialization} - consultation {fee}",
            supports,
        ))
    return out


def _resolve_clinic_timing(db: Session, claim: dict) -> list[dict]:
    rows = (
        db.query(DoctorSchedule.start_time, DoctorSchedule.end_time)
        .filter(DoctorSchedule.is_available.is_(True))
        .distinct()
        .all()
    )
    if not rows:
        return []
    start = min(r[0] for r in rows)
    end = max(r[1] for r in rows)
    opens = claim.get("opens")
    closes = claim.get("closes")
    supports = None
    if opens and closes:
        supports = (
            start.strftime("%H:%M") == str(opens)
            and end.strftime("%H:%M") == str(closes)
        )
    return [_ev(
        "doctor_schedules#*",
        f"Clinic timings {start.strftime('%H:%M')} - {end.strftime('%H:%M')}, Mon-Sun",
        supports,
    )]


def _resolve_appointment_status(db: Session, claim: dict) -> list[dict]:
    patient_id = claim.get("patient_id")
    expected = (claim.get("status") or "").strip().upper()
    if patient_id is None:
        return []
    rows = db.query(Appointment).filter(Appointment.patient_id == int(patient_id)).all()
    out = []
    for appt in rows:
        supports = None
        if expected:
            supports = (appt.status or "").upper() == expected
        out.append(_ev(
            f"appointments#{appt.id}",
            f"Appointment #{appt.id} - status {appt.status}",
            supports,
        ))
    return out


def _resolve_followup_status(db: Session, claim: dict) -> list[dict]:
    patient_id = claim.get("patient_id")
    expected = (claim.get("status") or "").strip().upper()
    if patient_id is None:
        return []
    rows = db.query(FollowUp).filter(FollowUp.patient_id == int(patient_id)).all()
    out = []
    for fu in rows:
        supports = None
        if expected:
            supports = (fu.status or "").upper() == expected
        out.append(_ev(
            f"follow_ups#{fu.id}",
            f"Follow-up #{fu.id} - {fu.follow_up_date} - status {fu.status}",
            supports,
        ))
    return out


def _resolve_prescribed_medicine(db: Session, claim: dict) -> list[dict]:
    patient_id = claim.get("patient_id")
    med_name = (claim.get("medicine") or "").strip()
    if patient_id is None or not med_name:
        return []
    linked = (
        db.query(PrescriptionMedicine)
        .join(Prescription, Prescription.id == PrescriptionMedicine.prescription_id)
        .filter(
            Prescription.patient_id == int(patient_id),
            PrescriptionMedicine.medicine_name.ilike(f"%{med_name}%"),
        )
        .first()
    )
    return [_ev(
        f"prescriptions#patient{patient_id}",
        f"'{med_name}' is prescribed to patient {patient_id}" if linked
        else f"'{med_name}' is NOT prescribed to patient {patient_id}",
        linked is not None,
    )]


_RESOLVERS = {
    "medicine_price": _resolve_medicine_price,
    "medicine_stock": _resolve_medicine_stock,
    "medicine_for_disease": _resolve_medicine_for_disease,
    "doctor_fee": _resolve_doctor_fee,
    "clinic_timing": _resolve_clinic_timing,
    "appointment_status": _resolve_appointment_status,
    "followup_status": _resolve_followup_status,
    "prescribed_medicine": _resolve_prescribed_medicine,
}


def resolve_evidence(db: Session, claim: dict) -> list[dict]:
    """Retrieve verified evidence for one claim (empty list = not found)."""
    resolver = _RESOLVERS.get(claim.get("kind"))
    if resolver is None:
        return []
    return resolver(db, claim)


def _claim_status(evidence: list[dict]) -> str:
    """VERIFIED / UNSUPPORTED / CONFLICTED / NOT_FOUND / INCOMPLETE."""
    if not evidence:
        return "NOT_FOUND"
    supports = [e for e in evidence if e.get("supports_claim") is True]
    contradicts = [e for e in evidence if e.get("supports_claim") is False]
    if supports and contradicts:
        return "CONFLICTED"
    if supports:
        return "VERIFIED"
    if contradicts:
        return "UNSUPPORTED"
    return "INCOMPLETE"


# ============================================================
# VALIDATION ENTRY POINT
# ============================================================

def validate_answer(
    db: Session,
    user: User | None,
    question: str,
    claims: list[dict],
    *,
    model_version: str | None = None,
) -> dict:
    """Validate answer claims against verified records.

    Returns {"request_id", "status", "refusal", "claims", "evidence"}.
    ``status`` is one of the six controlled statuses; anything that is not
    VERIFIED comes with a controlled refusal text - never invented data.
    """
    request_id = uuid.uuid4().hex
    claims = list(claims or [])

    if user is None or not getattr(user, "is_active", True):
        _record(db, None, request_id, question, None,
                STATUS_ACCESS_DENIED, "Not authenticated.", [], [])
        return {
            "request_id": request_id,
            "status": STATUS_ACCESS_DENIED,
            "refusal": "Please login first.",
            "claims": [],
            "evidence": [],
        }

    evaluated: list[dict] = []
    evidence_rows: list[dict] = []
    source_down = False

    for claim in claims:
        patient_id = claim.get("patient_id")
        if patient_id is not None and not enforce_patient_scope(db, user, patient_id):
            _record(db, user, request_id, question, None,
                    STATUS_ACCESS_DENIED,
                    "Access denied: patient record outside your authorized scope.",
                    evaluated, evidence_rows)
            return {
                "request_id": request_id,
                "status": STATUS_ACCESS_DENIED,
                "refusal": "Access denied: this record is outside your authorized scope.",
                "claims": evaluated,
                "evidence": evidence_rows,
            }
        try:
            evidence = resolve_evidence(db, claim)
        except Exception:
            # a connection failure is NOT proof that a record does not exist
            source_down = True
            evaluated.append({**claim, "status": STATUS_SOURCE_UNAVAILABLE, "evidence": []})
            break
        evaluated.append({
            **claim,
            "status": _claim_status(evidence),
            "evidence": evidence,
        })
        evidence_rows.extend(evidence)

    statuses = [c["status"] for c in evaluated]
    if source_down:
        overall = STATUS_SOURCE_UNAVAILABLE
    elif not evaluated:
        overall = STATUS_NOT_FOUND
    elif any(s == "CONFLICTED" for s in statuses):
        overall = STATUS_CONFLICTED
    elif all(s == "VERIFIED" for s in statuses):
        overall = STATUS_VERIFIED
    elif all(s == "NOT_FOUND" for s in statuses):
        overall = STATUS_NOT_FOUND
    else:
        overall = STATUS_INCOMPLETE

    refusal = None if overall == STATUS_VERIFIED else REFUSAL_TEXT
    _record(db, user, request_id, question, None, overall, refusal,
            evaluated, evidence_rows)
    return {
        "request_id": request_id,
        "status": overall,
        "refusal": refusal,
        "claims": evaluated,
        "evidence": evidence_rows,
    }


def _record(db, user, request_id, question, answer, overall, refusal, claims, evidence_rows) -> dict:
    """Persist the validation outcome: AI request + claims + evidence rows,
    and one ai_evidence_audit.log event. DB failure never loses the file trail."""
    actor = getattr(user, "email", None) if user else None
    role = user_role(user) if user else None
    if overall == STATUS_VERIFIED:
        result = "success"
    elif overall == STATUS_ACCESS_DENIED:
        result = "denied"
    else:
        result = "controlled_refusal"
    record = audit_log.log_event(
        "ai_evidence_audit",
        action="answer_validation",
        actor=actor,
        role=role,
        result=result,
        extra={
            "request_id": request_id,
            "status": overall,
            "claims_total": len(claims),
            "evidence_total": len(evidence_rows),
            "refusal": refusal,
        },
    )
    try:
        req = AiRequest(
            request_id=request_id,
            correlation_id=record.get("correlation_id"),
            actor=actor,
            role=role,
            question=question,
            answer=answer,
            status=overall,
            refusal_reason=refusal,
            model_version=None,
        )
        db.add(req)
        db.flush()
        for claim in claims:
            db.add(AiClaim(
                ai_request_id=req.id,
                claim_text=str(claim.get("text", "")),
                claim_kind=claim.get("kind"),
                status=claim.get("status", STATUS_NOT_FOUND),
            ))
        for ev in evidence_rows:
            db.add(AiEvidence(
                ai_request_id=req.id,
                source_type=ev.get("source_type", "DATABASE"),
                source_ref=ev.get("source_ref", ""),
                source_version=ev.get("source_version"),
                snippet=ev.get("snippet"),
                supports_claim=ev.get("supports_claim"),
            ))
        db.commit()
    except Exception:
        # the JSONL audit above already persisted - the file trail survives
        # even when the database is unavailable
        db.rollback()
    return record


# ============================================================
# CHATBOT EVIDENCE GATE
# ============================================================

def _to_24h(hhmm: str, ampm: str) -> str:
    h, m = hhmm.split(":")
    h = int(h) % 12
    if ampm.upper() == "PM":
        h += 12
    return f"{h:02d}:{m}"


def extract_claims(reply: str) -> list[dict]:
    """Extract checkable factual claims from a DB-backed chatbot reply.

    Covers the reply formats of the local knowledge handlers: medicine
    price lines, medicine cards, disease medicine lists, doctor fee lines
    and clinic timing lines. Guidance / disclaimer text produces no claims
    and passes through untouched.
    """
    claims: list[dict] = []
    text = reply or ""

    disease_match = re.search(r"🩺\s+([A-Za-z][A-Za-z &+\-/]+)", text)
    disease_name = disease_match.group(1).strip() if disease_match else None

    for m in re.finditer(r"•\s+([A-Za-z0-9][A-Za-z0-9 +\-/%()]*?)\s+-\s+Rs\s+([\d,]+\.\d{2})", text):
        # the catalog list appends " (Rx)" after the name - strip it so the
        # resolver can match the real medicine name
        name = re.sub(r"\s*\(Rx[^)]*\)$", "", m.group(1).strip()).strip()
        price = float(m.group(2).replace(",", ""))
        claims.append({
            "kind": "medicine_price",
            "text": f"{name} costs Rs {price:.2f}",
            "medicine": name, "price": price,
        })
        if disease_name:
            claims.append({
                "kind": "medicine_for_disease",
                "text": f"{name} is stocked for {disease_name}",
                "disease": disease_name, "medicine": name,
            })

    card = re.search(r"💊\s+([A-Za-z0-9][A-Za-z0-9 +\-/%()]*)", text)
    price_m = re.search(r"Price:\s+Rs\s+([\d,]+\.\d{2})", text)
    if card and price_m:
        name = card.group(1).strip()
        price = float(price_m.group(1).replace(",", ""))
        claims.append({
            "kind": "medicine_price",
            "text": f"{name} costs Rs {price:.2f}",
            "medicine": name, "price": price,
        })

    for m in re.finditer(r"Dr\.\s+([A-Za-z][A-Za-z .]*?)(?:,\s*\d+\s*yrs)?\s+-\s+consultation\s+Rs\s+([\d.]+)", text):
        name = m.group(1).strip()
        fee = float(m.group(2))
        claims.append({
            "kind": "doctor_fee",
            "text": f"Dr. {name} charges Rs {fee:.0f}",
            "doctor": name, "fee": fee,
        })

    t = re.search(r"Clinic timings:\s+(\d{1,2}:\d{2})\s*(AM|PM)\s*-\s*(\d{1,2}:\d{2})\s*(AM|PM)", text)
    if t:
        claims.append({
            "kind": "clinic_timing",
            "text": f"Clinic is open {t.group(1)} {t.group(2)} - {t.group(3)} {t.group(4)}",
            "opens": _to_24h(t.group(1), t.group(2)),
            "closes": _to_24h(t.group(3), t.group(4)),
        })

    seen, out = set(), []
    for c in claims:
        key = (c["kind"], c.get("medicine") or c.get("doctor") or c.get("disease"),
               c.get("price") or c.get("fee") or c.get("opens"))
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


def evidence_gate(db, user, question: str, reply: str) -> str:
    """Deterministic evidence gate before a DB-backed answer is returned.

    Extracts the reply's factual claims and validates them against the
    clinic's records. VERIFIED -> the reply passes unchanged. Anything
    else -> a controlled refusal (never invented data, never a half-truth).
    Replies with no extractable claims (guidance, disclaimers) pass through.
    """
    claims = extract_claims(reply)
    if not claims:
        return reply
    result = validate_answer(db, user, question, claims)
    if result["status"] == STATUS_VERIFIED:
        return reply
    return (
        "⚠️ " + REFUSAL_TEXT + "\n\n"
        "(Some claims in this answer could not be verified against the "
        "clinic's records - status: " + result["status"] + ".)"
    )
