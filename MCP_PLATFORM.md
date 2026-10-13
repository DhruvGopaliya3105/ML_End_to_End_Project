# 🧠 MCP Intelligence Platform — Sanjeevani Clinic

A research-grade, evidence-grounded, secure healthcare intelligence layer
integrated into the existing Sanjeevani Clinic project. **10 independent
FastMCP servers** sit behind an authenticated FastAPI gateway; every answer
the chatbot gives is validated against the clinic's own records; every
action is audited across **9 separate log streams**.

Nothing existing was replaced: pharmacy, appointments, doctor desk, chatbot,
payments, ML screening — all still work (see *Verify* below).

---

## 1. Architecture

```
 Patient / Doctor / Admin / Superuser
        │  browser (session cookie)
        ▼
 ┌─────────────┐   newpage.html  (/mcp console, role-based sections)
 │   FastAPI   │────────────────┐
 │  (main.py)  │                │
 └──────┬──────┘                │
        │  MCP gateway (src/services/mcp_gateway.py)
        │  - authenticates (server-side session)
        │  - authorizes (check_tool_access - deny by default)
        │  - propagates principal + correlation ID
        │  - timeouts -> controlled statuses, never stack traces
        ▼
 ┌──────────────────────────────────────────────┐
 │  10 FastMCP servers (streamable HTTP, 127.0.0.1) │
 │  U1 care-gap-intelligence      :9101  (USER)    │
 │  U2 evidence-ai                :9102  (USER)    │
 │  U3 health-timeline            :9103  (USER)    │
 │  U4 workflow-simulator         :9104  (USER)    │
 │  U5 care-continuity            :9105  (USER)    │
 │  A1 clinical-safety            :9201  (ADMIN)   │
 │  A2 hospital-intelligence      :9202  (ADMIN)   │
 │  A3 change-approval            :9203  (ADMIN)   │
 │  S1 ai-reliability             :9301  (SYSTEM)  │
 │  S2 flight-recorder            :9302  (SYSTEM)  │
 └──────────────────────┬───────────────────────────┘
                        ▼
        MySQL (or bundled SQLite) + verified knowledge = the clinic's own records
                        │
                        ▼
   Evidence validation → controlled answer or controlled refusal
   Audit logging → 9 JSONL streams (rotation + redaction)
```

**Request flow:** browser → FastAPI (session auth) → gateway (RBAC +
correlation ID) → MCP server (re-checks RBAC, service token) → database →
structured result → gateway audit → browser. Internal MCP ports are **never
exposed to browsers** — every server requires the shared
`X-MCP-Service-Token` and binds `127.0.0.1` only.

---

## 2. The 10 MCP servers (inventory)

| # | Server | Group | Category | Port | Service identity | Tools | Roles |
|---|--------|-------|----------|------|------------------|-------|-------|
| U1 | care-gap-intelligence | U1 | USER | 9101 | svc-u1-care-gap | detect_care_gaps, trace_missing_steps, get_care_timeline, create_care_review_task | PATIENT, DOCTOR |
| U2 | evidence-ai | U2 | USER | 9102 | svc-u2-evidence-ai | retrieve_evidence, verify_claims, explain_answer_sources, check_information_availability | PATIENT, DOCTOR, ADMIN, SUPERUSER |
| U3 | health-timeline | U3 | USER | 9103 | svc-u3-timeline | build_health_timeline, compare_visits, detect_stale_records, generate_verified_patient_summary | PATIENT, DOCTOR |
| U4 | workflow-simulator | U4 | USER | 9104 | svc-u4-simulator | simulate_scenario, compare_outcomes, explain_assumptions, validate_scenario_inputs | PATIENT, DOCTOR, ADMIN, SUPERUSER |
| U5 | care-continuity | U5 | USER | 9105 | svc-u5-continuity | get_pending_care_steps, check_followup_status, prepare_patient_summary, request_missing_information | PATIENT, DOCTOR |
| A1 | clinical-safety | A1 | ADMIN | 9201 | svc-a1-clinical-safety | detect_record_conflicts, flag_safety_concerns, request_clinical_review, get_conflict_resolution_history | DOCTOR, ADMIN, SUPERUSER |
| A2 | hospital-intelligence | A2 | ADMIN | 9202 | svc-a2-hospital-intel | analyze_workflow_patterns, measure_care_gaps, compare_periods, generate_aggregate_report | ADMIN, SUPERUSER |
| A3 | change-approval | A3 | ADMIN | 9203 | svc-a3-change-approval | preview_change_impact, request_approval, verify_rollback_plan, get_change_history | ADMIN, SUPERUSER |
| S1 | ai-reliability | S1 | SYSTEM | 9301 | svc-s1-ai-reliability | run_safety_benchmarks, test_access_boundaries, evaluate_answer_grounding, compare_versions, generate_test_report | SUPERUSER |
| S2 | flight-recorder | S2 | SYSTEM | 9302 | svc-s2-flight-recorder | reconstruct_event_history, reconcile_failed_workflow, verify_recovery, get_incident_timeline | ADMIN, SUPERUSER |

