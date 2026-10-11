"""
build_workbench_sql.py - generates the SQL you paste into MySQL Workbench.

Two files come out of this:

  pharmacy_seed.sql                    only the pharmacy DATA (32 diseases,
                                       111 medicines, links, partner chemists,
                                       demo logins, one sample prescription).
                                       Run it after pharmacy_setup.sql.

  database_setup_with_pharmacy.sql     ONE safe script for an existing project:
                                       your 15 clinic tables + seed data
                                       (copied from database_setup.sql with the
                                       DROP DATABASE line removed) + the 12
                                       pharmacy tables + pharmacy data + a
                                       verification grid.

Every statement is idempotent:
  * CREATE DATABASE / CREATE TABLE IF NOT EXISTS   -> nothing is destroyed
  * INSERT IGNORE on the natural unique keys       -> re-running adds nothing
  * parent lookups by email / sku / name           -> no hard-coded ids
So you can run it twice by mistake and your data is still fine.

Usage:
    python build_workbench_sql.py                  # reads sanjeevani_clinic.db
    python build_workbench_sql.py --db other.db
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sqlite3
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

TABLES = ("diseases", "medicines", "medicine_diseases", "nearby_pharmacies",
          "nearby_pharmacy_stocks")

LOGINS = [
    # name, email, phone, role, age, gender
    ("Super User", "superuser@sanjeevani.com", "9876500100", "SUPERUSER", 41, "Male"),
    ("Clinic Admin", "admin@demo.com", "9876500200", "ADMIN", 35, "Female"),
    ("Ravi Pharmacist", "pharmacist@demo.com", "9876500300", "PHARMACIST", 29, "Male"),
    ("Dr. Vikram Joshi", "doctor@demo.com", "9876500400", "DOCTOR", 44, "Male"),
    ("Demo Patient", "patient@demo.com", "9000000001", "PATIENT", 30, "Male"),
]

Rx_SENTINEL = "Acute bronchitis with low grade fever"


# --------------------------------------------------------------------------
# tiny SQL literal writer (no external dependency)
# --------------------------------------------------------------------------

def lit(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (dt.datetime, dt.date)):
        if isinstance(value, dt.datetime):
            return "'" + value.replace(microsecond=0).isoformat(sep=" ") + "'"
        return f"'{value.isoformat()}'"
    text = str(value)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}.*", text):
        return "'" + text[:10] + " " + text[11:19] + "'"
    escaped = (text.replace("\\", "\\\\")
                    .replace("'", "''")
                    .replace("\n", "\\n")
                    .replace("\r", "")
                    .replace("\x00", ""))
    return f"'{escaped}'"


def columns_of(db: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in db.execute(f"PRAGMA table_info({table})")]


def rows_of(db: sqlite3.Connection, table: str, order_by: str = "id"):
    cols = columns_of(db, table)
    out = []
    for row in db.execute(f"SELECT {', '.join(cols)} FROM {table} ORDER BY {order_by}"):
        out.append(dict(zip(cols, row)))
    return cols, out


def insert_rows(table: str, cols: list[str], rows: list[dict]) -> list[str]:
    if not rows:
        return []
    lines = [f"INSERT IGNORE INTO `{table}` ({', '.join('`' + c + '`' for c in cols)}) VALUES"]
    values = []
    for row in rows:
        values.append("  (" + ", ".join(lit(row[c]) for c in cols) + ")")
    lines.append(",\n".join(values) + ";")
    return lines


# --------------------------------------------------------------------------
# the pharmacy DATA
# --------------------------------------------------------------------------

def build_seed(db: sqlite3.Connection) -> str:
    parts: list[str] = []

    parts.append("""-- ============================================================================
--  PHARMACY SEED DATA  (diseases, medicines, chemists, logins, demo Rx)
-- ============================================================================
--
--  Generated from the app's own data by build_workbench_sql.py.
--  Safe to run more than once:
--      * INSERT IGNORE  -> rows are matched on their unique key
--      * child rows look up their parent by sku / name / email, never by id
--  Regenerate any time with:   python build_workbench_sql.py
--
--  Passwords below are real Argon2 hashes made by src/security/password.py,
--  so these accounts work on the login page immediately:
--      superuser@sanjeevani.com  Super@1234     (everything + roles)
--      admin@demo.com            Admin@1234     (all but role editing)
--      pharmacist@demo.com       Pharma@1234   (orders, stock, nearby)
--      doctor@demo.com           Doctor@1234   (catalog view)
--      patient@demo.com          Demo@1234     (shop + buy)
-- ============================================================================

