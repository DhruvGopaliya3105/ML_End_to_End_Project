-- ============================================================================
--  SANJEEVANI CLINIC - COMPLETE MYSQL DATABASE SETUP
-- ============================================================================
--
--  HOW TO USE THIS FILE
--  --------------------
--  1. Open MySQL Workbench and connect to your local MySQL server.
--  2. File -> Open SQL Script... -> select this file (database_setup.sql).
--  3. Press the lightning-bolt button (or Ctrl+Shift+Enter) to run it.
--     If Workbench asks, choose "Execute all statements".
--  4. Wait for it to finish. The final result grid shows row counts so you
--     can confirm the data loaded.
--
--  This script is safe to run more than once. It rebuilds the database from
--  scratch each time (see the DROP DATABASE line just below). If you want to
--  keep existing data, put two dashes in front of the DROP line to comment
--  it out - the rest of the script then only fills in what is missing.
--
--  WHAT THIS SCRIPT CREATES
--  ------------------------
--    15 tables + indexes + foreign keys
--    20 doctors                       (8 specialisations)
--    140 doctor schedules             (20 doctors x 7 days, 10:00-14:00)
--     5 visit types
--     2 demo logins you can use right away
--
--  DEMO LOGINS (created at the end of this script)
--  -----------------------------------------------
--    Patient : patient@demo.com  /  Demo@1234
--    Admin   : admin@demo.com    /  Admin@1234
--
--  The passwords are stored as real Argon2 hashes (the same algorithm the
--  app uses), so these accounts work in the login page immediately.
--
--  NOTE ON COLUMNS
--  ---------------
--  The last 7 columns of the `appointments` table (transaction_id,
--  payment_gateway, paid_at, razorpay_order_id, razorpay_payment_id,
--  payment_provider, payment_failure_reason) came from a payment-gateway
--  experiment. NO Python code in this project reads or writes them yet, so
--  they are just unused placeholder columns. They are kept here so nothing
--  you already had is lost. Feel free to delete them if you prefer.
--
-- ============================================================================


-- ============================================================================
-- 1. DATABASE
-- ============================================================================

DROP DATABASE IF EXISTS sanjeevani_clinic;
CREATE DATABASE sanjeevani_clinic
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE sanjeevani_clinic;


-- ============================================================================
-- 2. TABLES
-- ============================================================================

-- ---------------------------------------------------------------- users -----
CREATE TABLE IF NOT EXISTS users (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,
    email           VARCHAR(150) NOT NULL,
    phone           VARCHAR(20)  NULL,
    password_hash   VARCHAR(255) NOT NULL,
    age             INT          NULL,
    gender          VARCHAR(20)  NULL,
    profile_photo   VARCHAR(255) NULL,
    role            VARCHAR(20)  NOT NULL DEFAULT 'PATIENT',
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                 ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_users_email (email)
) ENGINE=InnoDB;


-- -------------------------------------------------------------- doctors -----
CREATE TABLE IF NOT EXISTS doctors (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    name              VARCHAR(100) NOT NULL,
    email             VARCHAR(150) NOT NULL,
    phone             VARCHAR(20)  NULL,
    specialization    VARCHAR(100) NOT NULL,
    qualification     VARCHAR(200) NULL,
    experience_years  INT          NULL,
    languages         VARCHAR(200) NULL,
    consultation_fee  NUMERIC(10,2) NULL,
    profile_photo     VARCHAR(255) NULL,
    bio               TEXT         NULL,
    is_active         BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                   ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_doctors_email (email)
) ENGINE=InnoDB;


-- ------------------------------------------------------- doctor_slots -------
CREATE TABLE IF NOT EXISTS doctor_slots (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    doctor_id    INT  NOT NULL,
    slot_date    DATE NOT NULL,
    start_time   TIME NOT NULL,
    end_time     TIME NOT NULL,
    is_available BOOLEAN  NOT NULL DEFAULT TRUE,
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY ix_slots_doctor_date (doctor_id, slot_date),
    CONSTRAINT fk_slots_doctor
        FOREIGN KEY (doctor_id) REFERENCES doctors(id) ON DELETE CASCADE
) ENGINE=InnoDB;


