-- ============================================================================
--  SANJEEVANI CLINIC - MCP INTELLIGENCE PLATFORM MIGRATION
--  (MySQL / MySQL Workbench)                                  16 NEW TABLES
-- ============================================================================
--
--  Adds the research-grade MCP platform tables to the EXISTING database:
--  MCP server registry, audit + security events, AI evidence records,
--  care gaps + review tasks, clinical conflicts, scenario runs, change
--  requests + approvals, workflow events + recovery attempts, and AI
--  benchmark runs + results.
--
--  WHAT IS SAFE ABOUT THIS FILE
--  ----------------------------
--   * NO DROP DATABASE and NO DROP TABLE anywhere. Your existing tables
--     and data are never touched or deleted.
--   * every table is CREATE TABLE IF NOT EXISTS and every seed row is
--     INSERT IGNORE, so pasting it twice is harmless (re-runnable).
--   * run it AFTER workbench_all_features.sql (it only ADDS tables).
--
--  HOW TO RUN
--  ----------
--    MySQL Workbench : open this file, run it against sanjeevani_clinic.
--    Command line    : mysql -u sanjeevani_app -p sanjeevani_clinic < migrations/mcp_platform.sql
-- ============================================================================

-- ------------------------------------------------------- mcp_servers -------
CREATE TABLE IF NOT EXISTS mcp_servers (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    name             VARCHAR(60)  NOT NULL,
    group_code       VARCHAR(4)   NOT NULL,
    category         VARCHAR(10)  NOT NULL,
    description      TEXT         NULL,
    base_url         VARCHAR(120) NOT NULL,
    service_identity VARCHAR(60)  NOT NULL,
    tools            JSON         NULL,
    required_roles   JSON         NULL,
    status           VARCHAR(12)  NOT NULL DEFAULT 'OFFLINE',
    last_health_at   DATETIME     NULL,
    last_error       TEXT         NULL,
    is_active        BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                  ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_mcp_servers_name (name),
    UNIQUE KEY uq_mcp_servers_identity (service_identity),
    KEY idx_mcp_servers_category (category)
) ENGINE=InnoDB;

-- ------------------------------------------------------- audit_events ------
CREATE TABLE IF NOT EXISTS audit_events (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    event_id        VARCHAR(64)  NOT NULL,
    correlation_id  VARCHAR(64)  NULL,
    request_id      VARCHAR(64)  NULL,
    actor           VARCHAR(150) NULL,
    role            VARCHAR(20)  NULL,
    mcp_server      VARCHAR(60)  NULL,
    tool            VARCHAR(80)  NULL,
    action          VARCHAR(80)  NULL,
    resource_type   VARCHAR(60)  NULL,
    resource_ref    VARCHAR(120) NULL,
    result          VARCHAR(20)  NOT NULL DEFAULT 'success',
    error_category  VARCHAR(60)  NULL,
    duration_ms     DOUBLE       NULL,
    policy_version  VARCHAR(20)  NULL,
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_audit_events_event (event_id),
    KEY idx_audit_events_correlation (correlation_id),
    KEY idx_audit_events_actor (actor),
    KEY idx_audit_events_created (created_at)
) ENGINE=InnoDB;

-- ------------------------------------------------------- security_events ---
CREATE TABLE IF NOT EXISTS security_events (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    event_id        VARCHAR(64)  NOT NULL,
    correlation_id  VARCHAR(64)  NULL,
    actor           VARCHAR(150) NULL,
    role            VARCHAR(20)  NULL,
    action          VARCHAR(80)  NOT NULL,
    resource_type   VARCHAR(60)  NULL,
    resource_ref    VARCHAR(120) NULL,
    result          VARCHAR(20)  NOT NULL DEFAULT 'denied',
    ip_address      VARCHAR(45)  NULL,
    user_agent      VARCHAR(255) NULL,
    details         JSON         NULL,
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_security_events_event (event_id),
    KEY idx_security_events_correlation (correlation_id),
    KEY idx_security_events_action (action),
    KEY idx_security_events_created (created_at)
) ENGINE=InnoDB;

-- ------------------------------------------------------- ai_requests -------
CREATE TABLE IF NOT EXISTS ai_requests (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    request_id      VARCHAR(64)  NOT NULL,
    correlation_id  VARCHAR(64)  NULL,
    actor           VARCHAR(150) NULL,
    role            VARCHAR(20)  NULL,
    question        TEXT         NOT NULL,
    answer          TEXT         NULL,
    status          VARCHAR(24)  NOT NULL,
    refusal_reason  TEXT         NULL,
    model_version   VARCHAR(60)  NULL,
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_ai_requests_request (request_id),
    KEY idx_ai_requests_correlation (correlation_id),
    KEY idx_ai_requests_status (status),
    KEY idx_ai_requests_created (created_at)
) ENGINE=InnoDB;

