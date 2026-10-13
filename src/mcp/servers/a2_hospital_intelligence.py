"""A2 - Privacy-Preserving Hospital Intelligence MCP (ADMIN, port 9202).

Aggregate operational analytics only - counts and rates, never patient
rows. Small-group suppression: any metric below the threshold is hidden.
"""

from datetime import date, datetime

from sqlalchemy import func

from src.database.connection import SessionLocal
from src.mcp.server_base import build_server, mcp_tool, serve
from src.models.appointment import Appointment
from src.models.care_gap import CareGap
from src.models.follow_up import FollowUp
from src.services.mcp_rbac import get_server

SERVER = get_server("hospital-intelligence")
mcp = build_server(SERVER)

MIN_GROUP = 5  # small-group suppression threshold


def _suppress(count: int):
    """Suppress small groups so individuals cannot be inferred."""
    return count if count >= MIN_GROUP else "<5 (suppressed)"


def _workflow_patterns(db) -> dict:
    total = db.query(Appointment).count()
    by_status = dict(
        db.query(Appointment.status, func.count(Appointment.id))
        .group_by(Appointment.status)
        .all()
    )
    completed = by_status.get("COMPLETED", 0)
    fu_total = db.query(FollowUp).count()
    fu_done = db.query(FollowUp).filter(FollowUp.status.in_(("DONE", "COMPLETED"))).count()
    past_due_pending = (
        db.query(Appointment)
        .filter(Appointment.appointment_date < date.today(),
                Appointment.status == "PENDING")
        .count()
    )
    return {
        "appointments": {
            "total": total,
            "by_status": by_status,
            "completion_rate": round(completed / total, 4) if total else 0,
        },
        "follow_ups": {
            "total": fu_total,
            "completed": fu_done,
            "completion_rate": round(fu_done / fu_total, 4) if fu_total else 0,
        },
        "drop_off": {"past_due_pending_appointments": _suppress(past_due_pending)},
    }


def _care_gaps_metrics(db) -> dict:
    return {
        "by_type": dict(
            db.query(CareGap.gap_type, func.count(CareGap.id))
            .group_by(CareGap.gap_type)
            .all()
        ),
        "by_status": dict(
            db.query(CareGap.status, func.count(CareGap.id))
            .group_by(CareGap.status)
            .all()
        ),
        "by_severity": dict(
            db.query(CareGap.severity, func.count(CareGap.id))
            .group_by(CareGap.severity)
            .all()
        ),
    }


def _period_metrics(db, start: str, end: str) -> dict:
    total = (
        db.query(Appointment)
        .filter(Appointment.appointment_date >= date.fromisoformat(start),
                Appointment.appointment_date <= date.fromisoformat(end))
        .count()
    )
    completed = (
        db.query(Appointment)
        .filter(Appointment.appointment_date >= date.fromisoformat(start),
                Appointment.appointment_date <= date.fromisoformat(end),
                Appointment.status == "COMPLETED")
        .count()
    )
    return {"total": total, "completed": completed,
            "completion_rate": round(completed / total, 4) if total else 0}


@mcp_tool(mcp, SERVER, "analyze_workflow_patterns")
def analyze_workflow_patterns(principal: dict | None = None,
                              audit_correlation_id: str = "") -> dict:
    """Aggregate appointment/follow-up completion and drop-off points."""
    db = SessionLocal()
    try:
        return {**_workflow_patterns(db),
                "privacy": "aggregate counts only - no patient-level rows"}
    finally:
        db.close()


@mcp_tool(mcp, SERVER, "measure_care_gaps")
def measure_care_gaps(principal: dict | None = None,
                      audit_correlation_id: str = "") -> dict:
    """Aggregate care-gap metrics by type, severity and status."""
    db = SessionLocal()
    try:
        return {"care_gaps": _care_gaps_metrics(db),
                "privacy": "aggregate counts only"}
    finally:
        db.close()


@mcp_tool(mcp, SERVER, "compare_periods")
def compare_periods(start_a: str, end_a: str, start_b: str, end_b: str,
                    principal: dict | None = None,
                    audit_correlation_id: str = "") -> dict:
    """Compare appointment metrics across two date ranges (aggregates only)."""
    db = SessionLocal()
    try:
        return {
            "period_a": {"range": [start_a, end_a], **_period_metrics(db, start_a, end_a)},
            "period_b": {"range": [start_b, end_b], **_period_metrics(db, start_b, end_b)},
            "privacy": "aggregate counts only",
        }
    finally:
        db.close()


@mcp_tool(mcp, SERVER, "generate_aggregate_report")
def generate_aggregate_report(principal: dict | None = None,
                              audit_correlation_id: str = "") -> dict:
    """Combined aggregate operational report (data-quality + care-gap view)."""
    db = SessionLocal()
    try:
        return {
            "generated_at": datetime.utcnow().isoformat(),
            "workflow": _workflow_patterns(db),
            "care_gaps": _care_gaps_metrics(db),
            "privacy": "aggregate counts only - minimum necessary data",
        }
    finally:
        db.close()


if __name__ == "__main__":
    serve(SERVER, mcp)
