"""MCP Intelligence Platform routes - FastAPI gateway to the 10 MCP servers.

The page ``/mcp`` (newpage.html) is the single intelligence console; every
section loads real server data through these endpoints. The browser never
talks to the MCP servers directly - all calls go through the gateway, which
authenticates, authorizes, times out and logs them.

Frontend visibility is not security enforcement: every endpoint here
independently validates the session + role, and the MCP servers re-check
on their side (defense in depth).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
)
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.database.connection import get_db
from src.models.ai_benchmark import AiBenchmarkResult, AiBenchmarkRun
from src.models.audit_event import AuditEvent, SecurityEvent
from src.models.care_gap import CareGap, CareReviewTask
from src.models.change_request import ChangeApproval, ChangeRequest
from src.models.clinical_conflict import ClinicalConflict
from src.models.mcp_registry import McpServer
from src.models.user import User
from src.models.workflow_event import RecoveryAttempt, WorkflowEvent
from src.security.rbac import (
    PERMISSIONS,
    ROLE_ADMIN,
    ROLE_DOCTOR,
    ROLE_PATIENT,
    ROLE_SUPERUSER,
    ROLES,
    get_session_user,
    role_has_default,
    role_permission_rows,
    user_role,
)
from src.services.audit_context import set_principal
from src.services.mcp_rbac import record_security_event
from src.services.mcp_gateway import call_tool, refresh_health
from src.services.mcp_rbac import SERVER_CATALOG

router = APIRouter(prefix="/mcp", tags=["mcp-platform"])

templates = Jinja2Templates(directory="templates")

ADMIN_ROLES = (ROLE_ADMIN, ROLE_SUPERUSER)


class ToolCallBody(BaseModel):
    server: str
    tool: str
    params: dict = {}


def _user(request: Request, db: Session) -> User | None:
    return get_session_user(request, db)


def _require_login(user: User | None) -> User:
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Please login first.")
    return user


def _require_roles(user: User, roles: tuple[str, ...]) -> User:
    role = user_role(user)
    if role not in roles and role != ROLE_SUPERUSER:
        raise HTTPException(status_code=403, detail="Not authorized for this section.")
    return user


def _principal(user: User) -> dict:
    role = user_role(user)
    principal = {"email": user.email, "role": role, "user_id": user.id}
    set_principal({"actor": user.email, "role": role, "user_id": user.id})
    return principal


# ============================================================
# PAGE
# ============================================================

@router.get("", response_class=HTMLResponse)
def mcp_page(request: Request, db: Session = Depends(get_db)):
    """The intelligence console - role-based sections, real server data."""
    user = _user(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    role = user_role(user)
    return templates.TemplateResponse(
        request,
        "newpage.html",
        {
            "user": user,
            "role": role,
            "patient_id": user.id if role == ROLE_PATIENT else "",
        },
    )


# ============================================================
# OVERVIEW (any logged-in role)
# ============================================================

@router.get("/api/overview")
def overview(request: Request, db: Session = Depends(get_db)):
    user = _require_login(_user(request, db))
    _principal(user)
    role = user_role(user)

    total_users = db.query(User).count()
    by_role = dict(
        db.query(User.role, func.count(User.id)).group_by(User.role).all()
    )
    servers = db.query(McpServer).all()
    online = sum(1 for s in servers if s.status == "ONLINE")
    since = datetime.utcnow() - timedelta(hours=24)
    denied_24h = (
        db.query(SecurityEvent)
        .filter(SecurityEvent.created_at >= since,
                SecurityEvent.result == "denied")
        .count()
    )
    recent_security = (
        db.query(SecurityEvent)
        .order_by(SecurityEvent.created_at.desc())
        .limit(5)
        .all()
    )
    return {
        "current_role": role,
        "users": {"total": total_users, "by_role": by_role},
        "mcp": {
            "total": len(SERVER_CATALOG),
            "online": online,
            "offline": len(SERVER_CATALOG) - online,
        },
        "security": {
            "denied_last_24h": denied_24h,
            "recent": [
                {"at": e.created_at.isoformat(), "action": e.action,
                 "actor": e.actor, "result": e.result,
                 "ref": e.resource_ref}
                for e in recent_security
            ],
        },
        "tasks": {
            "pending_review_tasks": db.query(CareReviewTask).filter(
                CareReviewTask.status != "DONE").count(),
            "open_care_gaps": db.query(CareGap).filter(
                CareGap.status == "OPEN").count(),
            "open_conflicts": db.query(ClinicalConflict).filter(
                ClinicalConflict.status != "RESOLVED").count(),
            "pending_change_requests": db.query(ChangeRequest).filter(
                ChangeRequest.status == "PENDING").count(),
            "unresolved_incidents": db.query(RecoveryAttempt).filter(
                RecoveryAttempt.status.in_(("PENDING", "IN_PROGRESS", "ESCALATED"))).count(),
        },
    }


# ============================================================
# MCP REGISTRY + HEALTH (admin / superuser)
# ============================================================

@router.get("/api/registry")
async def registry(request: Request, db: Session = Depends(get_db)):
    user = _require_roles(_require_login(_user(request, db)), ADMIN_ROLES)
    _principal(user)
    return {"servers": await refresh_health(db)}


# ============================================================
# GENERIC TOOL CALL (any logged-in role; RBAC enforced)
# ============================================================

@router.post("/api/call")
async def mcp_call(body: ToolCallBody, request: Request,
                   db: Session = Depends(get_db)):
    user = _require_login(_user(request, db))
    _principal(user)

    # ---- rate limit (per user) ----
    from src.services.rate_limit import check_limit

    allowed, retry_after = check_limit("gateway", user.email)
    if not allowed:
        record_security_event(
            db,
            action="rate_limited",
            actor=user.email,
            role=user_role(user),
            resource_type="mcp_gateway",
            resource_ref=f"{body.server}.{body.tool}",
            details={"retry_after_seconds": retry_after},
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent")
        )
        raise HTTPException(
            status_code=429,
            detail=f"Too many requests. Try again in {retry_after} seconds."
        )

    return await call_tool(db, user, body.server, body.tool, body.params)


# ============================================================
# AUDIT EXPLORER (admin / superuser)
# ============================================================

@router.get("/api/audit")
def audit_events(request: Request, db: Session = Depends(get_db),
                 hours: int = 24, actor: str = "", role: str = "",
                 server: str = "", tool: str = "", action: str = "",
                 result: str = "", correlation_id: str = "",
                 limit: int = 200):
    user = _require_roles(_require_login(_user(request, db)), ADMIN_ROLES)
    _principal(user)
    since = datetime.utcnow() - timedelta(hours=max(1, hours))
    query = db.query(AuditEvent).filter(AuditEvent.created_at >= since)
    if actor:
        query = query.filter(AuditEvent.actor.ilike(f"%{actor}%"))
    if role:
        query = query.filter(AuditEvent.role == role.upper())
    if server:
        query = query.filter(AuditEvent.mcp_server == server)
    if tool:
        query = query.filter(AuditEvent.tool == tool)
    if action:
        query = query.filter(AuditEvent.action == action)
    if result:
        query = query.filter(AuditEvent.result == result)
    if correlation_id:
        query = query.filter(AuditEvent.correlation_id == correlation_id)
    rows = query.order_by(AuditEvent.created_at.desc()).limit(min(limit, 500)).all()
    return {
        "count": len(rows),
        "events": [
            {"event_id": e.event_id, "at": e.created_at.isoformat(),
             "correlation_id": e.correlation_id, "actor": e.actor,
             "role": e.role, "server": e.mcp_server, "tool": e.tool,
             "action": e.action, "resource": e.resource_ref,
             "result": e.result, "error": e.error_category,
             "duration_ms": e.duration_ms}
            for e in rows
        ],
    }


@router.get("/api/security-events")
def security_events(request: Request, db: Session = Depends(get_db),
                    limit: int = 50):
    user = _require_roles(_require_login(_user(request, db)), ADMIN_ROLES)
    _principal(user)
    rows = (
        db.query(SecurityEvent)
        .order_by(SecurityEvent.created_at.desc())
        .limit(min(limit, 200))
        .all()
    )
    return {
        "count": len(rows),
        "events": [
            {"event_id": e.event_id, "at": e.created_at.isoformat(),
             "correlation_id": e.correlation_id, "actor": e.actor,
             "role": e.role, "action": e.action, "result": e.result,
             "ref": e.resource_ref, "ip": e.ip_address}
            for e in rows
        ],
    }


# ============================================================
# AI SAFETY CENTER (admin / superuser; superuser runs)
# ============================================================

@router.get("/api/benchmarks")
def benchmarks(request: Request, db: Session = Depends(get_db)):
    user = _require_roles(_require_login(_user(request, db)), ADMIN_ROLES)
    _principal(user)
    latest = (
        db.query(AiBenchmarkRun)
        .order_by(AiBenchmarkRun.created_at.desc())
        .first()
    )
    runs = (
        db.query(AiBenchmarkRun)
        .order_by(AiBenchmarkRun.created_at.desc())
        .limit(20)
        .all()
    )
    latest_results = []
    if latest is not None:
        latest_results = (
            db.query(AiBenchmarkResult)
            .filter(AiBenchmarkResult.run_id == latest.id)
            .all()
        )
    return {
        "latest": None if latest is None else {
            "id": latest.id,
            "suite_version": latest.suite_version,
            "started_at": latest.started_at.isoformat(),
            "total": latest.total_tests,
            "passed": latest.passed,
            "failed": latest.failed,
            "metrics": latest.metrics,
            "results": [
                {"test_id": r.test_id, "category": r.category,
                 "passed": r.passed, "details": r.details}
                for r in latest_results
            ],
        },
        "runs": [
            {"id": r.id, "suite_version": r.suite_version,
             "started_at": r.started_at.isoformat(),
             "total": r.total_tests, "passed": r.passed, "failed": r.failed,
             "metrics": r.metrics}
            for r in runs
        ],
    }


@router.post("/api/benchmarks/run")
async def run_benchmarks(request: Request, db: Session = Depends(get_db)):
    user = _require_roles(_require_login(_user(request, db)), (ROLE_SUPERUSER,))
    _principal(user)
    return await call_tool(db, user, "ai-reliability", "run_safety_benchmarks", {})


# ============================================================
# ACCESS CONTROL - role / permission matrix (admin / superuser)
# ============================================================

@router.get("/api/roles")
def roles_matrix(request: Request, db: Session = Depends(get_db)):
    user = _require_roles(_require_login(_user(request, db)), ADMIN_ROLES)
    _principal(user)
    overrides = role_permission_rows(db)
    matrix = {}
    for role in ROLES:
        matrix[role] = {}
        for key, _desc, _cat in PERMISSIONS:
            matrix[role][key] = overrides.get((role, key), role_has_default(role, key))
    return {
        "current_role": user_role(user),
        "roles": list(ROLES),
        "permissions": [
            {"key": key, "description": desc, "category": cat}
            for key, desc, cat in PERMISSIONS
        ],
        "matrix": matrix,
        "overrides": [
            {"role": role, "permission": permission, "is_allowed": allowed}
            for (role, permission), allowed in sorted(overrides.items())
        ],
    }


# ============================================================
# CHANGE IMPACT + APPROVALS (admin / superuser)
# ============================================================

@router.get("/api/change-requests")
def change_requests(request: Request, db: Session = Depends(get_db),
                    limit: int = 50):
    user = _require_roles(_require_login(_user(request, db)), ADMIN_ROLES)
    _principal(user)
    rows = (
        db.query(ChangeRequest)
        .order_by(ChangeRequest.created_at.desc())
        .limit(min(limit, 200))
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
            "id": cr.id,
            "change_type": cr.change_type,
            "description": cr.description,
            "status": cr.status,
            "proposed_by": cr.proposed_by,
            "impact_preview": cr.impact_preview,
            "rollback_plan": cr.rollback_plan,
            "created_at": cr.created_at.isoformat(),
            "decided_at": cr.decided_at.isoformat() if cr.decided_at else None,
            "decided_by": cr.decided_by,
            "approvals": [
                {"approver": a.approver, "decision": a.decision,
                 "decided_at": a.decided_at.isoformat(), "notes": a.notes}
                for a in approvals
            ],
        })
    return {"change_requests": out}


@router.post("/api/change-requests/preview")
async def preview_change(body: dict, request: Request,
                         db: Session = Depends(get_db)):
    user = _require_roles(_require_login(_user(request, db)), ADMIN_ROLES)
    _principal(user)
    change = dict(body.get("change") or {})
    return await call_tool(
        db, user, "change-approval", "preview_change_impact",
        {"change": change},
    )


# ============================================================
# FLIGHT RECORDER + RECOVERY (admin / superuser)
# ============================================================

@router.get("/api/recovery")
def recovery(request: Request, db: Session = Depends(get_db),
             limit: int = 50):
    user = _require_roles(_require_login(_user(request, db)), ADMIN_ROLES)
    _principal(user)
    attempts = (
        db.query(RecoveryAttempt)
        .order_by(RecoveryAttempt.created_at.desc())
        .limit(min(limit, 200))
        .all()
    )
    events = (
        db.query(WorkflowEvent)
        .order_by(WorkflowEvent.created_at.desc())
        .limit(min(limit, 200))
        .all()
    )
    return {
        "attempts": [
            {"id": a.id, "correlation_id": a.correlation_id,
             "incident_type": a.incident_type, "status": a.status,
             "attempts": a.attempts, "idempotency_key": a.idempotency_key,
             "result": a.result,
             "created_at": a.created_at.isoformat(),
             "completed_at": a.completed_at.isoformat() if a.completed_at else None}
            for a in attempts
        ],
        "recent_events": [
            {"id": e.id, "correlation_id": e.correlation_id,
             "workflow": e.workflow_type, "type": e.event_type,
             "resource": e.resource_ref, "at": e.created_at.isoformat(),
             "idempotency_key": e.idempotency_key}
            for e in events
        ],
    }