-- ---------------------------------------------------- doctor_schedules -----
-- day_of_week convention used by the app: 0 = Monday ... 6 = Sunday
CREATE TABLE IF NOT EXISTS doctor_schedules (
    id                    INT AUTO_INCREMENT PRIMARY KEY,
    doctor_id             INT NOT NULL,
    day_of_week           INT NOT NULL,
    start_time            TIME NOT NULL,
    end_time              TIME NOT NULL,
    slot_interval_minutes INT  NOT NULL DEFAULT 5,
    is_available          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at            DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at            DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                                   ON UPDATE CURRENT_TIMESTAMP,
    KEY ix_sched_doctor_day (doctor_id, day_of_week),
    CONSTRAINT fk_schedules_doctor
        FOREIGN KEY (doctor_id) REFERENCES doctors(id) ON DELETE CASCADE
) ENGINE=InnoDB;


-- -------------------------------------------------------- visit_types ------
CREATE TABLE IF NOT EXISTS visit_types (
    id                       INT AUTO_INCREMENT PRIMARY KEY,
    name                     VARCHAR(100) NOT NULL,
    min_duration_minutes     INT NOT NULL,
    max_duration_minutes     INT NOT NULL,
    default_duration_minutes INT NOT NULL,
    is_active                BOOLEAN NOT NULL DEFAULT TRUE,
    created_at               DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_visit_types_name (name)
) ENGINE=InnoDB;


-- ------------------------------------------------------- appointments ------
CREATE TABLE IF NOT EXISTS appointments (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    patient_id        INT  NOT NULL,
    doctor_id         INT  NOT NULL,
    slot_id           INT  NULL,
    appointment_date  DATE NOT NULL,
    start_time        TIME NOT NULL,
    end_time          TIME NOT NULL,
    visit_type        VARCHAR(100) NULL,
    duration_minutes  INT          NULL,
    status            VARCHAR(40)  NOT NULL DEFAULT 'BOOKED',
    reason            TEXT         NULL,

    -- payment / refund bookkeeping
    payment_method    VARCHAR(30)  NOT NULL DEFAULT 'CASH',
    payment_status    VARCHAR(30)  NOT NULL DEFAULT 'PENDING',
    payment_amount    NUMERIC(10,2) NULL,
    refund_status     VARCHAR(30)  NOT NULL DEFAULT 'NOT_REQUIRED',
    refund_amount     NUMERIC(10,2) NULL,
    refund_method     VARCHAR(30)  NULL,
    refund_reason     TEXT         NULL,
    refund_at         DATETIME     NULL,

    -- cancellation bookkeeping
    doctor_cancel_reason TEXT     NULL,
    cancelled_by         VARCHAR(30) NULL,
    cancelled_at         DATETIME NULL,

    -- payment-gateway columns (currently unused by the code - see header note)
    transaction_id         VARCHAR(120) NULL,
    payment_gateway        VARCHAR(50)  NULL,
    paid_at                DATETIME     NULL,
    razorpay_order_id      VARCHAR(120) NULL,
    razorpay_payment_id    VARCHAR(120) NULL,
    payment_provider       VARCHAR(50)  NULL,
    payment_failure_reason TEXT         NULL,

    created_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                               ON UPDATE CURRENT_TIMESTAMP,

    KEY ix_appt_patient  (patient_id),
    KEY ix_appt_doctor   (doctor_id),
    KEY ix_appt_date     (doctor_id, appointment_date),
    CONSTRAINT fk_appt_patient
        FOREIGN KEY (patient_id) REFERENCES users(id)   ON DELETE CASCADE,
    CONSTRAINT fk_appt_doctor
        FOREIGN KEY (doctor_id)  REFERENCES doctors(id) ON DELETE CASCADE,
    -- SET NULL (not CASCADE): deleting an empty slot must never delete a
    -- patient's appointment.
    CONSTRAINT fk_appt_slot
        FOREIGN KEY (slot_id)    REFERENCES doctor_slots(id) ON DELETE SET NULL
) ENGINE=InnoDB;