-- ------------------------------------------------------- ai_evidence -------
CREATE TABLE IF NOT EXISTS ai_evidence (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    ai_request_id   INT          NULL,
    source_type     VARCHAR(20)  NOT NULL,
    source_ref      VARCHAR(160) NOT NULL,
    source_version  VARCHAR(60)  NULL,
    snippet         TEXT         NULL,
    supports_claim  BOOLEAN      NULL,
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_ai_evidence_request (ai_request_id),
    CONSTRAINT fk_ai_evidence_request
        FOREIGN KEY (ai_request_id) REFERENCES ai_requests (id)
        ON DELETE CASCADE
) ENGINE=InnoDB;

-- ------------------------------------------------------- ai_claims ---------
CREATE TABLE IF NOT EXISTS ai_claims (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    ai_request_id   INT          NULL,
    claim_text      TEXT         NOT NULL,
    claim_kind      VARCHAR(40)  NULL,
    status          VARCHAR(24)  NOT NULL,
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_ai_claims_request (ai_request_id),
    KEY idx_ai_claims_kind (claim_kind),
    CONSTRAINT fk_ai_claims_request
        FOREIGN KEY (ai_request_id) REFERENCES ai_requests (id)
        ON DELETE CASCADE
) ENGINE=InnoDB;

-- ------------------------------------------------------- care_gaps ---------
CREATE TABLE IF NOT EXISTS care_gaps (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    patient_id      INT          NOT NULL,
    gap_type        VARCHAR(40)  NOT NULL,
    description     TEXT         NULL,
    severity        VARCHAR(12)  NOT NULL DEFAULT 'MEDIUM',
    status          VARCHAR(16)  NOT NULL DEFAULT 'OPEN',
    detected_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at     DATETIME     NULL,
    resolved_by     VARCHAR(150) NULL,
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_care_gaps_patient (patient_id),
    KEY idx_care_gaps_status (status),
    CONSTRAINT fk_care_gaps_patient
        FOREIGN KEY (patient_id) REFERENCES users (id)
        ON DELETE CASCADE
) ENGINE=InnoDB;

-- ------------------------------------------------- care_review_tasks -------
CREATE TABLE IF NOT EXISTS care_review_tasks (
    id                    INT AUTO_INCREMENT PRIMARY KEY,
    care_gap_id           INT          NOT NULL,
    assigned_to_user_id   INT          NULL,
    assigned_to_name      VARCHAR(120) NULL,
    status                VARCHAR(16)  NOT NULL DEFAULT 'PENDING',
    notes                 TEXT         NULL,
    created_at            DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at          DATETIME     NULL,
    KEY idx_care_review_tasks_gap (care_gap_id),
    KEY idx_care_review_tasks_status (status),
    CONSTRAINT fk_care_review_tasks_gap
        FOREIGN KEY (care_gap_id) REFERENCES care_gaps (id)
        ON DELETE CASCADE,
    CONSTRAINT fk_care_review_tasks_user
        FOREIGN KEY (assigned_to_user_id) REFERENCES users (id)
        ON DELETE SET NULL
) ENGINE=InnoDB;

-- ------------------------------------------------- clinical_conflicts ------
CREATE TABLE IF NOT EXISTS clinical_conflicts (
    id                    INT AUTO_INCREMENT PRIMARY KEY,
    conflict_type         VARCHAR(40)  NOT NULL,
    patient_id            INT          NULL,
    description           TEXT         NULL,
    severity              VARCHAR(12)  NOT NULL DEFAULT 'MEDIUM',
    status                VARCHAR(16)  NOT NULL DEFAULT 'OPEN',
    assigned_to_user_id   INT          NULL,
    detected_at           DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at           DATETIME     NULL,
    resolved_by           VARCHAR(150) NULL,
    resolution_notes      TEXT         NULL,
    created_at            DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_clinical_conflicts_type (conflict_type),
    KEY idx_clinical_conflicts_patient (patient_id),
    KEY idx_clinical_conflicts_status (status),
    CONSTRAINT fk_clinical_conflicts_patient
        FOREIGN KEY (patient_id) REFERENCES users (id)
        ON DELETE SET NULL,
    CONSTRAINT fk_clinical_conflicts_user
        FOREIGN KEY (assigned_to_user_id) REFERENCES users (id)
        ON DELETE SET NULL
) ENGINE=InnoDB;

