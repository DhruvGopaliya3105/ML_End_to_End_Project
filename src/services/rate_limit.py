"""In-memory rate limiting (per-process) for auth + gateway endpoints.

Local-dev grade: fixed windows per key, process-local store. Callers record
limited events to security_events. For a multi-process deployment, swap
the store for Redis - the interface (check_limit / reset_limits) stays the
same.
"""

from __future__ import annotations

import os
import time
from collections import defaultdict, deque

# bucket -> (max requests, window seconds)
WINDOWS = {
    "login": (int(os.environ.get("RATE_LIMIT_LOGIN", "10")), 300),     # 10 / 5 min
    "gateway": (int(os.environ.get("RATE_LIMIT_GATEWAY", "120")), 60),  # 120 / min
}

_hits: dict[str, deque] = defaultdict(deque)


def check_limit(bucket: str, key: str) -> tuple[bool, int]:
    """Return (allowed, retry_after_seconds) for one bucket+key."""
    limit, window = WINDOWS.get(bucket, (60, 60))
    now = time.time()
    queue = _hits[f"{bucket}:{key}"]
    while queue and queue[0] <= now - window:
        queue.popleft()
    if len(queue) >= limit:
        return False, int(queue[0] + window - now) + 1
    queue.append(now)
    return True, 0


def reset_limits() -> None:
    """Clear all counters (used by tests)."""
    _hits.clear()