-- ----------------------------------------------------- medical_records -----
CREATE TABLE IF NOT EXISTS medical_records (
    id                 INT AUTO_INCREMENT PRIMARY KEY,
    patient_id         INT  NOT NULL,
    doctor_id          INT  NULL,
    appointment_id     INT  NULL,
    visit_date         DATE NOT NULL,
    chief_complaint    TEXT NULL,
    symptoms           TEXT NULL,
    clinical_notes     TEXT NULL,
    diagnosis_notes    TEXT NULL,
    treatment_summary  TEXT NULL,
    medicines          TEXT NULL,
    doctor_instructions TEXT NULL,
    status             VARCHAR(30) NOT NULL DEFAULT 'ACTIVE',
    created_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                                ON UPDATE CURRENT_TIMESTAMP,
    KEY ix_mrec_patient (patient_id),
    CONSTRAINT fk_mrec_patient
        FOREIGN KEY (patient_id)     REFERENCES users(id)        ON DELETE CASCADE,
    CONSTRAINT fk_mrec_doctor
        FOREIGN KEY (doctor_id)      REFERENCES doctors(id)      ON DELETE SET NULL,
    CONSTRAINT fk_mrec_appointment
        FOREIGN KEY (appointment_id) REFERENCES appointments(id) ON DELETE SET NULL
) ENGINE=InnoDB;


-- ---------------------------------------------------------- treatments -----
CREATE TABLE IF NOT EXISTS treatments (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    patient_id        INT NOT NULL,
    medical_record_id INT NULL,
    doctor_id         INT NULL,
    treatment_name    VARCHAR(200) NOT NULL,
    description       TEXT NULL,
    start_date        DATE NULL,
    end_date          DATE NULL,
    status            VARCHAR(30) NOT NULL DEFAULT 'ONGOING',
    created_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                               ON UPDATE CURRENT_TIMESTAMP,
    KEY ix_treat_patient (patient_id),
    CONSTRAINT fk_treat_patient
        FOREIGN KEY (patient_id)        REFERENCES users(id)           ON DELETE CASCADE,
    CONSTRAINT fk_treat_medrec
        FOREIGN KEY (medical_record_id) REFERENCES medical_records(id) ON DELETE SET NULL,
    CONSTRAINT fk_treat_doctor
        FOREIGN KEY (doctor_id)         REFERENCES doctors(id)         ON DELETE SET NULL
) ENGINE=InnoDB;


-- ----------------------------------------------------------- follow_ups -----
CREATE TABLE IF NOT EXISTS follow_ups (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    patient_id        INT NOT NULL,
    medical_record_id INT NULL,
    doctor_id         INT NULL,
    appointment_id    INT NULL,
    follow_up_date    DATE NOT NULL,
    reason            TEXT NULL,
    instructions      TEXT NULL,
    status            VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    completed_at      DATETIME NULL,
    created_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                               ON UPDATE CURRENT_TIMESTAMP,
    KEY ix_fu_patient (patient_id),
    CONSTRAINT fk_fu_patient
        FOREIGN KEY (patient_id)        REFERENCES users(id)           ON DELETE CASCADE,
    CONSTRAINT fk_fu_medrec
        FOREIGN KEY (medical_record_id) REFERENCES medical_records(id) ON DELETE SET NULL,
    CONSTRAINT fk_fu_doctor
        FOREIGN KEY (doctor_id)         REFERENCES doctors(id)         ON DELETE SET NULL,
    CONSTRAINT fk_fu_appointment
        FOREIGN KEY (appointment_id)    REFERENCES appointments(id)    ON DELETE SET NULL
) ENGINE=InnoDB;


-- -------------------------------------------------------- prescriptions -----
CREATE TABLE IF NOT EXISTS prescriptions (
    id                 INT AUTO_INCREMENT PRIMARY KEY,
    patient_id         INT NOT NULL,
    doctor_id          INT NULL,
    medical_record_id  INT NULL,
    treatment_id       INT NULL,
    diagnosis          TEXT NULL,
    doctor_instructions TEXT NULL,
    created_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                                ON UPDATE CURRENT_TIMESTAMP,
    KEY ix_presc_patient (patient_id),
    CONSTRAINT fk_presc_patient
        FOREIGN KEY (patient_id)        REFERENCES users(id)           ON DELETE CASCADE,
    CONSTRAINT fk_presc_doctor
        FOREIGN KEY (doctor_id)         REFERENCES doctors(id)         ON DELETE SET NULL,
    CONSTRAINT fk_presc_medrec
        FOREIGN KEY (medical_record_id) REFERENCES medical_records(id) ON DELETE SET NULL,
    CONSTRAINT fk_presc_treatment
        FOREIGN KEY (treatment_id)      REFERENCES treatments(id)      ON DELETE SET NULL
) ENGINE=InnoDB;