USE sanjeevani_clinic;
""")

    # ---- users first (the medicines need nobody, but the Rx needs a patient)
    parts.append("-- ---------------------------------------------------------------- 1. logins --")
    user_cols, user_rows = rows_of(db, "users", order_by="id")
    hashes = {row["email"]: row["password_hash"] for row in user_rows}
    keep = ("name", "email", "phone", "password_hash", "age", "gender", "role",
            "is_active", "created_at", "updated_at")
    now = dt.datetime.now().replace(microsecond=0)
    login_rows = []
    for name, email, phone, role, age, gender in LOGINS:
        if email not in hashes:          # demo DB must contain every login
            continue
        login_rows.append({
            "name": name, "email": email, "phone": phone,
            "password_hash": hashes[email], "age": age, "gender": gender,
            "role": role, "is_active": True,
            "created_at": now, "updated_at": now,
        })
    parts.append("\n".join(
        "INSERT IGNORE INTO `users` (%s) VALUES (%s);" % (
            ", ".join(f"`{c}`" for c in keep),
            ", ".join(lit(row[c]) for c in keep)
        ) for row in login_rows
    ))

    # ---- catalog tables
    for title, table in (("2. diseases (the filter chips on /pharmacy)", "diseases"),
                         ("3. medicines (price, stock, photo, Rx rule)", "medicines")):
        cols, rows = rows_of(db, table)
        parts.append(f"\n-- ---------------------------------------------------------------- {title} --")
        parts.append(f"-- {len(rows)} rows")
        parts.extend(insert_rows(table, cols, rows))

    # ---- many-to-many links, resolved by natural key
    cols, links = rows_of(db, "medicine_diseases")
    med_sku = {row["id"]: row["sku"] for row in rows_of(db, "medicines")[1]}
    dis_name = {row["id"]: row["name"] for row in rows_of(db, "diseases")[1]}
    parts.append("\n-- ---------------------------------------------------------------- 4. which medicine treats what --")
    parts.append(f"-- {len(links)} links (medicine sku x disease name, so no hard-coded ids)")
    body = []
    for link in links:
        sku = med_sku.get(link["medicine_id"])
        name = dis_name.get(link["disease_id"])
        if not sku or not name:
            continue
        body.append(
            "INSERT IGNORE INTO `medicine_diseases` "
            "(`medicine_id`, `disease_id`, `is_primary`, `created_at`) "
            "SELECT m.`id`, d.`id`, %s, %s FROM `medicines` m, `diseases` d "
            "WHERE m.`sku` = %s AND d.`name` = %s;"
            % (lit(bool(link["is_primary"])), lit(now), lit(sku), lit(name))
        )
    parts.append("\n".join(body))

    # ---- partner chemists, idempotent on name
    cols, shops = rows_of(db, "nearby_pharmacies")
    parts.append("\n-- ---------------------------------------------------------------- 5. partner chemists (the SQL side of \"nearby\") --")
    for shop in shops:
        inserts = ", ".join(f"`{c}`" for c in cols)
        values = ", ".join(lit(shop[c]) for c in cols)
        parts.append(
            f"INSERT INTO `nearby_pharmacies` ({inserts})\n"
            f"SELECT {values} FROM DUAL WHERE NOT EXISTS (\n"
            f"  SELECT 1 FROM `nearby_pharmacies` x WHERE x.`name` = {lit(shop['name'])});"
        )

    # ---- their stock, parent ids looked up by name / sku
    cols, stock = rows_of(db, "nearby_pharmacy_stocks")
    shop_name = {row["id"]: row["name"] for row in shops}
    parts.append("\n-- ---------------------------------------------------------------- 6. what each chemist has in stock --")
    parts.append(f"-- {len(stock)} rows")
    body = []
    for row in stock:
        name = shop_name.get(row["pharmacy_id"])
        if not name:
            continue
        body.append(
            "INSERT IGNORE INTO `nearby_pharmacy_stocks` "
            "(`pharmacy_id`, `medicine_id`, `medicine_label`, `stock`, `price`, `trust`, `updated_at`) "
            "SELECT p.`id`, m.`id`, m.`name`, %s, %s, %s, %s "
            "FROM `nearby_pharmacies` p, `medicines` m "
            "WHERE p.`name` = %s AND m.`sku` = %s;"
            % (lit(row["stock"]), lit(row["price"]), lit(row["trust"]), lit(now),
               lit(name), lit(med_sku.get(row["medicine_id"], "")))
        )
    parts.append("\n".join(body))

    # ---- one demo prescription so /pharmacy/prescriptions has something
    parts.append("\n-- ---------------------------------------------------------------- 7. a demo prescription for the \"buy what the doctor gave\" page --")
    rx_cols, rx_rows = rows_of(db, "prescriptions")
    if not rx_rows:
        parts.append("-- (the demo database had no prescription, so nothing to insert here)")
        rx_rows = []
    for rx in rx_rows:
        parts.append(
        "INSERT INTO `prescriptions` "
        "(`patient_id`, `doctor_id`, `diagnosis`, `doctor_instructions`, `created_at`, `updated_at`)\n"
        "SELECT p.`id`, d.`id`, %s, %s, %s, %s\n"
        "FROM `users` p, `doctors` d\n"
        "WHERE p.`email` = 'patient@demo.com' AND d.`email` = 'vikram.joshi@sanjeevani.com'\n"
        "  AND NOT EXISTS (SELECT 1 FROM `prescriptions` x "
        "                   WHERE x.`patient_id` = p.`id` AND x.`diagnosis` = %s);"
        % (lit(Rx_SENTINEL), lit(rx["doctor_instructions"]), lit(now), lit(now),
           lit(Rx_SENTINEL))
        )

    med_cols, med_rows = rows_of(db, "prescription_medicines")
    med_rows = [row for row in med_rows if rx_rows and row["prescription_id"] == rx_rows[0]["id"]]
    body = []
    for row in med_rows:
        # this table has no natural unique key, so INSERT IGNORE cannot help -
        # guard on (this prescription, this medicine name) instead, which keeps
        # the script re-runnable.
        body.append(
            "INSERT INTO `prescription_medicines` "
            "(`prescription_id`, `medicine_name`, `dosage`, `frequency`, `duration`, `instructions`, `created_at`) "
            "SELECT x.`id`, %s, %s, %s, %s, %s, %s FROM `prescriptions` x, `users` u "
            "WHERE x.`patient_id` = u.`id` AND u.`email` = 'patient@demo.com' "
            "AND x.`diagnosis` = %s "
            "AND NOT EXISTS (SELECT 1 FROM `prescription_medicines` y "
            "                WHERE y.`prescription_id` = x.`id` AND y.`medicine_name` = %s);"
            % (lit(row["medicine_name"]), lit(row["dosage"]), lit(row["frequency"]),
               lit(row["duration"]), lit(row["instructions"]), lit(now),
               lit(Rx_SENTINEL), lit(row["medicine_name"]))
        )
    parts.append("\n".join(body))

    parts.append("""
