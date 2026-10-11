-- ============================================================================
--  SANJEEVANI CLINIC - UPGRADE AN EXISTING DATABASE TO THE NEW FEATURES
-- ============================================================================
--
--  Use this ONLY if you already pasted an earlier pharmacy/SQL file and just
--  want the two tables that the newest features need:
--
--      doctor_patient_notes   -> Doctor Desk ("notes" tab, /doctor-desk)
--      role_permissions       -> SUPERUSER role matrix (/pharmacy/admin -> Access)
--
--  plus one column the older database_setup.sql was missing on treatment_reviews.
--
--  NOTHING IS DELETED. No DROP, no TRUNCATE, no UPDATE. Every statement is
--  CREATE TABLE IF NOT EXISTS or a guarded ALTER, so:
--      * if your database is already up to date -> every line is a no-op
--      * if a table is missing                  -> it gets created
--      * your medical_records / follow_ups / appointments rows are untouched
--
--  HOW TO USE
--  ----------
--    1. MySQL Workbench -> File -> Open SQL Script -> this file
--    2. Ctrl+Shift+Enter ("Execute all statements")
--    3. The last grid tells you what is present now - all lines should read
--       "present" / the expected number.
--
--  (You can also just re-paste database_setup_with_pharmacy.sql or
--   workbench_pharmacy.sql - both are re-runnable too. This file is simply the
--   smallest thing that closes the gap.)
-- ============================================================================

CREATE DATABASE IF NOT EXISTS sanjeevani_clinic
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE sanjeevani_clinic;

-- Preflight: is this really the clinic database? (read-only)
SELECT IF((SELECT COUNT(*) FROM information_schema.tables
            WHERE table_schema = 'sanjeevani_clinic'
              AND table_name IN ('users', 'appointments')) = 2,
          'OK - clinic tables found, only the new feature tables will be added',
          'STOP - this database has no users/appointments table. Run database_setup_with_pharmacy.sql instead.') AS preflight_check;

-- ---------------------------------------------------------------------------
-- 1. treatment_reviews.updated_at  (the old database_setup.sql forgot it; the
--    app writes this column, so without it reviews fail with
--    "Unknown column 'treatment_reviews.updated_at' in 'field list'")
--    MySQL has no "ADD COLUMN IF NOT EXISTS", so it is guarded like this:
-- ---------------------------------------------------------------------------
SET @sql := IF((SELECT COUNT(*) FROM information_schema.columns
                 WHERE table_schema = 'sanjeevani_clinic'
                   AND table_name = 'treatment_reviews'
                   AND column_name = 'updated_at') = 0,
               'ALTER TABLE treatment_reviews ADD COLUMN updated_at DATETIME NULL',
               'SELECT ''treatment_reviews.updated_at already present - nothing to do'' AS step_1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ---------------------------------------------------------------------------
-- 2. the two tables that belong to the newest features
--    (created with foreign-key checks off so the file also works if you are
--     still missing the clinic tables - the relations are still declared)
-- ---------------------------------------------------------------------------
SET FOREIGN_KEY_CHECKS = 0;

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

SET FOREIGN_KEY_CHECKS = 1;

-- ---------------------------------------------------------------------------
-- 3. the SUPERUSER login (INSERT IGNORE - skipped when the email already
--    exists, so your existing logins and passwords are never touched)
--    Password: Super@1234   ->   everything + the Access (role matrix) tab
-- ---------------------------------------------------------------------------
SELECT IF((SELECT COUNT(*) FROM information_schema.tables
            WHERE table_schema = 'sanjeevani_clinic' AND table_name = 'users') = 1,
          'users table found - the SUPERUSER row below is added if missing',
          'no users table - run database_setup_with_pharmacy.sql first') AS step_3;

INSERT IGNORE INTO `users` (`name`, `email`, `phone`, `password_hash`, `age`, `gender`, `role`, `is_active`, `created_at`, `updated_at`) VALUES ('Super User', 'superuser@sanjeevani.com', '9876500100', '$argon2id$v=19$m=65536,t=3,p=4$4IriaKYXbcVbTQOGkhkE0g$06Mte6kmw9NoW+nYKHYwKh4pjcRNac79GYueAFtaelY', 41, 'Male', 'SUPERUSER', TRUE, '2026-10-08 08:45:55', '2026-10-08 08:45:55');

-- ---------------------------------------------------------------------------
-- 4. VERIFY - every line should say "present" / the expected number
-- ---------------------------------------------------------------------------
SELECT 'doctor_patient_notes table' AS what,
       IF(COUNT(*) = 1, 'present', 'MISSING - re-run this file') AS status
  FROM information_schema.tables
 WHERE table_schema = 'sanjeevani_clinic' AND table_name = 'doctor_patient_notes'
UNION ALL
SELECT 'role_permissions table',
       IF(COUNT(*) = 1, 'present', 'MISSING - re-run this file')
  FROM information_schema.tables
 WHERE table_schema = 'sanjeevani_clinic' AND table_name = 'role_permissions'
UNION ALL
SELECT 'treatment_reviews.updated_at',
       IF(COUNT(*) = 1, 'present', 'MISSING - re-run this file')
  FROM information_schema.columns
 WHERE table_schema = 'sanjeevani_clinic' AND table_name = 'treatment_reviews'
   AND column_name = 'updated_at'
UNION ALL
SELECT 'module tables found', CONCAT(COUNT(*), ' (expect 12)')
  FROM information_schema.tables
 WHERE table_schema = 'sanjeevani_clinic'
   AND table_name IN ('diseases','medicines','medicine_diseases','pharmacy_cart_items',
                      'nearby_pharmacies','nearby_pharmacy_stocks','pharmacy_snapshots',
                      'pharmacy_orders','pharmacy_order_items','pharmacy_audit_logs',
                      'role_permissions','doctor_patient_notes')
UNION ALL
SELECT 'logins by role',
       CONCAT('PATIENT ', (SELECT COUNT(*) FROM users WHERE role = 'PATIENT'),
              ' | DOCTOR ', (SELECT COUNT(*) FROM users WHERE role = 'DOCTOR'),
              ' | PHARMACIST ', (SELECT COUNT(*) FROM users WHERE role = 'PHARMACIST'),
              ' | ADMIN ', (SELECT COUNT(*) FROM users WHERE role = 'ADMIN'),
              ' | SUPERUSER ', (SELECT COUNT(*) FROM users WHERE role = 'SUPERUSER'));

-- What your own data looks like right now (read-only sanity check):
SELECT (SELECT COUNT(*) FROM medical_records) AS medical_records,
       (SELECT COUNT(*) FROM follow_ups)       AS follow_ups,
       (SELECT COUNT(*) FROM appointments)     AS appointments;

-- ============================================================================
--  Done. Now restart the app (uvicorn) and open:
--      http://127.0.0.1:8000/doctor-desk      (login doctor@demo.com)
--      http://127.0.0.1:8000/pharmacy/admin   (login superuser@sanjeevani.com)
-- ============================================================================
