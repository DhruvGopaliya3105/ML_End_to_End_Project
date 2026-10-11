"""
test_pharmacy_mysql.py - runs the pharmacy against your REAL MySQL database.

The rest of the test suite (test_pharmacy.py) deliberately uses a throwaway
SQLite file so it can never touch your data. This one is the opposite: it uses
exactly the .env settings your app uses, so it proves the MySQL path works on
your machine - tables, seed data, purchase, stock, refund, audit log, rollback.

    python test_pharmacy_mysql.py            # uses .env
    python test_pharmacy_mysql.py --dry-run  # only checks connectivity + tables

If MySQL cannot be reached the script prints SKIP and exits 0, so it never
breaks a demo. It writes into the database you point .env at (a demo order and
a demo medicine), so run it on your development database.
"""

from __future__ import annotations

import argparse
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

PASSED: list[str] = []
FAILED: list[str] = []


def check(label: str, condition, detail: str = "") -> bool:
    ok = bool(condition)
    (PASSED if ok else FAILED).append(label)
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{f'  ({detail})' if detail and not ok else ''}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    # --- 1. can we reach MySQL with the app's own settings? ---------------
    from src.database.connection import DATABASE_BACKEND, DATABASE_LABEL, engine

    print(f"Database the app would use: {DATABASE_LABEL}")

    if DATABASE_BACKEND != "mysql":
        print("\nSKIP - .env is not pointing at MySQL (USE_SQLITE is on, or MySQL")
        print("settings are incomplete). Set DB_USER/DB_PASSWORD/DB_HOST/DB_NAME in")
        print(".env and USE_SQLITE=false, then run this again.\n")
        return 0

    from sqlalchemy.exc import SQLAlchemyError

    try:
        with engine.connect() as probe:
            probe.exec_driver_sql("SELECT 1")
    except SQLAlchemyError as exc:
        print(f"\nSKIP - MySQL not reachable: {str(exc).splitlines()[0]}\n")
        return 0

    from sqlalchemy import inspect

    names = set(inspect(engine).get_table_names())
    expected = {
        "users", "doctors", "appointments",
        "diseases", "medicines", "medicine_diseases", "pharmacy_cart_items",
        "pharmacy_orders", "pharmacy_order_items", "nearby_pharmacies",
        "nearby_pharmacy_stocks", "pharmacy_snapshots", "pharmacy_audit_logs",
        "role_permissions",
        "medical_records", "follow_ups", "treatments",
        "treatment_reviews", "doctor_patient_notes",
    }
    check("all pharmacy + clinic + doctor desk tables exist", expected <= names,
          f"missing {sorted(expected - names)}")
    check("27 tables in this database", len(names) >= 27, f"found {len(names)}")

    if args.dry_run:
        print(f"\n{len(PASSED)} checks passed, {len(FAILED)} failed (dry run)")
        return 1 if FAILED else 0

    # --- 2. is the SQL seed data visible to the app? -----------------------
    from src.models.medicine import Medicine
    from src.models.disease import Disease
    from src.models.user import User
    from src.database.connection import SessionLocal

    db = SessionLocal()
    try:
        medicines = db.query(Medicine).count()
        diseases = db.query(Disease).count()
        check("catalog loaded from MySQL", medicines > 0, f"{medicines} medicines")
        check("disease list loaded", diseases > 0, f"{diseases} diseases")

        super_user = db.query(User).filter(User.email == "superuser@sanjeevani.com").first()
        check("super user exists in MySQL", super_user is not None
              and (super_user.role or "").upper() == "SUPERUSER")

        if medicines == 0 or super_user is None:
            print("\n  Tip: run  python seed_pharmacy.py  (or import pharmacy_seed.sql)")
            print("  in MySQL Workbench, then re-run this script.\n")
            return 1
    finally:
        db.close()

    # --- 3. the app, over HTTP, on MySQL ---------------------------------
    from fastapi.testclient import TestClient
    from main import app

    print("\n=== the app on MySQL ===")
    with TestClient(app) as client:
        page = client.get("/pharmacy")
        check("GET /pharmacy renders", page.status_code == 200, f"status {page.status_code}")
        check("medicine cards are on the page", "Rs" in page.text)

        api = client.get("/pharmacy/api/medicines", params={"q": "dolo"})
        rows = api.json().get("results", []) if api.status_code == 200 else []
        check("search API answers from MySQL", bool(rows), f"status {api.status_code}")

        target = db = None
        from src.database.connection import SessionLocal as SL
        db = SL()
        try:
            target = (
                db.query(Medicine)
                .filter(Medicine.requires_prescription.is_(False),
                        Medicine.stock > 5)
                .order_by(Medicine.price.asc())
                .first()
            )
            stock_before = target.stock
            price = float(target.price)
            target_id = target.id
        finally:
            db.close()

        # patient buys one pack
        login = client.post("/login", data={"email": "patient@demo.com",
                                           "password": "Demo@1234"},
                            follow_redirects=False)
        check("patient can log in against MySQL", login.status_code in (200, 303),
              f"status {login.status_code}")

        added = client.post("/pharmacy/api/cart/add",
                            data={"medicine_id": target_id, "quantity": 1})
        check("add to cart", added.status_code == 200, added.text[:120])

        checkout = client.post("/pharmacy/api/checkout",
                               data={"payment_method": "CASH",
                                     "delivery_type": "PICKUP",
                                     "phone": "9999900000"})
        order = checkout.json() if checkout.status_code == 200 else {}
        check("checkout creates a CONFIRMED order",
              checkout.status_code == 200 and order.get("status") == "CONFIRMED",
              f"{checkout.status_code} {checkout.text[:140]}")
        check("order number looks like PH-YYYYMMDD-####",
              str(order.get("order_no", "")).startswith("PH-"), order.get("order_no"))

        db = SL()
        try:
            fresh = db.get(Medicine, target_id)
            check("stock moved in MySQL", int(fresh.stock) == stock_before - 1,
                  f"{stock_before} -> {fresh.stock}")
        finally:
            db.close()

        order_id = order.get("order_id") or order.get("id")
        cancelled = client.post(f"/pharmacy/api/order/{order_id}/cancel",
                                data={"reason": "mysql smoke test cleanup"})
        check("patient can cancel it again", cancelled.status_code == 200,
              cancelled.text[:120])

        db = SL()
        try:
            fresh = db.get(Medicine, target_id)
            check("stock came back after cancel", int(fresh.stock) == stock_before,
                  f"now {fresh.stock}")
        finally:
            db.close()

        # nearby + admin + audit + rollback
        nearby = client.get("/pharmacy/nearby", params={"name": "Dolo"})
        check("nearby page works", nearby.status_code == 200, f"status {nearby.status_code}")

        admin_login = client.post("/login", data={"email": "superuser@sanjeevani.com",
                                                  "password": "Super@1234"},
                                  follow_redirects=False)
        check("super user can log in", admin_login.status_code in (200, 303))

        for tab in ("orders", "catalog", "nearby", "audit", "access", "snapshots"):
            res = client.get("/pharmacy/admin", params={"tab": tab})
            check(f"admin tab '{tab}'", res.status_code == 200, f"status {res.status_code}")

        # --- the doctor desk, over the same MySQL connection --------------
        doctor_login = client.post("/login", data={"email": "doctor@demo.com",
                                                   "password": "Doctor@1234"},
                                   follow_redirects=False)
        check("doctor login lands on the desk",
              doctor_login.status_code in (200, 303)
              and "doctor-desk" in (doctor_login.headers.get("location") or ""),
              doctor_login.headers.get("location", ""))

        roster = client.get("/doctor-desk")
        check("doctor desk roster renders", roster.status_code == 200,
              f"status {roster.status_code}")
        check("roster shows the signed-in doctor", "Vikram" in roster.text)

        tiles = client.get("/doctor-desk/api/summary")
        check("desk tiles API answers",
              tiles.status_code == 200 and tiles.json()["success"], tiles.text[:120])

        listed = client.get("/doctor-desk/api/patients")
        rows = listed.json().get("rows", []) if listed.status_code == 200 else []
        check("patient roster API returns rows", bool(rows), f"{len(rows)} rows")

        if rows:
            pid = rows[0]["id"]

            for tab in ("overview", "visits", "records", "prescriptions",
                        "medicines", "billing", "notes", "reviews",
                        "documents", "timeline"):
                res = client.get(f"/doctor-desk/patient/{pid}", params={"tab": tab})
                check(f"patient file tab '{tab}'", res.status_code == 200,
                      f"status {res.status_code}")

            statement = client.get(f"/doctor-desk/patient/{pid}/statement")
            check("printable statement renders", statement.status_code == 200,
                  f"status {statement.status_code}")

            note = client.post(f"/doctor-desk/patient/{pid}/notes",
                               data={"title": "MySQL desk check",
                                     "body": "Written through the doctor desk on MySQL.",
                                     "note_type": "NOTE"},
                               follow_redirects=False)
            check("doctor can save a note on MySQL", note.status_code == 303,
                  f"status {note.status_code}")

            from src.models.doctor_patient_note import DoctorPatientNote
            from src.database.connection import SessionLocal as _SL

            _db = _SL()
            try:
                saved = (_db.query(DoctorPatientNote)
                         .filter(DoctorPatientNote.title == "MySQL desk check")
                         .order_by(DoctorPatientNote.id.desc())
                         .first())
                check("note row landed in MySQL", saved is not None)

                if saved is not None:
                    flip = client.post(f"/doctor-desk/notes/{saved.id}/flag",
                                       data={"field": "urgent"},
                                       headers={"Accept": "application/json"})
                    check("note flag round-trips",
                          flip.status_code == 200
                          and flip.json().get("is_urgent") is True, flip.text[:120])

                    clean = client.post(f"/doctor-desk/notes/{saved.id}/flag",
                                        data={"field": "archive"},
                                        headers={"Accept": "application/json"})
                    check("test note archived again", clean.status_code == 200,
                          clean.text[:120])

                    # MySQL works in REPEATABLE READ: this session must end its
                    # transaction before it can see the commit the app made
                    # through a different connection.
                    _db.rollback()
                    _db.expire_all()
                    kept = _db.get(DoctorPatientNote, saved.id)
                    check("archive keeps the row (soft delete)",
                          kept is not None and kept.status == "ARCHIVED")
            finally:
                _db.close()

        from fastapi.testclient import TestClient as _TC
        from main import app as _app

        with _TC(_app) as guest:
            anon = guest.get("/doctor-desk", follow_redirects=False)
            check("the desk is not public",
                  anon.status_code == 303
                  and "/login" in (anon.headers.get("location") or ""),
                  f"{anon.status_code} {anon.headers.get('location', '')}")

        client.post("/login", data={"email": "patient@demo.com",
                                   "password": "Demo@1234"},
                    follow_redirects=False)
        bounced = client.get("/doctor-desk", follow_redirects=False)
        check("a patient cannot open the desk",
              bounced.status_code == 303
              and "/doctor-desk" not in (bounced.headers.get("location") or ""),
              f"{bounced.status_code} {bounced.headers.get('location', '')}")

        client.post("/login", data={"email": "superuser@sanjeevani.com",
                                    "password": "Super@1234"},
                    follow_redirects=False)

        audit = client.get("/pharmacy/admin/api/audit", params={"limit": 5})
        logs = audit.json().get("logs", []) if audit.status_code == 200 else []
        check("audit log rows written to MySQL", len(logs) > 0, f"{len(logs)} rows")

        snap = client.post("/pharmacy/admin/api/snapshots",
                           data={"scope": "CATALOG", "label": "mysql smoke point"})
        check("snapshot created", snap.status_code == 200, snap.text[:120])
        body = snap.json()
        snap_id = (body.get("snapshot") or {}).get("id") or body.get("id")

        old_price = price
        bump = client.post("/pharmacy/admin/api/catalog/bulk-price",
                           data={"percent": "1", "confirm": "yes"})
        check("bulk price change ran", bump.status_code == 200, bump.text[:120])

        preview = client.get(f"/pharmacy/admin/api/snapshots/{snap_id}/preview")
        checksum = ""
        if preview.status_code == 200 and snap_id:
            payload = preview.json().get("preview") or {}
            checksum = payload.get("checksum", "")
        check("preview gives a checksum", bool(checksum), preview.text[:120])

        restore = client.post(f"/pharmacy/admin/api/snapshots/{snap_id}/restore",
                              data={"checksum": checksum})
        check("restore accepted", restore.status_code == 200, restore.text[:160])

        db = SL()
        try:
            back = db.get(Medicine, target_id)
            check("price rolled back in MySQL",
                  abs(float(back.price) - old_price) < 0.011,
                  f"{old_price} -> {back.price}")
        finally:
            db.close()

    print("\n" + "-" * 62)
    print(f"{len(PASSED)} checks passed, {len(FAILED)} failed   [{DATABASE_LABEL}]")
    if FAILED:
        for label in FAILED:
            print(f"   failed: {label}")
        return 1
    print("MySQL path verified - the pharmacy really runs on your database.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