-- ---------------------------------------------------------------- what you should now have --
SELECT 'diseases'               AS what, COUNT(*) AS total, 'expect 32'  AS note FROM diseases
UNION ALL SELECT 'medicines',               COUNT(*), 'expect 111' FROM medicines
UNION ALL SELECT 'medicine_diseases',       COUNT(*), 'expect 158' FROM medicine_diseases
UNION ALL SELECT 'medicines with a photo',  COUNT(*), 'expect 111' FROM medicines WHERE image_path IS NOT NULL
UNION ALL SELECT 'prescription-only meds',  COUNT(*), 'expect 55'  FROM medicines WHERE requires_prescription = TRUE
UNION ALL SELECT 'nearby_pharmacies',       COUNT(*), 'expect 6'   FROM nearby_pharmacies
UNION ALL SELECT 'nearby stock rows',       COUNT(*), 'expect 25'  FROM nearby_pharmacy_stocks
UNION ALL SELECT 'demo logins',             COUNT(*), 'expect >= 5' FROM users
UNION ALL SELECT 'cart items (empty)',      COUNT(*), 'starts at 0' FROM pharmacy_cart_items
UNION ALL SELECT 'orders (empty)',          COUNT(*), 'starts at 0' FROM pharmacy_orders;
""")

    return "\n".join(part for part in parts if part.strip()) + "\n"


# --------------------------------------------------------------------------
# the combined, safe "paste everything" script
# --------------------------------------------------------------------------

def build_combined(seed_sql: str) -> str:
    """The whole database_setup.sql, neutralised, + pharmacy DDL + pharmacy data."""

    clinic = open(os.path.join(BASE_DIR, "database_setup.sql"), encoding="utf-8").read()

    # 1. never drop the database - this is the whole point of this new file
    clinic, dropped = re.subn(r"(?im)^\s*DROP DATABASE[^;]*;\s*$",
                              "-- DROP DATABASE removed on purpose: this script must never delete data",
                              clinic)
    if not dropped:
        raise SystemExit("database_setup.sql has no DROP DATABASE line? adjust the generator")

    # 2. tolerate a database that already exists
    clinic = re.sub(r"(?i)CREATE DATABASE sanjeevani_clinic",
                    "CREATE DATABASE IF NOT EXISTS sanjeevani_clinic", clinic)

    # 2b. the copied header still describes the OLD behaviour - fix the wording,
    #     because it is exactly the sentence that makes people fear a paste.
    stale = """--  This script is safe to run more than once. It rebuilds the database from
--  scratch each time (see the DROP DATABASE line just below). If you want to
--  keep existing data, put two dashes in front of the DROP line to comment
--  it out - the rest of the script then only fills in what is missing."""
    fixed = """--  This script is safe to run more than once and it does NOT rebuild the
--  database from scratch: the DROP DATABASE line of database_setup.sql was
--  removed here on purpose. Your appointments, medical_records, follow_ups,
--  prescriptions and uploaded reports stay exactly where they are - every
--  statement below is CREATE ... IF NOT EXISTS or INSERT IGNORE, so a second
--  run reports "0 rows affected" and changes nothing."""
    if stale not in clinic:
        raise SystemExit("database_setup.sql header changed - update build_combined (stale text)")
    clinic = clinic.replace(stale, fixed, 1)

    clinic = clinic.replace("--    15 tables + indexes + foreign keys",
                            "--    27 tables + indexes + foreign keys (15 clinic + 12 pharmacy)", 1)
    clinic = clinic.replace("--     2 demo logins you can use right away",
                            "--     5 demo logins you can use right away", 1)

    # 3. pharmacy DDL = the CREATE TABLE statements of the generated file, in order
    ddl = open(os.path.join(BASE_DIR, "pharmacy_setup.sql"), encoding="utf-8").read()
    # drop every comment line first, otherwise the header text (which mentions
    # "CREATE TABLE IF NOT EXISTS") would be matched as a statement
    ddl = "\n".join(ln for ln in ddl.splitlines() if not ln.strip().startswith("--"))
    tables = re.findall(r"(?m)^CREATE TABLE IF NOT EXISTS.*?COLLATE=utf8mb4_unicode_ci;",
                        ddl, re.S)
    if len(tables) != 12:
        raise SystemExit(f"expected 12 pharmacy CREATE TABLEs, got {len(tables)}")

    banner = """-- ============================================================================
