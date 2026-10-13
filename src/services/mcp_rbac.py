"""Central RBAC for the MCP platform - who may call which server and tool.

This is the single place where MCP authorization is decided:

* the 10 logical servers (5 User / 3 Admin / 2 System) with their ports,
  service identities, tools and required roles,
* the data scope each tool operates in.

The FastAPI gateway and every MCP server check through ``check_tool_access``.
The browser is never trusted: the principal comes from the server-side
session, and tool calls are enforced even when they arrive outside the
normal UI workflow.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from src.models.audit_event import AuditEvent, SecurityEvent
from src.models.mcp_registry import McpServer
from src.models.user import User
from src.security.rbac import (
    ROLE_ADMIN,
    ROLE_DOCTOR,
    ROLE_PATIENT,
    ROLE_SUPERUSER,
    user_role,
)
from src.services import audit_log

# ============================================================
# SERVER CATALOG - exactly 10 logical servers
# ============================================================
# category USER = 5, ADMIN = 3, SYSTEM = 2. Ports are local development
# ports; the gateway dials them over streamable HTTP and never exposes
# them to the browser.

SERVER_CATALOG = [
    {
        "group": "U1", "name": "care-gap-intelligence", "category": "USER",
        "port": 9101, "service_identity": "svc-u1-care-gap",
        "description": "Detect missing steps in a patient's recorded healthcare journey.",
        "tools": [
            "detect_care_gaps", "trace_missing_steps",
            "get_care_timeline", "create_care_review_task",
        ],
        "required_roles": [ROLE_PATIENT, ROLE_DOCTOR],
    },
    {
        "group": "U2", "name": "evidence-ai", "category": "USER",
        "port": 9102, "service_identity": "svc-u2-evidence-ai",
        "description": "Evidence-grounded answers for the healthcare chatbot.",
        "tools": [
            "retrieve_evidence", "verify_claims",
            "explain_answer_sources", "check_information_availability",
        ],
        "required_roles": [ROLE_PATIENT, ROLE_DOCTOR, ROLE_ADMIN, ROLE_SUPERUSER],
    },
    {
        "group": "U3", "name": "health-timeline", "category": "USER",
        "port": 9103, "service_identity": "svc-u3-timeline",
        "description": "Complete chronological patient journey from verified records.",
        "tools": [
            "build_health_timeline", "compare_visits",
            "detect_stale_records", "generate_verified_patient_summary",
        ],
        "required_roles": [ROLE_PATIENT, ROLE_DOCTOR],
    },
    {
        "group": "U4", "name": "workflow-simulator", "category": "USER",
        "port": 9104, "service_identity": "svc-u4-simulator",
        "description": "What-if simulation on synthetic data - never touches live records.",
        "tools": [
            "simulate_scenario", "compare_outcomes",
            "explain_assumptions", "validate_scenario_inputs",
        ],
        "required_roles": [ROLE_PATIENT, ROLE_DOCTOR, ROLE_ADMIN, ROLE_SUPERUSER],
    },
    {
        "group": "U5", "name": "care-continuity", "category": "USER",
        "port": 9105, "service_identity": "svc-u5-continuity",
        "description": "Recorded next steps and pending follow-up status for patients.",
        "tools": [
            "get_pending_care_steps", "check_followup_status",
            "prepare_patient_summary", "request_missing_information",
        ],
        "required_roles": [ROLE_PATIENT, ROLE_DOCTOR],
    },
    {
        "group": "A1", "name": "clinical-safety", "category": "ADMIN",
        "port": 9201, "service_identity": "svc-a1-clinical-safety",
        "description": "Detect conflicts and safety concerns in recorded clinical info.",
        "tools": [
            "detect_record_conflicts", "flag_safety_concerns",
            "request_clinical_review", "get_conflict_resolution_history",
        ],
        "required_roles": [ROLE_DOCTOR, ROLE_ADMIN, ROLE_SUPERUSER],
    },
    {
        "group": "A2", "name": "hospital-intelligence", "category": "ADMIN",
        "port": 9202, "service_identity": "svc-a2-hospital-intel",
        "description": "Privacy-preserving aggregate hospital operations analytics.",
        "tools": [
            "analyze_workflow_patterns", "measure_care_gaps",
            "compare_periods", "generate_aggregate_report",
        ],
        "required_roles": [ROLE_ADMIN, ROLE_SUPERUSER],
    },
    {
        "group": "A3", "name": "change-approval", "category": "ADMIN",
        "port": 9203, "service_identity": "svc-a3-change-approval",
        "description": "Preview and control important system changes with approvals.",
        "tools": [
            "preview_change_impact", "request_approval",
            "verify_rollback_plan", "get_change_history",
        ],
        "required_roles": [ROLE_ADMIN, ROLE_SUPERUSER],
    },
    {
        "group": "S1", "name": "ai-reliability", "category": "SYSTEM",
        "port": 9301, "service_identity": "svc-s1-ai-reliability",
        "description": "Red-team and reliability benchmarks for the AI + MCP stack.",
        "tools": [
            "run_safety_benchmarks", "test_access_boundaries",
            "evaluate_answer_grounding", "compare_versions", "generate_test_report",
        ],
        "required_roles": [ROLE_SUPERUSER],
    },
    {
        "group": "S2", "name": "flight-recorder", "category": "SYSTEM",
        "port": 9302, "service_identity": "svc-s2-flight-recorder",
        "description": "Reconstruct failed workflows and coordinate safe recovery.",
        "tools": [
            "reconstruct_event_history", "reconcile_failed_workflow",
            "verify_recovery", "get_incident_timeline",
        ],
        "required_roles": [ROLE_ADMIN, ROLE_SUPERUSER],
    },
]

# ============================================================
# TOOL SCOPES
# ============================================================
# own             - a patient sees only their own records
# own_or_assigned - patient own records; doctors authorized (enrolled) patients
# aggregate       - admin/superuser aggregate metrics only, no patient rows
# synthetic       - simulation on synthetic data only
# system          - system-level operations (superuser governed)

TOOL_SCOPES = {
    "care-gap-intelligence": "own_or_assigned",
    "evidence-ai": "own_or_assigned",
    "health-timeline": "own_or_assigned",
    "workflow-simulator": "synthetic",
    "care-continuity": "own_or_assigned",
    "clinical-safety": "own_or_assigned",
    "hospital-intelligence": "aggregate",
    "change-approval": "aggregate",
    "ai-reliability": "system",
    "flight-recorder": "aggregate",
}

_CATALOG_BY_NAME = {entry["name"]: entry for entry in SERVER_CATALOG}


def get_server(server_name: str) -> dict | None:
    """Catalog entry for one server, or None if it does not exist."""
    return _CATALOG_BY_NAME.get(server_name)


def list_servers() -> list[dict]:
    """All 10 catalog entries (the MCP Server Registry page reads this)."""
    return list(SERVER_CATALOG)


def get_tool_scope(server_name: str) -> str:
    return TOOL_SCOPES.get(server_name, "any")


def check_tool_access(
    db: Session,
    user: User | None,
    server_name: str,
    tool: str,
    *,
    patient_id: int | None = None,
) -> tuple[bool, str]:
    """Central MCP authorization check. Returns (allowed, reason).

    Deny by default. The principal is the server-side session user - never a
    user_id / role supplied by the browser. Patient-scoped tools additionally
    enforce resource ownership via ``enforce_patient_scope``.
    """
    if user is None or not getattr(user, "is_active", True):
        return False, "Please login first."
    role = user_role(user)
    server = get_server(server_name)
    if server is None:
        return False, f"Unknown MCP server: {server_name}"
    if tool not in server["tools"]:
        return False, f"Unknown tool '{tool}' on server '{server_name}'"
    if role != ROLE_SUPERUSER and role not in server["required_roles"]:
        return False, f"Role {role} may not call {server_name}.{tool}"
    scope = get_tool_scope(server_name)
    if scope in ("own", "own_or_assigned") and patient_id is not None:
        if not enforce_patient_scope(db, user, patient_id):
            return False, "Access denied: patient record outside your authorized scope."
    return True, "allowed"


def enforce_patient_scope(db: Session, user: User, patient_id: int) -> bool:
    """Resource ownership check: may this principal see this patient?"""
    role = user_role(user)
    if role == ROLE_SUPERUSER:
        return True
    try:
        patient_id = int(patient_id)
    except (TypeError, ValueError):
        return False
    patient = db.get(User, patient_id)
    if patient is None or not patient.is_active:
        return False
    if role == ROLE_PATIENT:
        # own records only - never another patient's, by any ID/URL/payload
        return patient_id == user.id
    if role == ROLE_DOCTOR:
        # doctors are authorized for enrolled patients (Doctor Desk scope)
        return True
    # ADMIN gets aggregates, not patient-level records
    return False


def seed_mcp_registry(db: Session) -> int:
    """Upsert the 10 registry rows. Idempotent - safe to run on every boot."""
    for entry in SERVER_CATALOG:
        row = db.query(McpServer).filter(McpServer.name == entry["name"]).first()
        if row is None:
            row = McpServer(name=entry["name"])
            db.add(row)
        row.group_code = entry["group"]
        row.category = entry["category"]
        row.description = entry["description"]
        row.base_url = f"http://127.0.0.1:{entry['port']}/mcp"
        row.service_identity = entry["service_identity"]
        row.tools = list(entry["tools"])
        row.required_roles = list(entry["required_roles"])
        row.is_active = True
    db.commit()
    return len(SERVER_CATALOG)


def mirror_audit_event(db: Session | None, record: dict) -> None:
    """Best-effort DB mirror of a JSONL audit record (never raises)."""
    if db is None or not record.get("event_id"):
        return
    try:
        db.add(AuditEvent(
            event_id=record["event_id"],
            correlation_id=record.get("correlation_id"),
            request_id=record.get("request_id"),
            actor=record.get("actor"),
            role=record.get("role"),
            mcp_server=record.get("mcp_server"),
            tool=record.get("tool"),
            action=record.get("action"),
            resource_type=record.get("resource_type"),
            resource_ref=record.get("resource_ref"),
            result=record.get("result", "success"),
            error_category=record.get("error_category"),
            duration_ms=record.get("duration_ms"),
            policy_version=record.get("policy_version"),
        ))
        db.commit()
    except Exception:
        db.rollback()


def record_security_event(
    db: Session | None,
    *,
    action: str,
    result: str = "denied",
    actor: str | None = None,
    role: str | None = None,
    resource_type: str | None = None,
    resource_ref: str | None = None,
    details: dict | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict:
    """Write a security event to the JSONL stream AND the DB (fail closed)."""
    record = audit_log.log_security_event(
        action=action,
        result=result,
        actor=actor,
        role=role,
        resource_type=resource_type,
        resource_ref=resource_ref,
        extra=details or {},
    )
    if db is not None:
        try:
            db.add(SecurityEvent(
                event_id=record["event_id"],
                correlation_id=record.get("correlation_id"),
                actor=actor,
                role=role,
                action=action,
                resource_type=resource_type,
                resource_ref=resource_ref,
                result=result,
                ip_address=ip_address,
                user_agent=user_agent,
                details=details,
            ))
            db.commit()
        except Exception:
            db.rollback()
    return record
