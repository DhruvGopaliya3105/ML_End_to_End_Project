-- ============================================================================
--  SANJEEVANI CLINIC - PHARMACY MODULE SCHEMA (MySQL)
-- ============================================================================
--
--  GENERATED FILE - do not edit by hand.
--  Source of truth: src/models/*.py
--  Regenerate with:  python pharmacy_schema_export.py
--  Generated on:    2026-10-08 06:29 UTC
--
--  YOU USUALLY DO NOT NEED THIS FILE. main.py runs Base.metadata.create_all()
--  at startup, which creates every table below automatically (MySQL and
--  SQLite). Use this script when you prefer to review / apply the DDL in
--  MySQL Workbench yourself.
--
--  HOW TO RUN
--  ----------
--  1. Open MySQL Workbench, connect to your local server.
--  2. File -> Open SQL Script -> this file.
--  3. Run it. It is safe to run more than once: every statement is
--     CREATE TABLE IF NOT EXISTS, so existing pharmacy data is never touched.
--     (There is deliberately NO DROP DATABASE / DROP TABLE here, unlike
--     database_setup.sql, because this file may be run against a live pharmacy.)
--  4. Then load the catalog + demo data:
--         python seed_pharmacy.py
--
--  12 tables:
--    medicines, diseases, medicine_diseases      - the catalog the patient shops from
--    pharmacy_cart_items                          - cart, stored per user in SQL
--    pharmacy_orders, pharmacy_order_items        - purchases + frozen price snapshots
--    nearby_pharmacies, nearby_pharmacy_stocks    - partner chemists for the emergency search
--    pharmacy_snapshots                           - rollback / restore points (super user)
--    pharmacy_audit_logs                          - append-only trail (super user)
--    role_permissions                             - role -> permission overrides (RBAC)
--    doctor_patient_notes                         - the doctor desk: notes kept on a patient file
--
--  Foreign keys point at the existing `users`, `doctors`, `prescriptions`,
--  `prescription_medicines` and `medicines` tables, so run database_setup.sql
--  first if this is a brand new database.
-- ============================================================================


USE sanjeevani_clinic;

SET NAMES utf8mb4;


-- ---- diseases ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS `diseases` (
  id INTEGER NOT NULL AUTO_INCREMENT,
  name VARCHAR(120) NOT NULL,
  slug VARCHAR(120) NOT NULL,
  group_name VARCHAR(120),
  description TEXT,
  icon VARCHAR(16),
  is_active BOOL NOT NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY `ix_diseases_name` (`name`),
  UNIQUE KEY `ix_diseases_slug` (`slug`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---- medicines ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS `medicines` (
  id INTEGER NOT NULL AUTO_INCREMENT,
  sku VARCHAR(40) NOT NULL,
  name VARCHAR(200) NOT NULL,
  generic_name VARCHAR(200),
  brand VARCHAR(120),
  form VARCHAR(40) NOT NULL,
  strength VARCHAR(60),
  pack_size VARCHAR(120),
  price NUMERIC(10, 2) NOT NULL,
  mrp NUMERIC(10, 2),
  stock INTEGER NOT NULL,
  low_stock_alert INTEGER NOT NULL,
  requires_prescription BOOL NOT NULL,
  warning VARCHAR(255),
  image_path VARCHAR(255),
  image_url VARCHAR(500),
  description TEXT,
  dosage_info TEXT,
  side_effects TEXT,
  is_active BOOL NOT NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  PRIMARY KEY (id),
  INDEX `ix_medicines_generic_name` (`generic_name`),
  INDEX `ix_medicines_name` (`name`),
  UNIQUE KEY `ix_medicines_sku` (`sku`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---- medicine_diseases -------------------------------------------------
CREATE TABLE IF NOT EXISTS `medicine_diseases` (
  id INTEGER NOT NULL AUTO_INCREMENT,
  medicine_id INTEGER NOT NULL,
  disease_id INTEGER NOT NULL,
  is_primary BOOL NOT NULL,
  created_at DATETIME NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uq_medicine_disease UNIQUE (medicine_id, disease_id),
  FOREIGN KEY(medicine_id) REFERENCES medicines (id) ON DELETE CASCADE,
  FOREIGN KEY(disease_id) REFERENCES diseases (id) ON DELETE CASCADE,
  INDEX `ix_medicine_diseases_disease_id` (`disease_id`),
  INDEX `ix_medicine_diseases_medicine_id` (`medicine_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---- pharmacy_cart_items -----------------------------------------------
CREATE TABLE IF NOT EXISTS `pharmacy_cart_items` (
  id INTEGER NOT NULL AUTO_INCREMENT,
  user_id INTEGER NOT NULL,
  medicine_id INTEGER,
  quantity INTEGER NOT NULL,
  unit_price NUMERIC(10, 2) NOT NULL,
  source VARCHAR(20) NOT NULL,
  prescription_id INTEGER,
  prescription_medicine_id INTEGER,
  dosage VARCHAR(100),
  frequency VARCHAR(100),
  duration VARCHAR(100),
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uq_cart_user_medicine_source UNIQUE (user_id, medicine_id, source),
  FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
  FOREIGN KEY(medicine_id) REFERENCES medicines (id) ON DELETE CASCADE,
  FOREIGN KEY(prescription_id) REFERENCES prescriptions (id) ON DELETE SET NULL,
  FOREIGN KEY(prescription_medicine_id) REFERENCES prescription_medicines (id) ON DELETE SET NULL,
  INDEX `ix_pharmacy_cart_items_medicine_id` (`medicine_id`),
  INDEX `ix_pharmacy_cart_items_prescription_id` (`prescription_id`),
  INDEX `ix_pharmacy_cart_items_prescription_medicine_id` (`prescription_medicine_id`),
  INDEX `ix_pharmacy_cart_items_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---- nearby_pharmacies -------------------------------------------------
CREATE TABLE IF NOT EXISTS `nearby_pharmacies` (
  id INTEGER NOT NULL AUTO_INCREMENT,
  name VARCHAR(200) NOT NULL,
  address VARCHAR(500),
  area VARCHAR(120),
  city VARCHAR(120) NOT NULL,
  pincode VARCHAR(12),
  phone VARCHAR(30),
  whatsapp VARCHAR(30),
  latitude FLOAT,
  longitude FLOAT,
  distance_km FLOAT,
  open_24x7 BOOL NOT NULL,
  opening_hours VARCHAR(120),
  rating FLOAT,
  is_partner BOOL NOT NULL,
  google_place_id VARCHAR(120),
  sync_status VARCHAR(20) NOT NULL,
  last_synced_at DATETIME,
  notes VARCHAR(500),
  is_active BOOL NOT NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  PRIMARY KEY (id),
  UNIQUE (google_place_id),
  INDEX `ix_nearby_pharmacies_name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---- nearby_pharmacy_stocks --------------------------------------------
CREATE TABLE IF NOT EXISTS `nearby_pharmacy_stocks` (
  id INTEGER NOT NULL AUTO_INCREMENT,
  pharmacy_id INTEGER NOT NULL,
  medicine_id INTEGER,
  medicine_label VARCHAR(200),
  stock INTEGER NOT NULL,
  price NUMERIC(10, 2),
  trust VARCHAR(20) NOT NULL,
  updated_at DATETIME NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uq_nearby_pharmacy_medicine UNIQUE (pharmacy_id, medicine_id),
  FOREIGN KEY(pharmacy_id) REFERENCES nearby_pharmacies (id) ON DELETE CASCADE,
  FOREIGN KEY(medicine_id) REFERENCES medicines (id) ON DELETE CASCADE,
  INDEX `ix_nearby_pharmacy_stocks_medicine_id` (`medicine_id`),
  INDEX `ix_nearby_pharmacy_stocks_pharmacy_id` (`pharmacy_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---- pharmacy_snapshots ------------------------------------------------
CREATE TABLE IF NOT EXISTS `pharmacy_snapshots` (
  id INTEGER NOT NULL AUTO_INCREMENT,
  label VARCHAR(160) NOT NULL,
  description VARCHAR(500),
  scope VARCHAR(30) NOT NULL,
  payload_json LONGTEXT NOT NULL,
  row_counts_json TEXT,
  tables_json TEXT,
  row_count INTEGER NOT NULL,
  size_bytes INTEGER NOT NULL,
  checksum VARCHAR(64) NOT NULL,
  created_by_user_id INTEGER,
  created_by_name VARCHAR(120),
  created_by_role VARCHAR(20),
  `trigger` VARCHAR(20) NOT NULL,
  is_pinned BOOL NOT NULL,
  restore_count INTEGER NOT NULL,
  last_restored_at DATETIME,
  last_restored_by VARCHAR(120),
  created_at DATETIME NOT NULL,
  PRIMARY KEY (id),
  FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE SET NULL,
  INDEX `ix_pharmacy_snapshots_created_at` (`created_at`),
  INDEX `ix_pharmacy_snapshots_created_by_user_id` (`created_by_user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---- pharmacy_orders ---------------------------------------------------
CREATE TABLE IF NOT EXISTS `pharmacy_orders` (
  id INTEGER NOT NULL AUTO_INCREMENT,
  order_no VARCHAR(40) NOT NULL,
  user_id INTEGER NOT NULL,
  order_type VARCHAR(20) NOT NULL,
  prescription_id INTEGER,
  status VARCHAR(30) NOT NULL,
  payment_method VARCHAR(20) NOT NULL,
  payment_status VARCHAR(20) NOT NULL,
  subtotal NUMERIC(10, 2) NOT NULL,
  delivery_fee NUMERIC(10, 2) NOT NULL,
  total NUMERIC(10, 2) NOT NULL,
  delivery_type VARCHAR(20) NOT NULL,
  address VARCHAR(500),
  phone VARCHAR(20),
  notes TEXT,
  is_emergency BOOL NOT NULL,
  transaction_id VARCHAR(80),
  payment_reference VARCHAR(120),
  payment_provider VARCHAR(30) NOT NULL,
  stock_adjusted BOOL NOT NULL,
  confirmed_at DATETIME,
  cancelled_at DATETIME,
  cancel_reason VARCHAR(500),
  handed_over_at DATETIME,
  snapshot_id INTEGER,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  PRIMARY KEY (id),
  FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
  FOREIGN KEY(prescription_id) REFERENCES prescriptions (id) ON DELETE SET NULL,
  FOREIGN KEY(snapshot_id) REFERENCES pharmacy_snapshots (id) ON DELETE SET NULL,
  UNIQUE KEY `ix_pharmacy_orders_order_no` (`order_no`),
  INDEX `ix_pharmacy_orders_prescription_id` (`prescription_id`),
  INDEX `ix_pharmacy_orders_snapshot_id` (`snapshot_id`),
  INDEX `ix_pharmacy_orders_status` (`status`),
  INDEX `ix_pharmacy_orders_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---- pharmacy_order_items ----------------------------------------------
CREATE TABLE IF NOT EXISTS `pharmacy_order_items` (
  id INTEGER NOT NULL AUTO_INCREMENT,
  order_id INTEGER NOT NULL,
  medicine_id INTEGER,
  medicine_name VARCHAR(200) NOT NULL,
  generic_name VARCHAR(200),
  form VARCHAR(40),
  strength VARCHAR(60),
  pack_size VARCHAR(120),
  image_path VARCHAR(255),
  quantity INTEGER NOT NULL,
  unit_price NUMERIC(10, 2) NOT NULL,
  line_total NUMERIC(10, 2) NOT NULL,
  source VARCHAR(20) NOT NULL,
  prescription_medicine_id INTEGER,
  dosage VARCHAR(100),
  frequency VARCHAR(100),
  duration VARCHAR(100),
  created_at DATETIME NOT NULL,
  PRIMARY KEY (id),
  FOREIGN KEY(order_id) REFERENCES pharmacy_orders (id) ON DELETE CASCADE,
  FOREIGN KEY(medicine_id) REFERENCES medicines (id) ON DELETE SET NULL,
  FOREIGN KEY(prescription_medicine_id) REFERENCES prescription_medicines (id) ON DELETE SET NULL,
  INDEX `ix_pharmacy_order_items_medicine_id` (`medicine_id`),
  INDEX `ix_pharmacy_order_items_order_id` (`order_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---- pharmacy_audit_logs -----------------------------------------------
CREATE TABLE IF NOT EXISTS `pharmacy_audit_logs` (
  id INTEGER NOT NULL AUTO_INCREMENT,
  severity VARCHAR(10) NOT NULL,
  action VARCHAR(80) NOT NULL,
  entity_type VARCHAR(40),
  entity_id VARCHAR(40),
  description VARCHAR(500),
  actor_user_id INTEGER,
  actor_name VARCHAR(120),
  actor_role VARCHAR(20),
  before_json LONGTEXT,
  after_json LONGTEXT,
  rollback_available BOOL NOT NULL,
  snapshot_id INTEGER,
  ip_address VARCHAR(60),
  user_agent VARCHAR(300),
  request_path VARCHAR(300),
  created_at DATETIME NOT NULL,
  PRIMARY KEY (id),
  FOREIGN KEY(actor_user_id) REFERENCES users (id) ON DELETE SET NULL,
  FOREIGN KEY(snapshot_id) REFERENCES pharmacy_snapshots (id) ON DELETE SET NULL,
  INDEX `ix_pharmacy_audit_created` (`created_at`),
  INDEX `ix_pharmacy_audit_entity` (`entity_type`, `entity_id`),
  INDEX `ix_pharmacy_audit_logs_action` (`action`),
  INDEX `ix_pharmacy_audit_logs_actor_user_id` (`actor_user_id`),
  INDEX `ix_pharmacy_audit_logs_snapshot_id` (`snapshot_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---- role_permissions --------------------------------------------------
CREATE TABLE IF NOT EXISTS `role_permissions` (
  id INTEGER NOT NULL AUTO_INCREMENT,
  `role` VARCHAR(20) NOT NULL,
  permission VARCHAR(80) NOT NULL,
  is_allowed BOOL NOT NULL,
  note VARCHAR(255),
  updated_by_user_id INTEGER,
  updated_by_name VARCHAR(120),
  updated_at DATETIME NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uq_role_permission UNIQUE (`role`, permission),
  FOREIGN KEY(updated_by_user_id) REFERENCES users (id) ON DELETE SET NULL,
  INDEX `ix_role_permissions_role` (`role`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---- doctor_patient_notes ----------------------------------------------
CREATE TABLE IF NOT EXISTS `doctor_patient_notes` (
  id INTEGER NOT NULL AUTO_INCREMENT,
  doctor_id INTEGER,
  doctor_name VARCHAR(120),
  doctor_specialization VARCHAR(100),
  patient_id INTEGER NOT NULL,
  note_type VARCHAR(20) NOT NULL,
  title VARCHAR(160) NOT NULL,
  body TEXT,
  visibility VARCHAR(20) NOT NULL,
  is_pinned BOOL NOT NULL,
  is_urgent BOOL NOT NULL,
  follow_up_date DATE,
  status VARCHAR(20) NOT NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  PRIMARY KEY (id),
  FOREIGN KEY(doctor_id) REFERENCES users (id) ON DELETE SET NULL,
  FOREIGN KEY(patient_id) REFERENCES users (id) ON DELETE CASCADE,
  INDEX `ix_doctor_patient_notes_doctor_id` (`doctor_id`),
  INDEX `ix_doctor_patient_notes_note_type` (`note_type`),
  INDEX `ix_doctor_patient_notes_patient_id` (`patient_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================================
--  OPTIONAL: verify it worked
-- ============================================================================

SELECT
    (SELECT COUNT(*) FROM medicines)          AS medicines,
    (SELECT COUNT(*) FROM diseases)           AS diseases,
    (SELECT COUNT(*) FROM medicine_diseases)  AS links,
    (SELECT COUNT(*) FROM nearby_pharmacies)  AS nearby_shops,
    (SELECT COUNT(*) FROM pharmacy_orders)    AS orders,
    (SELECT COUNT(*) FROM pharmacy_snapshots) AS snapshots,
    (SELECT COUNT(*) FROM pharmacy_audit_logs) AS audit_rows;

-- If every count is 0, the tables were created but not filled yet:
--     python seed_pharmacy.py
-- ============================================================================