-- ------------------------------------------------ prescription_medicines -----
CREATE TABLE IF NOT EXISTS prescription_medicines (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    prescription_id INT NOT NULL,
    medicine_name   VARCHAR(200) NOT NULL,
    dosage          VARCHAR(100) NULL,
    frequency       VARCHAR(100) NULL,
    duration        VARCHAR(100) NULL,
    instructions    VARCHAR(500) NULL,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY ix_med_presc (prescription_id),
    CONSTRAINT fk_med_presc
        FOREIGN KEY (prescription_id) REFERENCES prescriptions(id) ON DELETE CASCADE
) ENGINE=InnoDB;


-- ----------------------------------------------------- treatment_reviews -----
CREATE TABLE IF NOT EXISTS treatment_reviews (
    id                   INT AUTO_INCREMENT PRIMARY KEY,
    patient_id           INT NOT NULL,
    treatment_id         INT NULL,
    doctor_id            INT NULL,
    outcome              VARCHAR(100) NOT NULL,
    current_condition    VARCHAR(100) NOT NULL,
    experience           VARCHAR(100) NOT NULL,
    follow_up_preference VARCHAR(100) NOT NULL,
    change_reason        TEXT NULL,
    rating               INT  NULL,
    comment              TEXT NULL,
    created_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                                  ON UPDATE CURRENT_TIMESTAMP,
    KEY ix_rev_patient (patient_id),
    CONSTRAINT fk_rev_patient
        FOREIGN KEY (patient_id)   REFERENCES users(id)      ON DELETE CASCADE,
    CONSTRAINT fk_rev_treatment
        FOREIGN KEY (treatment_id) REFERENCES treatments(id) ON DELETE SET NULL,
    CONSTRAINT fk_rev_doctor
        FOREIGN KEY (doctor_id)    REFERENCES doctors(id)    ON DELETE SET NULL
) ENGINE=InnoDB;


-- -------------------------------------------------------- notifications -----
CREATE TABLE IF NOT EXISTS notifications (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    user_id           INT NOT NULL,
    appointment_id    INT NULL,
    title             VARCHAR(200) NOT NULL,
    message           TEXT NOT NULL,
    notification_type VARCHAR(50) NOT NULL DEFAULT 'GENERAL',
    is_read           BOOLEAN NOT NULL DEFAULT FALSE,
    created_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY ix_notif_user (user_id),
    CONSTRAINT fk_notif_user
        FOREIGN KEY (user_id)        REFERENCES users(id)        ON DELETE CASCADE,
    CONSTRAINT fk_notif_appointment
        FOREIGN KEY (appointment_id) REFERENCES appointments(id) ON DELETE SET NULL
) ENGINE=InnoDB;