--  SANJEEVANI CLINIC - COMPLETE SETUP, INCLUDING THE PHARMACY  (MySQL)
-- ============================================================================
--
--  Same result as database_setup.sql, plus the 12 pharmacy tables and their
--  demo data - and it will NOT delete anything you already have.
--
--   * no DROP DATABASE              -> appointments, records, follow-ups stay
--   * CREATE ... IF NOT EXISTS      -> safe on an existing database
--   * INSERT IGNORE / WHERE NOT EXISTS on every seed row -> run it twice, the
--     second run reports "0 rows affected" and changes nothing
--   * 15 clinic tables + 12 pharmacy tables = 27
--
--  HOW TO USE
--  ----------
--   1. MySQL Workbench -> File -> Open SQL Script -> this file
--   2. Lightning bolt (Ctrl+Shift+Enter) -> "Execute all statements"
--   3. Last two result grids show the row counts and all 27 table names.
--   4. From the project folder in a terminal:
--          python -m uvicorn main:app --port 8000 --reload
--      then open  http://127.0.0.1:8000/pharmacy
--
--  The app also creates these tables by itself on startup, so this file is for
--  review and for setting up a fresh machine before the first start.
--
--  Generated by  python build_workbench_sql.py  - do not edit the seed part by
--  hand; edit the data (or seed_pharmacy.py) and regenerate.
-- ============================================================================

"""

    pharmacy_head = (
        "\n\n-- ============================================================================\n"
        "--  PHARMACY MODULE - 12 new tables (generated from src/models/*.py)\n"
        "-- ============================================================================\n\n"
    )
    seed_head = (
        "\n\n-- ============================================================================\n"
        "--  PHARMACY MODULE - demo data\n"
        "-- ============================================================================\n"
    )
    seed_body = seed_sql.replace("USE sanjeevani_clinic;\n", "")

    tail = """

-- ============================================================================
--  FINAL CHECK - all 27 tables and the pharmacy totals
-- ============================================================================
SELECT TABLE_NAME AS table_name, TABLE_ROWS AS approx_rows
FROM information_schema.tables
WHERE table_schema = 'sanjeevani_clinic'
ORDER BY TABLE_NAME;

SELECT (SELECT COUNT(*) FROM information_schema.tables
         WHERE table_schema = 'sanjeevani_clinic')  AS tables_total,
       'expect 27'                                  AS note;

SELECT (SELECT COUNT(*) FROM medicines)             AS medicines,   'expect 111' AS note
UNION ALL SELECT (SELECT COUNT(*) FROM diseases),          'expect 32'
UNION ALL SELECT (SELECT COUNT(*) FROM medicine_diseases), 'expect 158'
UNION ALL SELECT (SELECT COUNT(*) FROM nearby_pharmacies), 'expect 6'
UNION ALL SELECT (SELECT COUNT(*) FROM nearby_pharmacy_stocks), 'expect 25'
UNION ALL SELECT (SELECT COUNT(*) FROM users WHERE role = 'SUPERUSER'), 'expect 1'
UNION ALL SELECT (SELECT COUNT(*) FROM pharmacy_orders), 'starts at 0';

-- ---------------------------------------------------------------------------
--  DOCTOR DESK + ROLE MATRIX - the parts the newest features need
--  (every line answers "present" / a number; nothing here changes data)
-- ---------------------------------------------------------------------------
SELECT 'doctor_patient_notes table' AS what,
       IF(COUNT(*) = 1, 'present', 'MISSING - re-paste this file') AS status
  FROM information_schema.tables
 WHERE table_schema = 'sanjeevani_clinic' AND table_name = 'doctor_patient_notes'
UNION ALL
SELECT 'treatment_reviews.updated_at column',
       IF(COUNT(*) = 1, 'present',
          'MISSING - run: ALTER TABLE treatment_reviews ADD COLUMN updated_at DATETIME NULL')
  FROM information_schema.columns
 WHERE table_schema = 'sanjeevani_clinic' AND table_name = 'treatment_reviews'
   AND column_name = 'updated_at'
UNION ALL
SELECT 'appointments payment columns',
       IF(COUNT(*) >= 3, 'present', 'MISSING - the desk billing tab needs these')
  FROM information_schema.columns
 WHERE table_schema = 'sanjeevani_clinic' AND table_name = 'appointments'
   AND column_name IN ('payment_method', 'payment_status', 'payment_amount')
UNION ALL
SELECT 'module tables found',
       CONCAT(COUNT(*), ' (expect 12)')
  FROM information_schema.tables
 WHERE table_schema = 'sanjeevani_clinic'
   AND table_name IN ('diseases','medicines','medicine_diseases','pharmacy_cart_items',
                      'nearby_pharmacies','nearby_pharmacy_stocks','pharmacy_snapshots',
                      'pharmacy_orders','pharmacy_order_items','pharmacy_audit_logs',
                      'role_permissions','doctor_patient_notes')
UNION ALL
SELECT 'role_permissions override rows',
       CONCAT(COUNT(*), ' (0 = every role uses the defaults in src/security/rbac.py)')
  FROM role_permissions
UNION ALL
SELECT 'logins by role',
       CONCAT('PATIENT ', (SELECT COUNT(*) FROM users WHERE role = 'PATIENT'),
              ' | DOCTOR ', (SELECT COUNT(*) FROM users WHERE role = 'DOCTOR'),
              ' | PHARMACIST ', (SELECT COUNT(*) FROM users WHERE role = 'PHARMACIST'),
              ' | ADMIN ', (SELECT COUNT(*) FROM users WHERE role = 'ADMIN'),
              ' | SUPERUSER ', (SELECT COUNT(*) FROM users WHERE role = 'SUPERUSER'));