Every server also exposes `health_check` and `server_info` (identity,
permissions, audit context). The canonical catalog lives in
`src/services/mcp_rbac.py` (`SERVER_CATALOG`); the registry table
`mcp_servers` is seeded from it on every boot (idempotent).

---

## 3. Role-permission matrix

| Capability | PATIENT | DOCTOR | ADMIN | SUPERUSER |
|---|---|---|---|---|
| Own records / journey / care gaps / continuity (U1, U3, U5) | ✅ own only | ✅ enrolled patients | ❌ aggregates only | ✅ (audited) |
| Evidence-backed chatbot answers (U2) | ✅ own scope | ✅ authorized scope | ✅ (no patient rows) | ✅ |
| What-if simulator (U4, synthetic data only) | ✅ | ✅ | ✅ | ✅ |
| Clinical conflict review (A1) | ❌ | ✅ review + approve changes | ✅ oversee | ✅ |
| Aggregate hospital analytics (A2) | ❌ | ❌ | ✅ | ✅ |
| Change impact + approvals (A3) | ❌ | ❌ | ✅ request | ✅ approve/execute |
| AI safety benchmarks (S1) | ❌ | ❌ | ❌ view | ✅ run |
| Flight recorder + recovery (S2) | ❌ | ❌ | ✅ review incidents | ✅ execute recovery |
| MCP registry / audit / access reports | ❌ | ❌ | ✅ | ✅ |
| Manage roles + permissions | ❌ | ❌ | ❌ | ✅ |

Hard rules enforced server-side on **every** request and **every** tool call:

- The principal comes from the server-side session — never from a
  `user_id` / `role` / `patient_id` in the URL or payload.
- Patients can never read another patient's records (IDOR-proof, enforced
  in the database query layer too).
- Admins get aggregates, not patient-level records.
- Superuser actions are still authenticated, authorized and audited; there
  is no undocumented bypass and no arbitrary SQL through any tool.
- Deny by default; least privilege; service identities never inherit
  superuser permissions.

---

## 4. Database — 16 new tables (additive migration)

`migrations/mcp_platform.sql` — **paste-safe, re-runnable, zero DROP**:
every table is `CREATE TABLE IF NOT EXISTS`, every seed row is
`INSERT IGNORE`. Run it in MySQL Workbench **after**
`workbench_all_features.sql` (it only adds tables; nothing existing is
touched). On SQLite the app creates the same tables automatically via
`Base.metadata.create_all()` on boot.

| Table | Purpose |
|---|---|
| mcp_servers | Registry: the 10 servers, health, tools, roles |
| audit_events | DB mirror of the JSONL audit streams |
| security_events | Auth failures, denials, rate limits, privileged ops |
| ai_requests | One evidence-grounded chatbot answer (or refusal) |
| ai_evidence | Evidence records retrieved for an answer |
| ai_claims | Checkable claims tied to evidence |
| care_gaps | Detected missing workflow steps (alerts, not diagnoses) |
| care_review_tasks | Review tasks created from care gaps |
| clinical_conflicts | Detected conflicts/safety concerns |
| scenario_runs | What-if simulations (always synthetic) |
| change_requests | Proposed changes with impact preview + rollback plan |
| change_approvals | Approval decisions (separation of duties) |
| workflow_events | Flight-recorder events with correlation + idempotency keys |
| recovery_attempts | Safe recovery attempts + outcomes |
| ai_benchmark_runs | AI safety benchmark runs |
| ai_benchmark_results | Per-test results + measured metrics |

---

## 5. Logging — 9 separate, persistent streams

Structured **JSON Lines** in `logs/` (override with `MCP_LOG_DIR`), each
with rotation (5 MB × 5 backups) and UTC timestamps:

| Stream | What it records |
|---|---|
| application.log | App startup/shutdown, MCP server starts, route errors |
| mcp_gateway_audit.log | Every gateway call: principal, server, tool, outcome, duration |
| mcp_tool_events.log | Every tool execution: start/end, duration, validation, error category |
| security_events.log | Auth failures, denials, rate limits, privileged operations |
| ai_evidence_audit.log | AI request ID, evidence refs, grounding result, refusal reason |
| clinical_review.log | Conflict cases, assignments, authorized resolutions |
| workflow_recovery.log | Failed workflows, retry decisions, idempotency, results |
| change_approval.log | Proposed changes, approver, decision, before/after, rollback |
| ai_benchmark.log | Suite version, test IDs, measured metrics, regressions |

Mandatory fields on every record: UTC timestamp, unique event ID,
correlation ID, request ID, actor/service identity, role, MCP server, tool,
action category, safe resource reference, result, error category, duration,
policy version. **Passwords, tokens, secrets and full patient records are
redacted before anything is written.** Security-audit writes fail closed.

---

## 6. Security

- **Authentication** on every protected endpoint; secure session cookies
  (`SESSION_SECRET` in `.env`); passwords hashed (argon2 via pwdlib).
- **Authorization**: central RBAC (`src/security/rbac.py` +
  `src/services/mcp_rbac.py`), enforced at the gateway **and** re-checked
  inside every MCP server (defense in depth). MCP tools enforce permissions
  even when called outside the UI.