-- ----------------------------------------------------- screening_history -----
CREATE TABLE IF NOT EXISTS screening_history (
    id                     INT AUTO_INCREMENT PRIMARY KEY,
    patient_id             INT NOT NULL,
    symptoms               TEXT NOT NULL,
    ai_response            TEXT NULL,
    care_category          VARCHAR(100) NULL,
    recommended_specialist VARCHAR(100) NULL,
    severity               VARCHAR(30)  NULL,
    created_at             DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY ix_scrn_patient (patient_id),
    CONSTRAINT fk_scrn_patient
        FOREIGN KEY (patient_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB;


-- ------------------------------------------------------ patient_documents -----
CREATE TABLE IF NOT EXISTS patient_documents (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    patient_id        INT NOT NULL,
    medical_record_id INT NULL,
    document_name     VARCHAR(255) NOT NULL,
    document_type     VARCHAR(100) NULL,
    file_path         VARCHAR(500) NOT NULL,
    file_size         BIGINT NULL,
    uploaded_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status            VARCHAR(30) NOT NULL DEFAULT 'UPLOADED',
    KEY ix_doc_patient (patient_id),
    CONSTRAINT fk_doc_patient
        FOREIGN KEY (patient_id)        REFERENCES users(id)           ON DELETE CASCADE,
    CONSTRAINT fk_doc_medrec
        FOREIGN KEY (medical_record_id) REFERENCES medical_records(id) ON DELETE SET NULL
) ENGINE=InnoDB;


-- ============================================================================
-- 3. SEED DATA
-- ============================================================================

-- ------------------------------------------------------- 5 visit types -----
INSERT IGNORE INTO visit_types
    (name, min_duration_minutes, max_duration_minutes, default_duration_minutes, is_active)
VALUES
    ('General Consultation',   10, 15, 15, TRUE),
    ('Follow-up',              10, 15, 10, TRUE),
    ('Specialist Consultation',15, 20, 20, TRUE),
    ('Detailed Consultation',  20, 30, 30, TRUE),
    ('Procedure / Assessment', 30, 60, 45, TRUE);


-- --------------------------------------------------------- 20 doctors ------
INSERT IGNORE INTO doctors
    (name, email, phone, specialization, qualification,
     experience_years, languages, consultation_fee, bio, is_active)
VALUES
    ('Dr. Amit Sharma',   'amit.sharma@sanjeevani.com',   '9876543210', 'Cardiology',       'MBBS, MD Cardiology',      8, 'Hindi, English',  800.00, 'Senior consultant in Cardiology at Sanjeevani Clinic.', TRUE),
    ('Dr. Neha Verma',    'neha.verma@sanjeevani.com',    '9876500001', 'Cardiology',       'MBBS, MD Cardiology',      6, 'Hindi, English',  700.00, 'Cardiology consultant at Sanjeevani Clinic.',           TRUE),
    ('Dr. Priya Mehta',   'priya.mehta@sanjeevani.com',   '9876500002', 'Dermatology',      'MBBS, MD Dermatology',     7, 'Hindi, English',  600.00, 'Dermatology specialist at Sanjeevani Clinic.',          TRUE),
    ('Dr. Rahul Jain',    'rahul.jain@sanjeevani.com',    '9876500003', 'Dermatology',      'MBBS, MD Dermatology',    10, 'Hindi, English',  800.00, 'Dermatology specialist at Sanjeevani Clinic.',          TRUE),
    ('Dr. Arjun Singh',   'arjun.singh@sanjeevani.com',   '9876500004', 'Neurology',        'MBBS, DM Neurology',       9, 'Hindi, English', 1000.00, 'Neurology specialist at Sanjeevani Clinic.',            TRUE),
    ('Dr. Kavita Rao',    'kavita.rao@sanjeevani.com',    '9876500005', 'Neurology',        'MBBS, MD, DM Neurology',  12, 'Hindi, English', 1200.00, 'Senior neurologist at Sanjeevani Clinic.',              TRUE),
    ('Dr. Raj Malhotra',  'raj.malhotra@sanjeevani.com',  '9876500006', 'Orthopedics',      'MBBS, MS Orthopedics',    11, 'Hindi, English',  900.00, 'Orthopedics specialist at Sanjeevani Clinic.',          TRUE),
    ('Dr. Anjali Gupta',  'anjali.gupta@sanjeevani.com',  '9876500007', 'Orthopedics',      'MBBS, MS Orthopedics',     6, 'Hindi, English',  700.00, 'Orthopedics specialist at Sanjeevani Clinic.',          TRUE),
    ('Dr. Rohan Sharma',  'rohan.sharma@sanjeevani.com',  '9876500008', 'Pediatrics',       'MBBS, MD Pediatrics',      8, 'Hindi, English',  600.00, 'Pediatrician at Sanjeevani Clinic.',                    TRUE),
    ('Dr. Sneha Kapoor',  'sneha.kapoor@sanjeevani.com',  '9876500009', 'Pediatrics',       'MBBS, MD Pediatrics',      5, 'Hindi, English',  550.00, 'Pediatrician at Sanjeevani Clinic.',                    TRUE),
    ('Dr. Vikram Joshi',  'vikram.joshi@sanjeevani.com',  '9876500010', 'General Medicine', 'MBBS, MD Medicine',       10, 'Hindi, English',  500.00, 'General physician at Sanjeevani Clinic.',               TRUE),
    ('Dr. Pooja Shah',    'pooja.shah@sanjeevani.com',    '9876500011', 'General Medicine', 'MBBS, MD Medicine',        7, 'Hindi, English',  450.00, 'General physician at Sanjeevani Clinic.',               TRUE),
    ('Dr. Nitin Agarwal', 'nitin.agarwal@sanjeevani.com', '9876500012', 'Ophthalmology',    'MBBS, MS Ophthalmology',   9, 'Hindi, English',  700.00, 'Eye specialist at Sanjeevani Clinic.',                  TRUE),
    ('Dr. Riya Bansal',   'riya.bansal@sanjeevani.com',   '9876500013', 'Ophthalmology',    'MBBS, MS Ophthalmology',   6, 'Hindi, English',  650.00, 'Eye specialist at Sanjeevani Clinic.',                  TRUE),
    ('Dr. Karan Mehta',   'karan.mehta@sanjeevani.com',   '9876500014', 'Dentistry',        'BDS, MDS',                 8, 'Hindi, English',  500.00, 'Dental surgeon at Sanjeevani Clinic.',                  TRUE),
    ('Dr. Simran Kaur',   'simran.kaur@sanjeevani.com',   '9876500015', 'Dentistry',        'BDS, MDS',                 5, 'Hindi, English',  450.00, 'Dental surgeon at Sanjeevani Clinic.',                  TRUE),
    ('Dr. Manish Sethi',  'manish.sethi@sanjeevani.com',  '9876500016', 'ENT',              'MBBS, MS ENT',            10, 'Hindi, English',  650.00, 'ENT specialist at Sanjeevani Clinic.',                  TRUE),
    ('Dr. Aarti Mishra',  'aarti.mishra@sanjeevani.com',  '9876500017', 'ENT',              'MBBS, MS ENT',             7, 'Hindi, English',  600.00, 'ENT specialist at Sanjeevani Clinic.',                  TRUE),
    ('Dr. Shreya Kapoor', 'shreya.kapoor@sanjeevani.com', '9876500018', 'Gynecology',       'MBBS, MS Gynecology',      9, 'Hindi, English',  800.00, 'Gynecologist at Sanjeevani Clinic.',                    TRUE),
    ('Dr. Meera Joshi',   'meera.joshi@sanjeevani.com',   '9876500019', 'Gynecology',       'MBBS, MD Gynecology',     12, 'Hindi, English', 1000.00, 'Senior gynecologist at Sanjeevani Clinic.',             TRUE);


-- --------------------------------- 140 schedules (20 doctors x 7 days) -----
-- All doctors are available every day, 10:00-14:00, in 5-minute steps.
-- The WHERE NOT EXISTS guard means re-running this file will not create
-- duplicate schedule rows.
INSERT INTO doctor_schedules
    (doctor_id, day_of_week, start_time, end_time, slot_interval_minutes, is_available)
SELECT d.id, w.day_no, '10:00:00', '14:00:00', 5, TRUE
FROM doctors d
CROSS JOIN (
    SELECT 0 AS day_no UNION ALL SELECT 1 UNION ALL SELECT 2 UNION ALL
    SELECT 3 UNION ALL SELECT 4 UNION ALL SELECT 5 UNION ALL SELECT 6
) w
WHERE NOT EXISTS (
    SELECT 1 FROM doctor_schedules s
    WHERE s.doctor_id = d.id AND s.day_of_week = w.day_no
);


-- ------------------------------------------------------- 2 demo logins -----
-- Passwords are real Argon2 hashes produced by the app's own
-- src/security/password.py, so these accounts work on the login page.
--   patient@demo.com / Demo@1234
--   admin@demo.com   / Admin@1234
INSERT IGNORE INTO users
    (name, email, phone, password_hash, age, gender, role, is_active)
VALUES
    ('Demo Patient', 'patient@demo.com', '9000000001',
     '$argon2id$v=19$m=65536,t=3,p=4$VNDqehahMb4vW5KgwHls0Q$dWH8nqN4IJOkmUAayBz3s9s4NZUuq1ttQpXqdx5Lk1Q',
     30, 'Male', 'PATIENT', TRUE),
    ('Demo Admin', 'admin@demo.com', '9000000002',
     '$argon2id$v=19$m=65536,t=3,p=4$6SYvIAxmNJVi0ZGA/UK71w$G3TwH8zTINPa+WiN5PY1PFZ8nT6rqmvWQuSvZR2wus4',
     35, 'Female', 'ADMIN', TRUE);


-- ============================================================================
-- 4. VERIFY - the last result grid should show these numbers
-- ============================================================================
--    tables            15
--    users              2
--    doctors           20
--    doctor_schedules 140
--    visit_types        5
-- ============================================================================

SELECT 'users'            AS what, COUNT(*) AS total, 'expect 2'   AS note FROM users
UNION ALL SELECT 'doctors',          COUNT(*), 'expect 20'  FROM doctors
UNION ALL SELECT 'doctor_schedules', COUNT(*), 'expect 140' FROM doctor_schedules
UNION ALL SELECT 'visit_types',      COUNT(*), 'expect 5'   FROM visit_types
UNION ALL SELECT 'appointments',     COUNT(*), 'starts at 0' FROM appointments
UNION ALL SELECT 'TABLES IN DB',     COUNT(*), 'expect 15'
    FROM information_schema.tables
    WHERE table_schema = 'sanjeevani_clinic';