-- ---------------------------------------------------------------------------
--  5. (OPTIONAL) the two MySQL accounts this project logs in with
--  Kept at the very END on purpose: if your Workbench user is not an admin,
--  these lines fail with ERROR 1227 and your database is already complete by
--  then - just ignore / delete this block.
--  .env then uses:  DB_USER=sanjeevani_app  DB_PASSWORD=Sanjeevani@12345
-- ---------------------------------------------------------------------------
CREATE USER IF NOT EXISTS 'sanjeevani'@'localhost'   IDENTIFIED BY 'data@123';
GRANT ALL PRIVILEGES ON sanjeevani_clinic.* TO 'sanjeevani'@'localhost';

CREATE USER IF NOT EXISTS 'sanjeevani_app'@'localhost'
    IDENTIFIED BY 'Sanjeevani@12345';
GRANT ALL PRIVILEGES ON sanjeevani_clinic.* TO 'sanjeevani_app'@'localhost';
FLUSH PRIVILEGES;

SELECT user, host FROM mysql.user
 WHERE user IN ('sanjeevani', 'sanjeevani_app')
 ORDER BY user;
"""

    return banner + clinic + pharmacy_head + "\n\n".join(tables) + seed_head + seed_body + tail


STANDALONE_HEAD = [
    "-- ============================================================================",
    "--  SANJEEVANI CLINIC - PHARMACY: 12 NEW TABLES + 5 DEMO LOGINS         (MySQL)",
    "-- ============================================================================",
    "--  Paste this whole file into MySQL Workbench, then Ctrl+Shift+Enter",
    "--  (\"Execute all statements\").",
    "--",
    "--   * ADDS the 12 pharmacy tables to the database you already use. Nothing is",
    "--     dropped or rewritten: every statement is CREATE TABLE IF NOT EXISTS, so",
    "--     running it twice is harmless (the second run reports 0 rows affected).",
    "--   * the 5 demo logins are real Argon2 hashes made by the app itself, so the",
    "--     login page works with them immediately.",
    "--   * the catalogue (32 diseases, 111 medicines, 6 chemists, their stock) is",
    "--     NOT here on purpose - that INSERT block is ~100 KB. Load it with ONE of:",
    "--         python seed_pharmacy.py            <- recommended; also creates the",
    "--                                               pinned baseline snapshot the",
    "--                                               rollback tab uses, and demo",
    "--                                               doctors if there are none, and the",
    "--                                               demo OPD history the doctor desk shows",
    "--         database_setup_with_pharmacy.sql   <- clinic tables + pharmacy +",
    "--                                               all data in one file, for a",
    "--                                               fresh machine or for review",
    "--   * generated by  python build_workbench_sql.py  - edit that, not this file",
    "-- ============================================================================",
    "",
    "CREATE DATABASE IF NOT EXISTS sanjeevani_clinic",
    "    CHARACTER SET utf8mb4",
    "    COLLATE utf8mb4_unicode_ci;",
    "",
    "USE sanjeevani_clinic;",
    "",
    "-- Preflight: this file only ADDS the pharmacy - your own data is never touched.",
    "SELECT IF((SELECT COUNT(*) FROM information_schema.tables",
    "            WHERE table_schema = 'sanjeevani_clinic'",
    "              AND table_name IN ('users', 'prescriptions')) = 2,",
    "          'OK - clinic tables found, adding the 12 pharmacy tables',",
    "          'NOTE - clinic tables not found yet; the pharmacy tables below are still created, but for a complete database run database_setup_with_pharmacy.sql') AS preflight_check;",
    "",
    "SET @has_users := (SELECT COUNT(*) FROM information_schema.tables",
    "                   WHERE table_schema = 'sanjeevani_clinic'",
    "                     AND table_name = 'users');",
    "",
    "-- ---------------------------------------------------------------- 12 tables --",
    "-- Created with FOREIGN_KEY_CHECKS off so this file also works before the",
    "-- clinic tables exist; the relations themselves are still declared.",
    "SET FOREIGN_KEY_CHECKS = 0;",
    "",
]

STANDALONE_LOGIN_HEAD = [
    "",
    "-- ---------------------------------------------------------------- login rows --",
    "-- Guarded: skipped quietly when this database has no `users` table yet.",
]

STANDALONE_CHECKS = [
    "",
    "-- ------------------------------------------------------------------- verify --",
    "SELECT (SELECT COUNT(*) FROM information_schema.tables",
    "         WHERE table_schema = 'sanjeevani_clinic')              AS tables_total,",
    "       '12 pharmacy tables here, 27 with your clinic tables'  AS note;",
    "",
    "-- the desk table is the newest of the 12: if this says 'MISSING', the",
    "-- file was pasted from an older copy - re-paste this one.",
    "SELECT IF(COUNT(*) = 1, 'present', 'MISSING') AS doctor_patient_notes,",
    "       'needed by /doctor-desk notes + the 12th table' AS note",
    "  FROM information_schema.tables",
    " WHERE table_schema = 'sanjeevani_clinic' AND table_name = 'doctor_patient_notes';",
    "",
    "SELECT COUNT(*) AS medicines, '0 is normal - run: python seed_pharmacy.py' AS note",
    "  FROM medicines",
    "UNION ALL SELECT COUNT(*), '0 is normal' FROM diseases",
    "UNION ALL SELECT COUNT(*), '6 partner chemists after seeding' FROM nearby_pharmacies;",
    "",
]


def build_upgrade_file(seed_sql: str) -> str:
    """The 20-line script for a database that already has everything older.

    Someone who pasted an earlier edition only needs the two tables that came
    with the newest features, plus a guarded ALTER for a column the old
    database_setup.sql forgot. Everything is IF NOT EXISTS / guarded, so
    running it on an up-to-date database changes nothing.
    """

    ddl = open(os.path.join(BASE_DIR, "pharmacy_setup.sql"), encoding="utf-8").read()
    ddl = "\n".join(ln for ln in ddl.splitlines() if not ln.strip().startswith("--"))
    tables = re.findall(r"(?m)^CREATE TABLE IF NOT EXISTS.*?COLLATE=utf8mb4_unicode_ci;",
                        ddl, re.S)
    if len(tables) != 12:
        raise SystemExit(f"expected 12 pharmacy CREATE TABLEs, got {len(tables)}")

    wanted = {}
    for stmt in tables:
        name = re.search(r"CREATE TABLE IF NOT EXISTS `(\w+)`", stmt).group(1)
        wanted[name] = stmt + "\n"
    if "doctor_patient_notes" not in wanted or "role_permissions" not in wanted:
        raise SystemExit("upgrade file needs doctor_patient_notes + role_permissions")

    login = next(ln for ln in seed_sql.splitlines()
                 if "superuser@sanjeevani.com" in ln and ln.startswith("INSERT IGNORE"))

    head = """-- ============================================================================
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

