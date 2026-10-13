"""Start all 10 MCP servers for local development.

    python -m src.mcp.run_all

Each server gets its own port + service identity and is reachable only
with the shared MCP_SERVICE_TOKEN (see src/mcp/server_base.py). Servers
bind 127.0.0.1 on purpose - they are internal services; the FastAPI
gateway is the only door browsers can use.
"""

from __future__ import annotations

import threading
import time

from src.mcp.server_base import serve
from src.mcp.servers import (
    a1_clinical_safety,
    a2_hospital_intelligence,
    a3_change_approval,
    s1_ai_reliability,
    s2_flight_recorder,
    u1_care_gap,
    u2_evidence_ai,
    u3_health_timeline,
    u4_workflow_simulator,
    u5_care_continuity,
)
from src.services.mcp_rbac import SERVER_CATALOG

MODULES = [
    u1_care_gap, u2_evidence_ai, u3_health_timeline,
    u4_workflow_simulator, u5_care_continuity,
    a1_clinical_safety, a2_hospital_intelligence, a3_change_approval,
    s1_ai_reliability, s2_flight_recorder,
]


def main() -> None:
    threads = []
    for mod in MODULES:
        entry = mod.SERVER
        t = threading.Thread(
            target=serve, args=(entry, mod.mcp),
            daemon=True, name=entry["name"],
        )
        t.start()
        threads.append(t)
        time.sleep(0.2)
    print(f"Started {len(threads)} MCP servers: "
          + ", ".join(e["name"] for e in SERVER_CATALOG))
    print("Press Ctrl+C to stop all.")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("Stopping all MCP servers.")


if __name__ == "__main__":
    main()
