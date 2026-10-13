"""Structured, persistent, multi-stream audit logging for the MCP platform.

Nine logically separate JSON Lines streams (per the platform specification):

    application.log          FastAPI startup/shutdown, route errors, ops events
    mcp_gateway_audit.log    incoming MCP-related requests, principal, outcome
    mcp_tool_events.log      tool execution start/end, duration, validation
    security_events.log      auth failures, denials, rate limits, privileged ops
    ai_evidence_audit.log    request ID, evidence refs, grounding, refusals
    clinical_review.log      conflict cases, assignments, resolutions
    workflow_recovery.log    failed workflows, retries, idempotency, results
    change_approval.log      proposed changes, approver, before/after, rollback
    ai_benchmark.log         suite version, test IDs, metrics, regressions

Every record carries a UTC timestamp, a unique event ID, correlation and
request IDs, the authenticated actor or service identity, role, MCP server,
tool, action category, a safe resource reference, the result, error category,
execution duration and the policy version. Sensitive fields are redacted
before anything is written. Streams rotate, persist across restarts and are
append-only in practice.
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

from src.services.audit_context import (
    get_correlation_id,
    get_principal,
    get_request_id,
)

BASE_DIR = Path(__file__).resolve().parents[2]
LOG_DIR = Path(os.environ.get("MCP_LOG_DIR") or (BASE_DIR / "logs"))

STREAMS = (
    "application",
    "mcp_gateway_audit",
    "mcp_tool_events",
    "security_events",
    "ai_evidence_audit",
    "clinical_review",
    "workflow_recovery",
    "change_approval",
    "ai_benchmark",
)

POLICY_VERSION = os.environ.get("MCP_POLICY_VERSION", "1.0.0")

# Rotation / retention: 5 MB per file, 5 backups per stream.
_MAX_BYTES = int(os.environ.get("MCP_LOG_MAX_BYTES", str(5 * 1024 * 1024)))
_BACKUP_COUNT = int(os.environ.get("MCP_LOG_BACKUP_COUNT", "5"))

# Keys whose values must never reach a log file.
_SENSITIVE_KEY_RE = re.compile(
    r"(?i)(password|passwd|secret|api[_-]?key|access[_-]?key|token|"
    r"authorization|cookie|session|credential|otp|pin|cvv|card)"
)
# Obvious secret shapes inside free text.
_SECRET_TEXT_RES = (
    re.compile(r"(?i)bearer\s+[a-z0-9._~+/=-]+"),
    re.compile(r"(?i)(password|passwd|secret|api[_-]?key)\s*[:=]\s*\S+"),
)

_LOGGERS: dict[str, logging.Logger] = {}


def _redact_text(text: str) -> str:
    for pattern in _SECRET_TEXT_RES:
        text = pattern.sub("***REDACTED***", text)
    return text


def _redact(value):
    """Recursively redact sensitive keys/values before logging."""
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if _SENSITIVE_KEY_RE.search(str(key)):
                out[key] = "***REDACTED***"
            else:
                out[key] = _redact(item)
        return out
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        return _redact_text(value)
    return value


class _JsonFormatter(logging.Formatter):
    """One JSON object per line - the whole record, nothing else."""

    def format(self, record: logging.LogRecord) -> str:
        payload = record.msg if isinstance(record.msg, dict) else {"message": str(record.msg)}
        try:
            return json.dumps(payload, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            return json.dumps({"message": "unserializable log record"}, default=str)


def get_logger(stream: str) -> logging.Logger:
    """Return (creating on first use) the JSONL logger for one stream."""
    if stream not in STREAMS:
        raise ValueError(f"unknown log stream: {stream!r}")
    logger = _LOGGERS.get(stream)
    if logger is not None:
        return logger
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(f"mcp.{stream}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = RotatingFileHandler(
        LOG_DIR / f"{stream}.log",
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setFormatter(_JsonFormatter())
    logger.addHandler(handler)
    _LOGGERS[stream] = logger
    return logger


def log_event(
    stream: str,
    *,
    event_id: str | None = None,
    correlation_id: str | None = None,
    request_id: str | None = None,
    actor: str | None = None,
    role: str | None = None,
    mcp_server: str | None = None,
    tool: str | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    resource_ref: str | None = None,
    result: str = "success",
    error_category: str | None = None,
    duration_ms: float | None = None,
    policy_version: str | None = None,
    required: bool = False,
    **extra,
) -> dict:
    """Write one structured event to a stream. Returns the record.

    ``required=True`` makes an audit failure raise (fail closed) - use it
    for sensitive operations whose audit trail is required for safety.
    """
    record = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "event_id": event_id or uuid.uuid4().hex,
        "correlation_id": correlation_id or get_correlation_id() or None,
        "request_id": request_id or get_request_id() or None,
        "actor": actor or (get_principal() or {}).get("actor"),
        "role": role or (get_principal() or {}).get("role"),
        "mcp_server": mcp_server,
        "tool": tool,
        "action": action,
        "resource_type": resource_type,
        "resource_ref": resource_ref,
        "result": result,
        "error_category": error_category,
        "duration_ms": duration_ms,
        "policy_version": policy_version or POLICY_VERSION,
    }
    if extra:
        record["extra"] = extra
    record = _redact(record)

    try:
        get_logger(stream).info(record)
    except Exception:
        if required:
            raise
        # operational logging must never take the request down
        logging.getLogger("mcp.fallback").exception("audit log write failed")
    return record


def log_security_event(action: str, result: str = "denied", **kwargs) -> dict:
    """Convenience wrapper for the security stream (fail closed)."""
    kwargs.setdefault("action", action)
    kwargs.setdefault("result", result)
    return log_event("security_events", required=True, **kwargs)