"""

    mid = """SET FOREIGN_KEY_CHECKS = 1;

-- ---------------------------------------------------------------------------
-- 3. the SUPERUSER login (INSERT IGNORE - skipped when the email already
--    exists, so your existing logins and passwords are never touched)
--    Password: Super@1234   ->   everything + the Access (role matrix) tab
-- ---------------------------------------------------------------------------
SELECT IF((SELECT COUNT(*) FROM information_schema.tables
            WHERE table_schema = 'sanjeevani_clinic' AND table_name = 'users') = 1,
          'users table found - the SUPERUSER row below is added if missing',
          'no users table - run database_setup_with_pharmacy.sql first') AS step_3;

"""

    tail = """
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
"""

    return (head
            + wanted["doctor_patient_notes"] + "\n"
            + wanted["role_permissions"] + "\n"
            + mid
            + login + "\n"
            + tail)


def build_standalone(seed_sql: str) -> str:
    """workbench_pharmacy.sql - only what the pharmacy needs, laid on top of a
    database that already has the clinic tables, and written so it also runs
    without errors on an empty one (the logins are guarded, and foreign key
    checks are off while the tables are created - the same trick mysqldump
    uses to keep statement order irrelevant)."""

    ddl = open(os.path.join(BASE_DIR, "pharmacy_setup.sql"), encoding="utf-8").read()
    ddl = "\n".join(line for line in ddl.splitlines()
                     if not line.strip().startswith("--"))
    tables = re.findall(r"(?m)^CREATE TABLE IF NOT EXISTS.*?COLLATE=utf8mb4_unicode_ci;",
                        ddl, re.S)
    if len(tables) != 12:
        raise SystemExit(f"expected 12 pharmacy CREATE TABLEs, got {len(tables)}")

    lines = list(STANDALONE_HEAD)
    lines.append("\n\n".join(table.strip() for table in tables))
    lines.append("SET FOREIGN_KEY_CHECKS = 1;")
    lines.extend(STANDALONE_LOGIN_HEAD)

    for statement in [ln for ln in seed_sql.splitlines()
                      if ln.startswith("INSERT IGNORE INTO `users`")]:
        # doubled single quotes, because the statement goes inside a SQL string
        inner = statement.rstrip(";").replace("'", "''")
        lines.append(
            "SET @sql := IF(@has_users = 1, '" + inner + "', 'SELECT 1');\n"
            "PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;"
        )

    lines.extend(STANDALONE_CHECKS)
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=os.path.join(BASE_DIR, "sanjeevani_clinic.db"))
    args = parser.parse_args()

    if not os.path.exists(args.db):
        print(f"!! demo database not found: {args.db}\n   run  python seed_pharmacy.py  first")
        return 1

    db = sqlite3.connect(args.db)
    db.row_factory = sqlite3.Row

    seed = build_seed(db)
    open(os.path.join(BASE_DIR, "pharmacy_seed.sql"), "w", encoding="utf-8").write(seed)

    standalone = build_standalone(seed)
    open(os.path.join(BASE_DIR, "workbench_pharmacy.sql"), "w",
         encoding="utf-8").write(standalone)

    combined = build_combined(seed)
    path = os.path.join(BASE_DIR, "database_setup_with_pharmacy.sql")
    open(path, "w", encoding="utf-8").write(combined)

    upgrade = build_upgrade_file(seed)
    open(os.path.join(BASE_DIR, "mysql_upgrade_existing_db.sql"), "w",
         encoding="utf-8").write(upgrade)

    everything = build_all_features_file(seed)
    open(os.path.join(BASE_DIR, "workbench_all_features.sql"), "w",
         encoding="utf-8").write(everything)

    print(f"pharmacy_seed.sql                 {len(seed):>8,} bytes")
    print(f"workbench_pharmacy.sql            {len(standalone):>8,} bytes  "
          f"({standalone.count(chr(10)) + 1} lines)")
    print(f"database_setup_with_pharmacy.sql  {len(combined):>8,} bytes  ({combined.count(chr(10))} lines)")
    active_drops = [ln for ln in combined.splitlines()
                    if re.match(r"^\s*(DROP|TRUNCATE)\b", ln, re.I)]
    print("real DROP/TRUNCATE statements:", len(active_drops) or "none")
    print("CREATE TABLE count:", len(re.findall(r"CREATE TABLE IF NOT EXISTS", combined)))
    print(f"mysql_upgrade_existing_db.sql     {len(upgrade):>8,} bytes  "
          f"({upgrade.count(chr(10))} lines)")
    bad = [ln for ln in upgrade.splitlines() if re.match(r"^\s*(DROP|TRUNCATE|DELETE|UPDATE)\b", ln, re.I)]
    print("upgrade file DROP/TRUNCATE/DELETE/UPDATE statements:", len(bad) or "none")
    print(f"workbench_all_features.sql        {len(everything):>8,} bytes  "
          f"({everything.count(chr(10))} lines)")
    print("workbench_all_features.sql CREATE TABLEs:",
          len(re.findall(r"(?m)^CREATE TABLE IF NOT EXISTS", everything)),
          "(anchored count; a header comment also contains the words)")
    bad = [ln for ln in everything.splitlines()
           if re.match(r"^\s*(DROP|TRUNCATE)\b", ln, re.I)]
    print("workbench_all_features.sql DROP/TRUNCATE statements:", len(bad) or "none")
    return 0


def build_all_features_file(seed_sql: str) -> str:
    """ONE file with everything: the 15 original clinic tables AND the 12 new
    pharmacy / doctor-desk tables, plus the logins and a combined verify grid.

    This is the file to paste when someone says "give me the complete updated
    SQL for all existing + new features". The 111-medicine catalogue is left to
    `python seed_pharmacy.py` on purpose (it is ~100 KB of INSERTs).
    """

    clinic = open(os.path.join(BASE_DIR, "database_setup.sql"), encoding="utf-8").read()

    # 1. never drop the database
    clinic, dropped = re.subn(r"(?im)^\s*DROP DATABASE[^;]*;\s*$\n?",
                              "", clinic)
    if not dropped:
        raise SystemExit("database_setup.sql has no DROP DATABASE line? adjust the generator")

    # 2. keep the clinic part from CREATE DATABASE ... up to (not incl.) its own
    #    verify grid, so the tail can be replaced by the combined one
    start = clinic.index("CREATE DATABASE sanjeevani_clinic")
    clinic_body = clinic[start:]
    clinic_body = re.sub(r"(?i)CREATE DATABASE sanjeevani_clinic",
                         "CREATE DATABASE IF NOT EXISTS sanjeevani_clinic",
                         clinic_body, count=1)
    end_marker = "-- 4. VERIFY - the last result grid should show these numbers"
    if end_marker not in clinic_body:
        raise SystemExit("database_setup.sql verify section moved? adjust the generator")
    clinic_body = clinic_body[:clinic_body.index(end_marker)].rstrip()
    # the cut leaves the section-4 banner comment behind: remove it
    clinic_body = re.sub(r"\n-- =+\s*$", "", clinic_body) + "\n"

    # 3. the 12 new tables
    ddl = open(os.path.join(BASE_DIR, "pharmacy_setup.sql"), encoding="utf-8").read()
    ddl = "\n".join(ln for ln in ddl.splitlines() if not ln.strip().startswith("--"))
    tables = re.findall(r"(?m)^CREATE TABLE IF NOT EXISTS.*?COLLATE=utf8mb4_unicode_ci;",
                        ddl, re.S)
    if len(tables) != 12:
        raise SystemExit(f"expected 12 pharmacy CREATE TABLEs, got {len(tables)}")

    # 4. the newest login rows (guarded prepared statements)
    logins = [ln for ln in seed_sql.splitlines()
              if ln.startswith("INSERT IGNORE") and "@demo.com" in ln
              or ln.startswith("INSERT IGNORE") and "@sanjeevani.com" in ln]

    head = """-- ============================================================================
