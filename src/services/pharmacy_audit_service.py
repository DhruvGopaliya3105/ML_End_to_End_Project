"""Audit trail writer / reader for the pharmacy module.

Called by the pharmacy services (not by the templates), because a log entry
that a page could forget to write is not an audit trail.

Everything here is defensive: a broken audit write must never roll back a
patient's order. If the log table is missing (fresh database before the first
startup) the row is skipped and the error goes to the normal app log.
"""

import json
import logging
from datetime import (
    date,
    datetime,
    time
)
from decimal import Decimal

from fastapi import Request
from sqlalchemy import (
    cast,
    func,
    or_,
    Date
)
from sqlalchemy.orm import Session

from src.models.pharmacy_audit_log import PharmacyAuditLog


logger = logging.getLogger(__name__)


# =========================================================
# HELPERS
# =========================================================

def _json_safe(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


def dumps(value) -> str | None:
    if value is None:
        return None
    try:
        return json.dumps(
            value,
            default=_json_safe,
            ensure_ascii=False,
            sort_keys=True
        )
    except Exception:  # noqa: BLE001 - logging must never break a request
        return json.dumps(
            {"unserialisable": str(value)[:500]},
            ensure_ascii=False
        )


def row_to_dict(obj, redact: tuple[str, ...] = ()) -> dict | None:
    """Column values of a SQLAlchemy model instance as a plain dict."""

    if obj is None:
        return None

    out = {}

    for column in obj.__table__.columns:
        if column.name in redact:
            out[column.name] = "***"
            continue

        out[column.name] = getattr(obj, column.name)

    return out


def _client_ip(request: Request | None) -> str | None:
    if request is None:
        return None

    forwarded = request.headers.get("x-forwarded-for")

    if forwarded:
        return forwarded.split(",")[0].strip()[:60]

    client = getattr(request, "client", None)

    if client is not None:
        return str(client.host)[:60]

    return None


# =========================================================
# WRITE
# =========================================================

def log_activity(
    db: Session,
    *,
    action: str,
    actor: dict | None = None,
    entity_type: str | None = None,
    entity_id: int | str | None = None,
    description: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
    severity: str = "INFO",
    request: Request | None = None,
    rollback_available: bool = False,
    snapshot_id: int | None = None,
    commit: bool = False
) -> PharmacyAuditLog | None:

    actor = actor or {}

    entry = PharmacyAuditLog(
        severity=severity,
        action=action[:80],
        entity_type=entity_type[:40] if entity_type else None,
        entity_id=str(entity_id)[:40] if entity_id is not None else None,
        description=(description or "")[:500] or None,
        actor_user_id=actor.get("user_id"),
        actor_name=(actor.get("name") or "Anonymous")[:120],
        actor_role=(actor.get("role") or "GUEST")[:20],
        before_json=dumps(before),
        after_json=dumps(after),
        rollback_available=rollback_available,
        snapshot_id=snapshot_id,
        ip_address=_client_ip(request),
        user_agent=(
            request.headers.get("user-agent", "")[:300]
            if request is not None else None
        ),
        request_path=(
            (request.url.path or "")[:300] if request is not None else None
        ),
        created_at=datetime.utcnow()
    )

    try:

        db.add(entry)

        if commit:
            db.commit()
        else:
            db.flush()

    except Exception:  # noqa: BLE001
        logger.exception("pharmacy audit log write failed (%s)", action)
        db.rollback()
        return None

    return entry


def log_change(
    db: Session,
    *,
    action: str,
    before_obj,
    after_obj=None,
    **kwargs
) -> PharmacyAuditLog | None:
    """Convenience wrapper: pass model instances, get before/after dicts."""

    return log_activity(
        db,
        action=action,
        before=row_to_dict(before_obj),
        after=row_to_dict(after_obj) if after_obj is not None else None,
        **kwargs
    )


# =========================================================
# READ
# =========================================================

def build_query(
    db: Session,
    *,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    actor: str | None = None,
    severity: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    search: str | None = None
):

    query = db.query(PharmacyAuditLog)

    if action:
        query = query.filter(PharmacyAuditLog.action == action)

    if entity_type:
        query = query.filter(
            PharmacyAuditLog.entity_type == entity_type
        )

    if entity_id:
        query = query.filter(
            PharmacyAuditLog.entity_id == str(entity_id)
        )

    if actor:
        like = f"%{actor}%"
        query = query.filter(
            or_(
                PharmacyAuditLog.actor_name.ilike(like),
                PharmacyAuditLog.actor_user_id.cast(StringType()).ilike(like)
            )
        )

    if severity:
        query = query.filter(PharmacyAuditLog.severity == severity)

    if date_from:
        try:
            start = datetime.strptime(date_from, "%Y-%m-%d")
            query = query.filter(PharmacyAuditLog.created_at >= start)
        except ValueError:
            pass

    if date_to:
        try:
            end = datetime.strptime(date_to, "%Y-%m-%d").replace(
                hour=23,
                minute=59,
                second=59
            )
            query = query.filter(PharmacyAuditLog.created_at <= end)
        except ValueError:
            pass

    if search:
        like = f"%{search}%"
        query = query.filter(
            or_(
                PharmacyAuditLog.description.ilike(like),
                PharmacyAuditLog.action.ilike(like),
                PharmacyAuditLog.entity_id.ilike(like),
                PharmacyAuditLog.actor_name.ilike(like)
            )
        )

    return query


# `str` works for cast() on both MySQL and SQLite, kept in one place so the
# import above does not look like a mistake.
def StringType():  # noqa: N802 - matches SQLAlchemy naming
    from sqlalchemy import String
    return String()


def list_logs(
    db: Session,
    *,
    limit: int = 100,
    offset: int = 0,
    **filters
) -> list[PharmacyAuditLog]:

    return (
        build_query(db, **filters)
        .order_by(PharmacyAuditLog.created_at.desc(), PharmacyAuditLog.id.desc())
        .offset(max(0, offset))
        .limit(min(max(1, limit), 500))
        .all()
    )


def count_logs(db: Session, **filters) -> int:
    return build_query(db, **filters).count()


def to_log_dict(entry: PharmacyAuditLog) -> dict:
    return {
        "id": entry.id,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
        "created_at_display": (
            entry.created_at.strftime("%d %b %Y, %I:%M %p")
            if entry.created_at else ""
        ),
        "severity": entry.severity,
        "action": entry.action,
        "entity_type": entry.entity_type,
        "entity_id": entry.entity_id,
        "description": entry.description,
        "actor_name": entry.actor_name,
        "actor_role": entry.actor_role,
        "actor_user_id": entry.actor_user_id,
        "rollback_available": entry.rollback_available,
        "snapshot_id": entry.snapshot_id,
        "ip_address": entry.ip_address,
        "before_json": entry.before_json,
        "after_json": entry.after_json,
    }


def action_options(db: Session) -> list[str]:
    return [
        row[0]
        for row in (
            db.query(PharmacyAuditLog.action)
            .distinct()
            .order_by(PharmacyAuditLog.action)
            .all()
        )
    ]


def as_csv(rows: list[dict]) -> str:
    import csv
    import io

    buffer = io.StringIO()

    fields = [
        "created_at", "severity", "actor_name", "actor_role", "action",
        "entity_type", "entity_id", "description", "ip_address",
        "rollback_available", "snapshot_id",
    ]

    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()

    for row in rows:
        writer.writerow(row)

    return buffer.getvalue()


# Re-exported so callers do not have to import `func` themselves for the
# small "events today" counter on the admin dashboard.
def events_on_day(db: Session, day: date) -> int:
    return (
        db.query(func.count(PharmacyAuditLog.id))
        .filter(cast(PharmacyAuditLog.created_at, Date) == day)
        .scalar()
        or 0
    )