- **Service-to-service auth**: every MCP server requires the shared
  `X-MCP-Service-Token` (`MCP_SERVICE_TOKEN` in `.env`); servers bind
  `127.0.0.1` only — browsers can never reach them directly.
- **Rate limiting**: login 10 attempts / 5 min per IP+email; gateway
  120 calls / min per user (in-memory store; swap for Redis in multi-process
  deployments). Limited events are recorded to security_events.
- **Input validation** on every tool (typed schemas via FastMCP);
  controlled errors only — never stack traces, never fake data.
- **Audit**: every tool call, denial and privileged action is logged and
  mirrored to the database.

---

## 7. Hallucination control (evidence validation)

Before any **DB-backed** chatbot answer is returned, a deterministic gate
(`src/services/evidence_service.py`) extracts the reply's factual claims
(medicine prices, disease-medicine links, doctor fees, clinic timings) and
validates them against the clinic's records:

| Status | Meaning |
|---|---|
| VERIFIED | Every claim is supported by a real record → answer passes unchanged |
| INCOMPLETE | Some claims could not be verified → controlled refusal |
| CONFLICTED | Records contradict each other → controlled refusal + conflict flagged |
| NOT_FOUND | Verified absence → "Verified information is not available in the current records." |
| SOURCE_UNAVAILABLE | The database could not be checked (never treated as NOT_FOUND) |
| ACCESS_DENIED | The principal is outside the record's scope |

The language model never creates database facts; it can only restate what
the resolvers verified. Emergency symptoms always trigger urgent-care
guidance. We report **measured** benchmark performance — hallucinations are
reduced, not claimed to be eliminated.

---

## 8. Safe recovery (flight recorder)

Payments and appointment bookings record **workflow events** with a
correlation ID and an idempotency key. Example: a payment succeeds at the
provider but the appointment stays pending — `reconcile_failed_workflow`
retrieves the correlated events, **verifies the recorded payment status
with the trusted source**, retries the update **idempotently** (replays
never duplicate), records the outcome, and escalates unresolved cases for
authorized review. A success is never inferred from a browser redirect or
an unverified client request.

---

## 9. The `/mcp` console (newpage.html)

One page, ten sections, role-based visibility (the server still enforces
every endpoint independently):

1. **Overview** — users by role, MCP online/offline, security events, pending tasks
2. **MCP Server Registry** — all 10 servers, tools, health, permissions, errors
3. **AI Safety Center** — benchmark metrics, grounding/refusal accuracy, run button
4. **Patient Journey Intelligence** — timeline, missing steps, downloadable verified summary
5. **What-If Simulator** — synthetic scenarios, assumptions, outcomes (clearly marked synthetic)
6. **Clinical Safety Review** — conflicts, severity, reviewer, resolution history
7. **Access Control** — role-permission matrix, overrides, denied attempts
8. **Audit Explorer** — filters: time, user, role, server, tool, action, result, correlation ID
9. **Change Impact & Approval** — preview (never executes), requests, rollback feasibility
10. **Flight Recorder & Recovery** — incident timelines, idempotent reconcile, verification

---

## 10. How to run

```bash
# 1. install (adds fastmcp to the existing requirements)
pip install -r requirements.txt

# 2. configure (copy and edit)
cp .env.example .env        # set DB_* for MySQL, MCP_SERVICE_TOKEN, SESSION_SECRET

# 3. database (MySQL users: run the additive migration in Workbench)
#    mysql -u sanjeevani_app -p sanjeevani_clinic < migrations/mcp_platform.sql
#    (SQLite users: nothing to do - tables are created on boot)

# 4. start the 10 MCP servers (localhost only, service-token protected)
python -m src.mcp.run_all
#    Windows shortcut:  start_mcp.bat

# 5. start the app (in another terminal)
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 6. open the console
#    http://localhost:8000/mcp   (login first: patient@demo.com / Demo@1234)
```

The servers must be running for the console's live sections; the app boots
fine without them (sections report controlled `SOURCE_UNAVAILABLE`).

---

## 11. Verify (run and check)

```bash
# Full platform verification: 62 checks, all 6 acceptance areas
# (servers start in-process - no external processes needed)
python test_mcp_platform.py
#   -> PASSED: 62, FAILED: 0, plus an honest skipped/unverified report

# Existing features regression: 233 checks
python test_pharmacy.py

# On your real MySQL database: 58 checks
python test_pharmacy_mysql.py
```

---

## 12. Honest limitations

- **Rate limiting** is in-memory (per process) — use Redis for multi-process
  deployments (interface unchanged).
- **Payment provider verification** uses the simulated provider in tests;
  configure the real provider per deployment.
- **Evidence grounding** uses the clinic's own records in this deployment;
  external approved medical sources can be added as resolvers.
- **Load testing** is synthetic smoke only (no load rig in CI).
- **MCP servers are local** (127.0.0.1) by design; production deployments
  should front them with TLS + network policy.
- **Hallucinations are reduced, not eliminated** — the AI Safety Center
  reports measured metrics; it never claims perfection.