--  SANJEEVANI CLINIC - COMPLETE DATABASE: ALL EXISTING + ALL NEW FEATURES
--  (MySQL / MySQL Workbench)                                         27 TABLES
-- ============================================================================
--
--  ONE script for the whole project, old and new:
--
--     15 original clinic tables   users, doctors, doctor_slots, doctor_schedules,
--                                 visit_types, appointments, medical_records,
--                                 treatments, follow_ups, prescriptions,
--                                 prescription_medicines, treatment_reviews,
--                                 notifications, screening_history,
--                                 patient_documents
--     12 new module tables        diseases, medicines, medicine_diseases,
--                                 pharmacy_cart_items, nearby_pharmacies,
--                                 nearby_pharmacy_stocks, pharmacy_snapshots,
--                                 pharmacy_orders, pharmacy_order_items,
--                                 pharmacy_audit_logs, role_permissions,
--                                 doctor_patient_notes
--
--  WHAT IS SAFE ABOUT THIS FILE
--  ----------------------------
--   * NO DROP DATABASE and NO DROP TABLE anywhere. Your appointments,
--     medical_records, follow_ups and uploaded reports are never deleted.
--   * every table is CREATE TABLE IF NOT EXISTS and every seed row is
--     INSERT IGNORE / WHERE NOT EXISTS, so pasting it twice is harmless
--     (the second run reports "0 rows affected").
--   * it also fixes the one column the ORIGINAL database_setup.sql was missing
--     (treatment_reviews.updated_at) with a guarded ALTER, so an older database
--     that was created from that file still ends up complete.
--
--  HOW TO USE
--  ----------
--    1. MySQL Workbench -> File -> Open SQL Script -> this file
--    2. Ctrl+Shift+Enter  ("Execute all statements")
--    3. The grids at the end tell you what is present right now: total
--       tables (27), the 12 module tables, the doctor-desk + role-matrix
--       tables, treatment_reviews.updated_at, doctors/schedules/visit types,
--       a "logins by role" count and the medicine catalogue count.
--
--  THE MEDICINE CATALOGUE
--  ----------------------
--    The 111 medicines / 32 diseases / partner chemists are NOT in this file
--    (that INSERT block is ~100 KB). Load them with ONE command from the
--    project folder:
--        python seed_pharmacy.py
--    It is re-runnable and also makes the pinned rollback snapshot the
--    pharmacy console uses.
--
--  Generated by  python build_workbench_sql.py  - edit that, not this file.
-- ============================================================================

