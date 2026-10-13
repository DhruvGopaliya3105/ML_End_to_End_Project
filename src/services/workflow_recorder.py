"""Flight-recorder event recording for payments + appointments.

Every significant workflow state transition is recorded with a correlation
ID (from the audit-context middleware) and an idempotency key, so the
flight-recorder MCP server can reconstruct and safely reconcile failed
workflows. Recording is best-effort: it never breaks the main request flow.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from src.models.workflow_event import WorkflowEvent
from src.services import audit_log
from src.services.audit_context import get_correlation_id


def record_workflow_event(
    db: Session,
    *,
    workflow_type: str,
    resource_type: str,
    resource_ref: str,
    event_type: str,
    payload: dict | None = None,
    idempotency_key: str | None = None,
    correlation_id: str | None = None,
) -> None:
    """Record one workflow event (best-effort, never raises)."""
    correlation_id = correlation_id or get_correlation_id() or uuid.uuid4().hex
    try:
        db.add(WorkflowEvent(
            correlation_id=correlation_id,
            workflow_type=workflow_type,
            resource_type=resource_type,
            resource_ref=resource_ref,
            event_type=event_type,
            payload=payload,
            idempotency_key=idempotency_key,
        ))
        db.flush()
    except Exception:
        pass  # the flight recorder must never break the main flow
    audit_log.log_event(
        "workflow_recovery",
        action=event_type.lower(),
        resource_type=resource_type,
        resource_ref=resource_ref,
        correlation_id=correlation_id,
        result="success",
        extra={"workflow": workflow_type},
    )