-- ------------------------------------------------------- scenario_runs -----
CREATE TABLE IF NOT EXISTS scenario_runs (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    scenario_type   VARCHAR(60)  NOT NULL,
    assumptions     JSON         NULL,
    inputs          JSON         NULL,
    outputs         JSON         NULL,
    affected_counts JSON         NULL,
    status          VARCHAR(16)  NOT NULL DEFAULT 'COMPLETED',
    is_synthetic    BOOLEAN      NOT NULL DEFAULT TRUE,
    created_by      VARCHAR(150) NULL,
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_scenario_runs_type (scenario_type),
    KEY idx_scenario_runs_created (created_at)
) ENGINE=InnoDB;

-- ---------------------------------------------------- change_requests ------
CREATE TABLE IF NOT EXISTS change_requests (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    change_type     VARCHAR(60)  NOT NULL,
    description     TEXT         NULL,
    proposed_by     VARCHAR(150) NULL,
    status          VARCHAR(16)  NOT NULL DEFAULT 'PENDING',
    impact_preview  JSON         NULL,
    before_data     JSON         NULL,
    after_data      JSON         NULL,
    rollback_plan   TEXT         NULL,
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    decided_at      DATETIME     NULL,
    decided_by      VARCHAR(150) NULL,
    KEY idx_change_requests_type (change_type),
    KEY idx_change_requests_status (status),
    KEY idx_change_requests_proposed (proposed_by)
) ENGINE=InnoDB;

-- ---------------------------------------------------- change_approvals -----
CREATE TABLE IF NOT EXISTS change_approvals (
    id                 INT AUTO_INCREMENT PRIMARY KEY,
    change_request_id  INT          NOT NULL,
    approver           VARCHAR(150) NOT NULL,
    decision           VARCHAR(16)  NOT NULL,
    notes              TEXT         NULL,
    decided_at         DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_change_approvals_request (change_request_id),
    CONSTRAINT fk_change_approvals_request
        FOREIGN KEY (change_request_id) REFERENCES change_requests (id)
        ON DELETE CASCADE
) ENGINE=InnoDB;

-- ---------------------------------------------------- workflow_events ------
CREATE TABLE IF NOT EXISTS workflow_events (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    correlation_id   VARCHAR(64)  NOT NULL,
    workflow_type    VARCHAR(40)  NOT NULL,
    resource_type    VARCHAR(60)  NULL,
    resource_ref     VARCHAR(120) NULL,
    event_type       VARCHAR(40)  NOT NULL,
    payload          JSON         NULL,
    idempotency_key  VARCHAR(80)  NULL,
    created_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_workflow_events_correlation (correlation_id),
    KEY idx_workflow_events_type (workflow_type),
    KEY idx_workflow_events_resource (resource_ref),
    KEY idx_workflow_events_idempotency (idempotency_key),
    KEY idx_workflow_events_created (created_at)
) ENGINE=InnoDB;

-- -------------------------------------------------- recovery_attempts ------
CREATE TABLE IF NOT EXISTS recovery_attempts (
    id                 INT AUTO_INCREMENT PRIMARY KEY,
    workflow_event_id  INT          NULL,
    correlation_id     VARCHAR(64)  NULL,
    incident_type      VARCHAR(60)  NOT NULL,
    status             VARCHAR(16)  NOT NULL DEFAULT 'PENDING',
    idempotency_key    VARCHAR(80)  NULL,
    attempts           INT          NOT NULL DEFAULT 0,
    result             JSON         NULL,
    created_at         DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at       DATETIME     NULL,
    KEY idx_recovery_attempts_event (workflow_event_id),
    KEY idx_recovery_attempts_correlation (correlation_id),
    KEY idx_recovery_attempts_status (status),
    CONSTRAINT fk_recovery_attempts_event
        FOREIGN KEY (workflow_event_id) REFERENCES workflow_events (id)
        ON DELETE SET NULL
) ENGINE=InnoDB;

-- ------------------------------------------------- ai_benchmark_runs -------
CREATE TABLE IF NOT EXISTS ai_benchmark_runs (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    suite_version   VARCHAR(40)  NOT NULL,
    model_version   VARCHAR(60)  NULL,
    started_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at     DATETIME     NULL,
    total_tests     INT          NOT NULL DEFAULT 0,
    passed          INT          NOT NULL DEFAULT 0,
    failed          INT          NOT NULL DEFAULT 0,
    metrics         JSON         NULL,
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_ai_benchmark_runs_suite (suite_version),
    KEY idx_ai_benchmark_runs_created (created_at)
) ENGINE=InnoDB;

-- ------------------------------------------------ ai_benchmark_results -----
CREATE TABLE IF NOT EXISTS ai_benchmark_results (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    run_id          INT          NOT NULL,
    test_id         VARCHAR(80)  NOT NULL,
    category        VARCHAR(40)  NOT NULL,
    passed          BOOLEAN      NOT NULL DEFAULT FALSE,
    metric_name     VARCHAR(60)  NULL,
    metric_value    DOUBLE       NULL,
    details         JSON         NULL,
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_ai_benchmark_results_run (run_id),
    KEY idx_ai_benchmark_results_test (test_id),
    KEY idx_ai_benchmark_results_category (category),
    CONSTRAINT fk_ai_benchmark_results_run
        FOREIGN KEY (run_id) REFERENCES ai_benchmark_runs (id)
        ON DELETE CASCADE
) ENGINE=InnoDB;