"""

    mid = """

-- ============================================================================
--  NEW FEATURES - the 12 module tables
--  (pharmacy shop / cart / orders, nearby chemists, audit + snapshots,
--   the role matrix and the doctor desk notes)
--  FOREIGN_KEY_CHECKS off so this block also works on a database that is
--  still missing some clinic table; the relations are still declared.
-- ============================================================================

SET FOREIGN_KEY_CHECKS = 0;

"""

    login_head = """
SET FOREIGN_KEY_CHECKS = 1;

-- ---------------------------------------------------------------------------
--  the new logins (INSERT IGNORE: an existing email is never overwritten, so
--  your own passwords and users stay exactly as they are)
--    superuser@sanjeevani.com  Super@1234    everything + the Access tab
--    admin@demo.com            Admin@1234
--    pharmacist@demo.com       Pharma@1234
--    doctor@demo.com           Doctor@1234   -> lands on /doctor-desk
--    patient@demo.com          Demo@1234
-- ---------------------------------------------------------------------------
SELECT IF((SELECT COUNT(*) FROM information_schema.tables
            WHERE table_schema = 'sanjeevani_clinic' AND table_name = 'users') = 1,
          'users table found - the demo logins below are added if missing',
          'no users table yet - run the clinic part of this file first') AS step_logins;

"""

    tail = """
-- ============================================================================
--  VERIFY - every line should read "present" / the expected number
-- ============================================================================
SELECT TABLE_NAME AS table_name, TABLE_ROWS AS approx_rows
FROM information_schema.tables
WHERE table_schema = 'sanjeevani_clinic'
ORDER BY TABLE_NAME;

SELECT 'tables in total' AS what,
       CONCAT(COUNT(*), ' (expect 27 = 15 clinic + 12 module)') AS status
  FROM information_schema.tables WHERE table_schema = 'sanjeevani_clinic'
UNION ALL
SELECT 'module tables found',
       CONCAT(COUNT(*), ' (expect 12)')
  FROM information_schema.tables
 WHERE table_schema = 'sanjeevani_clinic'
   AND table_name IN ('diseases','medicines','medicine_diseases','pharmacy_cart_items',
                      'nearby_pharmacies','nearby_pharmacy_stocks','pharmacy_snapshots',
                      'pharmacy_orders','pharmacy_order_items','pharmacy_audit_logs',
                      'role_permissions','doctor_patient_notes')
UNION ALL
SELECT 'doctor_patient_notes (doctor desk)',
       IF(COUNT(*) = 1, 'present', 'MISSING')
  FROM information_schema.tables
 WHERE table_schema = 'sanjeevani_clinic' AND table_name = 'doctor_patient_notes'
UNION ALL
SELECT 'role_permissions (SUPERUSER access tab)',
       IF(COUNT(*) = 1, 'present', 'MISSING')
  FROM information_schema.tables
 WHERE table_schema = 'sanjeevani_clinic' AND table_name = 'role_permissions'
UNION ALL
SELECT 'treatment_reviews.updated_at',
       IF(COUNT(*) = 1, 'present', 'MISSING - re-run this file')
  FROM information_schema.columns
 WHERE table_schema = 'sanjeevani_clinic' AND table_name = 'treatment_reviews'
   AND column_name = 'updated_at'
UNION ALL
SELECT 'doctors / schedules / visit types',
       CONCAT((SELECT COUNT(*) FROM doctors), ' doctors, ',
              (SELECT COUNT(*) FROM doctor_schedules), ' schedules, ',
              (SELECT COUNT(*) FROM visit_types), ' visit types')
UNION ALL
SELECT 'logins by role',
       CONCAT('PATIENT ', (SELECT COUNT(*) FROM users WHERE role = 'PATIENT'),
              ' | DOCTOR ', (SELECT COUNT(*) FROM users WHERE role = 'DOCTOR'),
              ' | PHARMACIST ', (SELECT COUNT(*) FROM users WHERE role = 'PHARMACIST'),
              ' | ADMIN ', (SELECT COUNT(*) FROM users WHERE role = 'ADMIN'),
              ' | SUPERUSER ', (SELECT COUNT(*) FROM users WHERE role = 'SUPERUSER'))
UNION ALL
SELECT 'catalogue (medicines)',
       CONCAT((SELECT COUNT(*) FROM medicines), ' - run "python seed_pharmacy.py" for the 111');
"""

    return (head + clinic_body + "\n\n" + mid + "\n\n".join(tables)
            + "\n\n" + login_head + "\n".join(logins) + "\n" + tail)


if __name__ == "__main__":
    sys.exit(main())
