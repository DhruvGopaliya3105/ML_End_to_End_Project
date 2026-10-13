"""U2 - Evidence-Backed AI MCP (USER, port 9102, svc-u2-evidence-ai).

Evidence-grounded answers for the healthcare chatbot. Never invents
prescriptions, diagnoses, prices, appointments or medical history.
"""

from src.database.connection import SessionLocal
from src.mcp.server_base import (
    ControlledError,
    _resolve_user,
    build_server,
    mcp_tool,
    require_patient,
    serve,
)
from src.models.ai_evidence import AiClaim, AiEvidence, AiRequest
from src.security.rbac import ROLE_PATIENT, user_role
from src.services.evidence_service import resolve_evidence, validate_answer
from src.services.mcp_rbac import get_server

SERVER = get_server("evidence-ai")
mcp = build_server(SERVER)


@mcp_tool(mcp, SERVER, "retrieve_evidence")
def retrieve_evidence(kind: str, params: dict | None = None,
                      principal: dict | None = None,
                      audit_correlation_id: str = "") -> dict:
    """Retrieve verified evidence for one claim.

    Kinds: medicine_price, medicine_stock, medicine_for_disease, doctor_fee,
    clinic_timing, appointment_status, followup_status, prescribed_medicine.
    """
    db = SessionLocal()
    try:
        params = dict(params or {})
        if params.get("patient_id") is not None:
            require_patient(db, principal, params["patient_id"])
        evidence = resolve_evidence(db, {"kind": kind, **params})
        return {"kind": kind, "evidence": evidence, "available": bool(evidence)}
    finally:
        db.close()


@mcp_tool(mcp, SERVER, "verify_claims")
def verify_claims(question: str, claims: list,
                  principal: dict | None = None,
                  audit_correlation_id: str = "") -> dict:
    """Validate answer claims against verified records (hallucination control).

    Returns one of: VERIFIED, INCOMPLETE, CONFLICTED, NOT_FOUND,
    SOURCE_UNAVAILABLE, ACCESS_DENIED - with a controlled refusal whenever
    the answer cannot be fully verified.
    """
    db = SessionLocal()
    try:
        user = _resolve_user(db, principal)
        return validate_answer(db, user, question, claims)
    finally:
        db.close()


@mcp_tool(mcp, SERVER, "explain_answer_sources")
def explain_answer_sources(request_id: str, principal: dict | None = None,
                           audit_correlation_id: str = "") -> dict:
    """Explain which verified records an AI answer was grounded in."""
    db = SessionLocal()
    try:
        req = db.query(AiRequest).filter(AiRequest.request_id == request_id).first()
        if req is None:
            raise ControlledError("NOT_FOUND", "no AI request with that id")
        user = _resolve_user(db, principal)
        if user is not None and user_role(user) == ROLE_PATIENT and req.actor != user.email:
            raise ControlledError("ACCESS_DENIED", "this AI request is not yours")
        evidence = db.query(AiEvidence).filter(AiEvidence.ai_request_id == req.id).all()
        claims = db.query(AiClaim).filter(AiClaim.ai_request_id == req.id).all()
        return {
            "request_id": request_id,
            "status": req.status,
            "question": req.question,
            "sources": [
                {"ref": e.source_ref, "type": e.source_type, "snippet": e.snippet,
                 "supports": e.supports_claim}
                for e in evidence
            ],
            "claims": [
                {"text": c.claim_text, "kind": c.claim_kind, "status": c.status}
                for c in claims
            ],
        }
    finally:
        db.close()


@mcp_tool(mcp, SERVER, "check_information_availability")
def check_information_availability(kind: str, params: dict | None = None,
                                 principal: dict | None = None,
                                 audit_correlation_id: str = "") -> dict:
    """Is this information available in verified records?

    Distinguishes NOT_FOUND (verified absence) from SOURCE_UNAVAILABLE
    (verification could not be completed - never treated as absence).
    """
    db = SessionLocal()
    try:
        params = dict(params or {})
        if params.get("patient_id") is not None:
            require_patient(db, principal, params["patient_id"])
        try:
            evidence = resolve_evidence(db, {"kind": kind, **params})
        except Exception:
            return {
                "kind": kind,
                "availability": "SOURCE_UNAVAILABLE",
                "message": "Verification could not be completed - the source is unavailable.",
            }
        if not evidence:
            return {
                "kind": kind,
                "availability": "NOT_FOUND",
                "message": "Verified information is not available in the current records.",
            }
        return {"kind": kind, "availability": "AVAILABLE", "evidence_count": len(evidence)}
    finally:
        db.close()


if __name__ == "__main__":
    serve(SERVER, mcp)