-- ============================================================================
--  SEED: the 10 logical MCP servers (INSERT IGNORE = re-runnable)
-- ============================================================================
INSERT IGNORE INTO mcp_servers
    (name, group_code, category, description, base_url, service_identity,
     tools, required_roles, status, is_active)
VALUES
    ('care-gap-intelligence', 'U1', 'USER',
     'Detect missing steps in a patient''s recorded healthcare journey.',
     'http://127.0.0.1:9101/mcp', 'svc-u1-care-gap',
     '["detect_care_gaps","trace_missing_steps","get_care_timeline","create_care_review_task"]',
     '["PATIENT","DOCTOR"]', 'OFFLINE', TRUE),
    ('evidence-ai', 'U2', 'USER',
     'Evidence-grounded answers for the healthcare chatbot.',
     'http://127.0.0.1:9102/mcp', 'svc-u2-evidence-ai',
     '["retrieve_evidence","verify_claims","explain_answer_sources","check_information_availability"]',
     '["PATIENT","DOCTOR","ADMIN","SUPERUSER"]', 'OFFLINE', TRUE),
    ('health-timeline', 'U3', 'USER',
     'Complete chronological patient journey from verified records.',
     'http://127.0.0.1:9103/mcp', 'svc-u3-timeline',
     '["build_health_timeline","compare_visits","detect_stale_records","generate_verified_patient_summary"]',
     '["PATIENT","DOCTOR"]', 'OFFLINE', TRUE),
    ('workflow-simulator', 'U4', 'USER',
     'What-if simulation on synthetic data - never touches live records.',
     'http://127.0.0.1:9104/mcp', 'svc-u4-simulator',
     '["simulate_scenario","compare_outcomes","explain_assumptions","validate_scenario_inputs"]',
     '["PATIENT","DOCTOR","ADMIN","SUPERUSER"]', 'OFFLINE', TRUE),
    ('care-continuity', 'U5', 'USER',
     'Recorded next steps and pending follow-up status for patients.',
     'http://127.0.0.1:9105/mcp', 'svc-u5-continuity',
     '["get_pending_care_steps","check_followup_status","prepare_patient_summary","request_missing_information"]',
     '["PATIENT","DOCTOR"]', 'OFFLINE', TRUE),
    ('clinical-safety', 'A1', 'ADMIN',
     'Detect conflicts and safety concerns in recorded clinical info.',
     'http://127.0.0.1:9201/mcp', 'svc-a1-clinical-safety',
     '["detect_record_conflicts","flag_safety_concerns","request_clinical_review","get_conflict_resolution_history"]',
     '["DOCTOR","ADMIN","SUPERUSER"]', 'OFFLINE', TRUE),
    ('hospital-intelligence', 'A2', 'ADMIN',
     'Privacy-preserving aggregate hospital operations analytics.',
     'http://127.0.0.1:9202/mcp', 'svc-a2-hospital-intel',
     '["analyze_workflow_patterns","measure_care_gaps","compare_periods","generate_aggregate_report"]',
     '["ADMIN","SUPERUSER"]', 'OFFLINE', TRUE),
    ('change-approval', 'A3', 'ADMIN',
     'Preview and control important system changes with approvals.',
     'http://127.0.0.1:9203/mcp', 'svc-a3-change-approval',
     '["preview_change_impact","request_approval","verify_rollback_plan","get_change_history"]',
     '["ADMIN","SUPERUSER"]', 'OFFLINE', TRUE),
    ('ai-reliability', 'S1', 'SYSTEM',
     'Red-team and reliability benchmarks for the AI + MCP stack.',
     'http://127.0.0.1:9301/mcp', 'svc-s1-ai-reliability',
     '["run_safety_benchmarks","test_access_boundaries","evaluate_answer_grounding","compare_versions","generate_test_report"]',
     '["SUPERUSER"]', 'OFFLINE', TRUE),
    ('flight-recorder', 'S2', 'SYSTEM',
     'Reconstruct failed workflows and coordinate safe recovery.',
     'http://127.0.0.1:9302/mcp', 'svc-s2-flight-recorder',
     '["reconstruct_event_history","reconcile_failed_workflow","verify_recovery","get_incident_timeline"]',
     '["ADMIN","SUPERUSER"]', 'OFFLINE', TRUE);

-- ============================================================================
--  DONE - 16 new tables + 10 registry rows. Nothing existing was dropped.
-- ============================================================================
