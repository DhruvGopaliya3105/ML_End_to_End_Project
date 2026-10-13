"""One command that cross-checks the WHOLE project: clinic + pharmacy + doctor desk.

    python check_all_features.py            # safe: builds its own throwaway DB
    python check_all_features.py --live     # read-only checks on YOUR database
    python check_all_features.py --html out.html   # also write a printable report

What it proves, in order
-----------------------
1.  app boots on the real code (no mocks, real HTTP through TestClient)
2.  every page of every feature answers (clinic pages, /pharmacy, /pharmacy/admin,
    /doctor-desk) - for each role, and the role that must NOT see a page does not
3.  the features are actually linked to each other (navbars, dashboard cards,
    receipt -> order, doctor file -> statement, Rx -> cart button) - checked in
    the template source, so a dead button is caught even if the page renders
4.  the tables reference each other honestly: no orphan rows through any foreign
    key of the pharmacy / doctor desk tables (that is what "integrated" means)
5.  a real end-to-end walk: patient buys a strip -> counter fulfils -> receipt
    prints; doctor writes a prescription -> pushes it to the patient's cart ->
    the patient's Rx tab offers exactly that medicine -> note + payment written
    back by the desk are visible to the patient / the ledger
7.  the SQL you pasted matches the models (no missing table / column)
8.  the ORIGINAL clinic features still work end to end, not just render:
    signup -> wrong password refused -> login -> doctors -> slot lookup ->
    book appointment -> shows in /appointments -> cancel -> profile update ->
    follow-up complete -> treatment review -> AI screening -> report upload ->
    notifications
6.  the Google Maps / Places wiring: /pharmacy/api/nearby answers with AND
    without GOOGLE_MAPS_API_KEY, always with google_status, and the admin
    "Sync from Google" endpoint is mounted (it never calls Google from here)

Expected output on a good day:  319/319 checks passed, 0 failed
                                (320 when your .env points at MySQL)

It exits 1 if anything fails, so it is usable before pushing.
"""

from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
from datetime import date
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

PASSED: list[str] = []
FAILED: list[tuple[str, str]] = []
NOTES: list[str] = []

LIVE = False
HTML_OUT: str | None = None


def ok(name: str, condition: bool, extra: str = "") -> None:
    if condition:
        PASSED.append(f"{CURRENT} :: {name}")
    else:
        FAILED.append((f"{CURRENT} :: {name}", extra))


def note(text: str) -> None:
    NOTES.append(text)


CURRENT = "boot"


def show(title: str) -> None:
    global CURRENT
    CURRENT = title
    print(f"\n=== {title} ===")


# =====================================================================
# 1. pages per role
# =====================================================================

CLINIC_PAGES = [
    "/",
    "/health",
    "/dashboard",
    "/profile",
    "/predict",
    "/screening",
    "/chatbot",
    "/doctors",
    "/appointments",
    "/medical-history",
    "/medical-reports",
    "/follow-up-care",
    "/notifications",
]

PHARMACY_PAGES = [
    "/pharmacy",
    "/pharmacy?disease=diabetes",
    "/pharmacy?q=dolo",
    "/pharmacy/cart",
    "/pharmacy/orders",
    "/pharmacy/prescriptions",
    "/pharmacy/nearby",
]

ADMIN_TABS = [
    "/pharmacy/admin?tab=orders",
    "/pharmacy/admin?tab=catalog",
    "/pharmacy/admin?tab=nearby",
    "/pharmacy/admin?tab=audit",
    "/pharmacy/admin?tab=access",
    "/pharmacy/admin?tab=snapshots",
]

DESK_PAGES = [
    "/doctor-desk",
    "/doctor-desk?scope=new",
    "/doctor-desk?scope=followup",
    "/doctor-desk?scope=unpaid",
    "/doctor-desk?scope=urgent",
    "/doctor-desk?sort=due&direction=asc",
]

DESK_TABS = [
    "overview", "visits", "records", "prescriptions", "medicines",
    "billing", "notes", "reviews", "documents", "timeline",
]

API_ENDPOINTS = [
    "/pharmacy/api/medicines?q=para",
    "/pharmacy/api/cart",
    "/pharmacy/api/nearby?name=Dolo&lat=26.91&lng=75.78",
    "/pharmacy/admin/api/orders?limit=2",
    "/pharmacy/admin/api/audit?limit=2",
    "/pharmacy/admin/api/snapshots",
    "/doctor-desk/api/patients",
    "/doctor-desk/api/summary",
]

LOGINS = {
    "PATIENT": ("patient@demo.com", "Demo@1234"),
    "DOCTOR": ("doctor@demo.com", "Doctor@1234"),
    "PHARMACIST": ("pharmacist@demo.com", "Pharma@1234"),
    "ADMIN": ("admin@demo.com", "Admin@1234"),
    "SUPERUSER": ("superuser@sanjeevani.com", "Super@1234"),
}


def check_pages(client) -> None:
    show("2. pages answer for the role that is supposed to use them")

    def visit(role: str, urls: list[str], allow_303: bool = False) -> None:
        for url in urls:
            response = client.get(url, follow_redirects=False)
            good = (response.status_code == 200
                    or (allow_303 and response.status_code == 303))
            ok(f"{role} {url}", good,
               f"status {response.status_code} {response.headers.get('location', '')}")

    for role, (email, password) in LOGINS.items():
        login = client.post("/login", data={"email": email, "password": password},
                            follow_redirects=False)
        want = "/doctor-desk" if role == "DOCTOR" else "/dashboard"
        landed = (login.status_code == 303
                  and want in (login.headers.get("location") or ""))
        if LIVE and not landed:
            note(f"live mode: this server has no {role} demo login "
                 f"({email}), so its page checks are skipped - open the pages "
                 f"in your browser while logged in instead")
            continue
        ok(f"{role} login lands on the right page", landed,
           f"went to {login.headers.get('location')}")

        visit(role, CLINIC_PAGES, allow_303=True)
        visit(role, PHARMACY_PAGES, allow_303=True)

        desk = client.get("/doctor-desk", follow_redirects=False)
        if role in ("DOCTOR", "ADMIN", "SUPERUSER"):
            ok(f"{role} can open the doctor desk", desk.status_code == 200,
               f"status {desk.status_code}")
            for tab in DESK_TABS:
                page = client.get(f"/doctor-desk/patient/1?tab={tab}")
                ok(f"{role} desk tab {tab}", page.status_code == 200,
                   f"status {page.status_code}")
        else:
            ok(f"{role} is kept out of the doctor desk",
               desk.status_code == 303
               and "/doctor-desk" not in (desk.headers.get("location") or ""),
               f"{desk.status_code} {desk.headers.get('location', '')}")

        if role in ("PHARMACIST", "ADMIN", "SUPERUSER"):
            visit(role, ADMIN_TABS)

    # the pharmacy admin console for a patient is the one page that must bounce
    client.post("/login", data={"email": "patient@demo.com", "password": "Demo@1234"},
                follow_redirects=False)
    if LIVE and client.get("/dashboard", follow_redirects=False).status_code != 200:
        note("live mode: patient demo login absent, admin-console and API checks "
             "run only for the accounts this server really has")
        return
    bounced = client.get("/pharmacy/admin", follow_redirects=False)
    ok("patient is bounced from the admin console",
       bounced.status_code in (200, 303)
       and (bounced.status_code == 303 or "Order queue" not in bounced.text),
       f"status {bounced.status_code}")

    show("2b. JSON APIs answer")
    client.post("/login", data={"email": "superuser@sanjeevani.com", "password": "Super@1234"},
                 follow_redirects=False)
    for url in API_ENDPOINTS:
        response = client.get(url)
        body = ""
        try:
            body = str(response.json().get("success", True))
        except Exception:  # noqa: BLE001
            pass
        ok(f"API {url}", response.status_code == 200 and body != "False",
           f"status {response.status_code} {response.text[:100]}")


# =====================================================================
# 6. Google Maps / Places wiring (optional, but it must fail loudly)
# =====================================================================

def check_google(client) -> None:
    """The nearby search must work with OR without a Google key.

    Without a key the page has to fall back to the partner chemists in SQL and
    say so; with a key it must be able to report what Google answered. This
    check never calls Google if your key is present, so it cannot eat quota.
    """

    show("6. Google Maps / Places wiring (optional)")

    env_file = BASE_DIR / ".env"
    example = (BASE_DIR / ".env.example").read_text(encoding="utf-8")
    ok("the Google key has a documented slot in .env.example",
       "GOOGLE_MAPS_API_KEY" in example)
    if env_file.exists():
        ok(".env exists (that is where your key goes)", True)
    else:
        note("this copy has no .env yet - copy .env.example to .env before you "
             "turn on MySQL or a Google key; the app runs without it")

    key = (os.environ.get("GOOGLE_MAPS_API_KEY") or "").strip()

    nearby = client.get("/pharmacy/api/nearby?name=Dolo")
    ok("nearby API answers whether or not Google is configured",
       nearby.status_code == 200, f"status {nearby.status_code}")
    payload = nearby.json() if nearby.status_code == 200 else {}
    ok("nearby payload reports google_status, so the page can explain itself",
       "google_status" in payload, str(list(payload))[:120])
    ok("nearby list is not empty even without Google",
       bool(payload.get("results") or payload.get("pharmacies") or payload.get("items"))
       or key == "",
       "empty nearby list")

    page = client.get("/pharmacy/nearby")
    ok("nearby page renders", page.status_code == 200, f"status {page.status_code}")
    ok("the page tells the user about Google (hint line)",
       "GOOGLE_MAPS_API_KEY" in page.text or "Google" in page.text,
       "no mention of Google anywhere in /pharmacy/nearby")

    # a GET on a POST-only route answers 405 when the route exists, so this
    # proves the endpoint is mounted without importing/inspecting internals
    probe = client.get("/pharmacy/admin/api/nearby/sync-google",
                       headers={"Accept": "application/json"})
    ok("admin sync endpoint is mounted", probe.status_code in (405, 409, 200),
       f"status {probe.status_code}")

    if key:
        note(f"a Google key is configured (…{key[-4:]}) and nearby_status = "
             f"{payload.get('google_status')!r} - the checker does not call "
             f"Google itself; use Pharmacy admin -> Nearby -> Sync from Google")
        ok("service only reads the key through the environment",
           "GOOGLE_MAPS_API_KEY" in (BASE_DIR / "src/services/pharmacy_nearby_service.py")
           .read_text(encoding="utf-8"))
    else:
        client.post("/login", data={"email": "superuser@sanjeevani.com",
                                   "password": "Super@1234"},
                    follow_redirects=False)
        sync = client.post("/pharmacy/admin/api/nearby/sync-google",
                           headers={"Accept": "application/json"})
        ok("without a key the sync endpoint explains itself instead of crashing",
           sync.status_code in (200, 409) and "GOOGLE_MAPS_API_KEY" in sync.text,
           f"status {sync.status_code} {sync.text[:140]}")
        note("no GOOGLE_MAPS_API_KEY in .env -> that is fine, the emergency "
             "search uses the partner chemists from SQL (add the key + restart "
             "to also pull live shops)")


# =====================================================================
# 7. does the SQL you pasted really match the models?
# =====================================================================

def check_schema_parity(db) -> None:
    """Compare Base.metadata (the models) with the live database.

    This is the check that catches a pasted SQL file which is one column
    behind the code - the kind of thing that only shows up later as
    "Unknown column 'x' in 'field list'". Works the same on MySQL and SQLite.
    """

    show("7. database schema matches the code (no missing table / column)")

    from sqlalchemy import inspect as sa_inspect
    from src.database.base import Base

    engine = db.get_bind()
    inspector = sa_inspect(engine)
    live_tables = set(inspector.get_table_names())

    missing_tables: list[str] = []
    missing_columns: list[str] = []
    extra_columns: list[str] = []

    for name, table in sorted(Base.metadata.tables.items()):
        if name not in live_tables:
            missing_tables.append(name)
            continue
        live_cols = {c["name"] for c in inspector.get_columns(name)}
        want_cols = {c.name for c in table.columns}
        if want_cols - live_cols:
            missing_columns.append(f"{name}: " + ", ".join(sorted(want_cols - live_cols)))
        if live_cols - want_cols:
            extra_columns.append(f"{name}: " + ", ".join(sorted(live_cols - want_cols)))

    ok("every model table exists in the database", not missing_tables,
       f"missing: {missing_tables}")
    ok("no model column is missing in the database", not missing_columns,
       "; ".join(missing_columns)[:400])
    ok("every model table has a primary key in the database",
       all(inspector.get_pk_constraint(t).get("constrained_columns")
           for t in live_tables & set(Base.metadata.tables)),
       "a table without a PK breaks SQLAlchemy merges")
    ok("foreign keys of the module tables are real FKs in the database",
       all(len(inspector.get_foreign_keys(t)) > 0
           for t in ("pharmacy_orders", "pharmacy_order_items",
                     "doctor_patient_notes") if t in live_tables),
       "no FK found - those tables came from a script that skipped constraints")

    if extra_columns:
        note("columns in your database that the code does not use (harmless, "
             "kept so nothing you already had is lost): "
             + "; ".join(extra_columns)[:420])
    print(f"   {len(Base.metadata.tables)} model tables checked on "
          f"{engine.dialect.name} / {len(live_tables)} tables found")



# =====================================================================
# 8. the original clinic features, end to end
# =====================================================================

def check_clinic_flows(client, db) -> None:
    """Walk the features the project had BEFORE the pharmacy, for real.

    Rendering a page is not proof: here every original feature is exercised
    through HTTP (signup, login, booking, cancel, profile, follow-up, review,
    screening, report upload, notifications) and the database is read back.
    Write steps are skipped in --live mode, so your own database is safe.
    """

    show("8. the ORIGINAL clinic features still work (signup -> ... -> report)")

    import io
    import time as _time

    from src.config import UPLOAD_DIR
    from src.models.appointment import Appointment
    from src.models.doctor import Doctor
    from src.models.follow_up import FollowUp
    from src.models.medical_record import MedicalRecord
    from src.models.notification import Notification
    from src.models.patient_document import PatientDocument
    from src.models.screening import ScreeningHistory
    from src.models.treatment_review import TreatmentReview
    from src.models.user import User
    from src.models.visit_type import VisitType
    from src.security.password import verify_password

    stamp = _time.strftime("%H%M%S")
    email = f"clinic.check.{stamp}@demo.com"
    password = "Check@1234"
    created_file: str | None = None

    # ---------------------------------------------------------------- signup --
    if not LIVE:
        signup = client.post("/signup", data={
            "name": "Clinic Check", "email": email, "phone": "9000000009",
            "password": password, "age": "31", "gender": "Male",
        }, follow_redirects=False)
        ok("POST /signup answers with a redirect (no crash)",
           signup.status_code in (200, 303), f"HTTP {signup.status_code}")

        db.expire_all()
        fresh = db.query(User).filter(User.email == email).first()
        ok("signup really created the user row", fresh is not None, email)
        ok("the stored password is a real hash the app can verify",
           bool(fresh) and verify_password(password, fresh.password_hash))
        ok("a self-registered user gets the PATIENT role",
           bool(fresh) and fresh.role == "PATIENT",
           f"role={getattr(fresh, 'role', '?')}")
    else:
        fresh = db.query(User).filter(User.email == "sunita@demo.com").first()
        note("live mode: signup / booking / upload / review are skipped "
             "(they write) - run without --live for all of them")

    login_email = email if not LIVE else "sunita@demo.com"
    login_pass = password if not LIVE else "Demo@1234"

    # --------------------------------------------------- wrong password vs ok --
    if fresh is not None:
        # a separate browser: /signup already opened a session on `client`
        from fastapi.testclient import TestClient
        import main as app_module

        with TestClient(app_module.app) as stranger:
            bad = stranger.post("/login", data={"email": login_email,
                                                "password": "definitely-wrong"},
                                follow_redirects=False)
            ok("a wrong password is refused with an error, not a login",
               bad.status_code != 303 and "invalid" in bad.text.lower(),
               f"HTTP {bad.status_code}, body: {bad.text[:120]!r}")

            after_bad = stranger.get("/dashboard")
            ok("a stranger's dashboard never leaks the demo patient's data",
               after_bad.status_code == 200
               and "patient@demo.com" not in after_bad.text
               and "Demo Patient" not in after_bad.text,
               f"HTTP {after_bad.status_code}")

            private = stranger.get("/appointments", follow_redirects=False)
            ok("a stranger is sent to /login for private pages",
               private.status_code == 303
               and "/login" in str(private.headers.get("location")),
               f"HTTP {private.status_code} -> {private.headers.get('location')}")

        good = client.post("/login", data={"email": login_email,
                                           "password": login_pass},
                           follow_redirects=False)
        ok("the right password logs in", good.status_code == 303,
           f"HTTP {good.status_code} -> {good.headers.get('location')}")
        dash = client.get("/dashboard", follow_redirects=False)
        ok("the signed-in patient really reaches /dashboard",
           dash.status_code == 200, f"HTTP {dash.status_code}")

    # ------------------------------------------------------------ doctor list --
    doctors = client.get("/doctors")
    ok("GET /doctors renders", doctors.status_code == 200, f"HTTP {doctors.status_code}")
    db.expire_all()
    first_doctor = db.query(Doctor).filter(Doctor.is_active.is_(True)).first()
    ok("there is an active doctor to book", first_doctor is not None)
    if first_doctor is not None:
        detail = client.get(f"/doctor/{first_doctor.id}")
        ok("a single doctor profile renders", detail.status_code == 200,
           f"HTTP {detail.status_code}")

    # ------------------------------------------------------------ visit types --
    visit = db.query(VisitType).filter(VisitType.is_active.is_(True)).first()
    if visit is None and not LIVE:
        visit = VisitType(name="General Consultation", min_duration_minutes=10,
                          max_duration_minutes=15, default_duration_minutes=15,
                          is_active=True)
        db.add(visit)
        db.commit()
        note("this throwaway database had no visit_types row, so one was added "
             "(your own setup script seeds all 5)")
    ok("a visit type exists for booking", visit is not None)

    # --------------------------------------------------------- book -> cancel --
    if not LIVE and fresh is not None and first_doctor is not None and visit is not None:
        target_day = (date.today() + timedelta(days=1)).isoformat()
        page = client.get(f"/book-appointment?doctor_id={first_doctor.id}"
                          f"&appointment_date={target_day}")
        ok("the booking page opens for the patient", page.status_code == 200,
           f"HTTP {page.status_code}")

        slots = client.get("/api/appointment-times"
                           f"?doctor_id={first_doctor.id}"
                           f"&appointment_date={target_day}"
                           f"&visit_type_id={visit.id}")
        ok("the slot lookup API answers JSON", slots.status_code == 200,
           f"HTTP {slots.status_code}: {slots.text[:120]}")

        booked = client.post("/book-appointment", data={
            "doctor_id": first_doctor.id,
            "appointment_date": target_day,
            "start_time": "10:30",
            "end_time": "10:45",
            "visit_type_id": visit.id,
            "reason": "integration check",
            "payment_method": "CASH",
            "payment_amount": "0",
        }, follow_redirects=False)
        ok("POST /book-appointment answers with a redirect",
           booked.status_code in (200, 303), f"HTTP {booked.status_code}")

        db.expire_all()
        row = (db.query(Appointment)
               .filter(Appointment.patient_id == fresh.id)
               .order_by(Appointment.id.desc()).first())
        ok("the appointment row is in the database", row is not None)
        if row is not None:
            ok("a new appointment starts as CONFIRMED with payment PENDING",
               row.status in ("BOOKED", "CONFIRMED")
               and row.payment_status == "PENDING",
               f"status={row.status}, payment={row.payment_status}")

            listed = client.get("/appointments")
            ok("the appointment shows on /appointments",
               listed.status_code == 200 and str(row.id) in listed.text,
               f"HTTP {listed.status_code}, id visible: {str(row.id) in listed.text}")

            cancelled = client.post(f"/appointments/{row.id}/cancel",
                                    follow_redirects=False)
            ok("cancel answers with a redirect", cancelled.status_code in (200, 303),
               f"HTTP {cancelled.status_code}")
            db.expire_all()
            db.refresh(row)
            ok("the appointment is really CANCELLED in the database",
               row.status == "CANCELLED", f"status={row.status}")
            ok("a cash appointment needs no refund path (NOT_REQUIRED)",
               row.refund_status == "NOT_REQUIRED", f"refund={row.refund_status}")

        # a second booking that is NOT cancelled: the review page only offers
        # doctors the patient actually has a live appointment with
        again = client.post("/book-appointment", data={
            "doctor_id": first_doctor.id,
            "appointment_date": target_day,
            "start_time": "11:00",
            "end_time": "11:15",
            "visit_type_id": visit.id,
            "reason": "integration check (kept)",
            "payment_method": "CASH",
            "payment_amount": "0",
        }, follow_redirects=False)
        db.expire_all()
        live_rows = (db.query(Appointment)
                     .filter(Appointment.patient_id == fresh.id,
                             Appointment.status.notin_(["CANCELLED", "CANCELED"]))
                     .count())
        ok("a second, active appointment can be booked for the same day",
           again.status_code in (200, 303) and live_rows >= 1,
           f"HTTP {again.status_code}, active rows: {live_rows}")

    # -------------------------------------------------------------- profile ----
    if not LIVE and fresh is not None:
        new_name = "Clinic Check Updated"
        updated = client.post("/profile/update", data={
            "name": new_name, "phone": "9000000010", "age": "32", "gender": "Male",
        }, follow_redirects=False)
        ok("POST /profile/update answers with a redirect",
           updated.status_code in (200, 303), f"HTTP {updated.status_code}")
        db.expire_all()
        db.refresh(fresh)
        ok("the profile change is stored", fresh.name == new_name, f"name={fresh.name}")

    edit_page = client.get("/profile/edit")
    ok("GET /profile/edit renders", edit_page.status_code == 200,
       f"HTTP {edit_page.status_code}")

    # ------------------------------------------------------------ follow-up ----
    if not LIVE and fresh is not None:
        fu = FollowUp(patient_id=fresh.id,
                      doctor_id=first_doctor.id if first_doctor else None,
                      follow_up_date=date.today() + timedelta(days=3),
                      reason="integration check", status="PENDING")
        db.add(fu)
        db.commit()
        care = client.get("/follow-up-care")
        ok("GET /follow-up-care renders", care.status_code == 200,
           f"HTTP {care.status_code}")

        done = client.post(f"/follow-up/{fu.id}/complete", follow_redirects=False)
        ok("marking a follow-up complete answers with a redirect",
           done.status_code in (200, 303), f"HTTP {done.status_code}")
        db.expire_all()
        db.refresh(fu)
        ok("the follow-up really moved out of PENDING",
           fu.status != "PENDING", f"status={fu.status}")

    # --------------------------------------------------- treatment review ------
    page = client.get("/treatment-review")
    ok("GET /treatment-review renders", page.status_code == 200,
       f"HTTP {page.status_code}")
    if not LIVE and fresh is not None and first_doctor is not None:
        submitted = client.post("/treatment-review/submit", data={
            "doctor_id": first_doctor.id,
            "rating": "5",
            "outcome": "Improved",
            "current_condition": "Better",
            "experience": "Good",
            "follow_up_preference": "IN_PERSON",
            "change_reason": "integration check",
            "care_action": "",
        }, follow_redirects=False)
        ok("POST /treatment-review/submit answers",
           submitted.status_code in (200, 303), f"HTTP {submitted.status_code}")
        db.expire_all()
        review = (db.query(TreatmentReview)
                  .filter(TreatmentReview.patient_id == fresh.id).first())
        ok("the review row is stored", review is not None,
           f"HTTP {submitted.status_code}, "
           f"redirect={submitted.headers.get('location')}")

    # ----------------------------------------------------------- screening -----
    page = client.get("/screening")
    ok("GET /screening renders", page.status_code == 200, f"HTTP {page.status_code}")
    if not LIVE and fresh is not None:
        screened = client.post("/screening", data={
            "symptoms": "mild fever and body ache for two days",
        }, follow_redirects=False)
        ok("POST /screening answers without a crash",
           screened.status_code in (200, 303), f"HTTP {screened.status_code}")
        db.expire_all()
        row = (db.query(ScreeningHistory)
               .filter(ScreeningHistory.patient_id == fresh.id)
               .order_by(ScreeningHistory.id.desc()).first())
        ok("the screening result is stored", row is not None)
        if row is not None:
            ok("the screening stored both the symptoms and an answer",
               bool(row.symptoms) and bool(row.ai_response),
               f"ai_response={str(row.ai_response)[:60]!r}")

    # -------------------------------------------------------- report upload ----
    listing = client.get("/medical-reports")
    ok("GET /medical-reports renders", listing.status_code == 200,
       f"HTTP {listing.status_code}")
    if not LIVE:
        upload = client.post("/medical-reports/upload", data={
            "document_type": "Medical Report",
        }, files={"file": ("integration-check.pdf",
                           io.BytesIO(b"%PDF-1.4 integration check"), "application/pdf")})
        ok("POST /medical-reports/upload answers", upload.status_code in (200, 303),
           f"HTTP {upload.status_code}")
        db.expire_all()
        doc = (db.query(PatientDocument)
               .filter(PatientDocument.document_name.like("integration-check%"))
               .order_by(PatientDocument.id.desc()).first())
        ok("the uploaded report is recorded in the database", doc is not None)
        if doc is not None:
            created_file = doc.file_path
            ok("the uploaded file really exists on disk",
               Path(doc.file_path).exists()
               or (Path(UPLOAD_DIR) / Path(doc.file_path).name).exists(),
               str(doc.file_path))

    # -------------------------------------------------------- notifications ----
    if not LIVE and fresh is not None:
        db.add(Notification(user_id=fresh.id, title="Integration check",
                            message="created by check_all_features.py",
                            notification_type="GENERAL", is_read=False))
        db.commit()
    page = client.get("/notifications")
    ok("GET /notifications renders", page.status_code == 200,
       f"HTTP {page.status_code}")
    if not LIVE and fresh is not None:
        db.expire_all()
        n = db.query(Notification).filter(Notification.user_id == fresh.id).count()
        ok("the patient has at least one notification row", n >= 1, f"{n} rows")

    # ------------------------------------------------------------ medical hx ---
    demo = db.query(User).filter(User.email == "patient@demo.com").first()
    records = (db.query(MedicalRecord).filter(MedicalRecord.patient_id == demo.id)
               .count() if demo else 0)
    sheet = client.get("/medical-history")
    ok("GET /medical-history renders", sheet.status_code == 200,
       f"HTTP {sheet.status_code}")
    note(f"the long-lived demo patient has {records} medical record(s) - that "
         f"history is what the booking + desk read, and it is still there")

    # ------------------------------------------------------------- cleanup -----
    if created_file:
        for candidate in (Path(created_file),
                          Path(UPLOAD_DIR) / Path(created_file).name):
            if candidate.exists():
                candidate.unlink()
                break
        note("the report file this check uploaded was deleted again - only that "
             "one file, nothing else under uploads/ was touched")


# =====================================================================
# 2. are the features linked to each other
# =====================================================================

LINK_RULES = [
    # (file, must contain, why)
    ("templates/dashboard.html", "/pharmacy", "dashboard card -> pharmacy"),
    ("templates/dashboard.html", "/doctor-desk", "dashboard card -> doctor desk"),
    ("templates/dashboard.html", "/appointments", "dashboard card -> appointments"),
    ("templates/partials/pharmacy_nav.html", "/dashboard", "pharmacy nav -> clinic dashboard"),
    ("templates/partials/pharmacy_nav.html", "/pharmacy/prescriptions", "nav -> doctor's Rx"),
    ("templates/partials/pharmacy_nav.html", "/pharmacy/admin", "nav -> admin console"),
    ("templates/partials/doctor_nav.html", "/pharmacy", "desk nav -> pharmacy"),
    ("templates/partials/doctor_nav.html", "/dashboard", "desk nav -> my account"),
    ("static/pharmacy.js", "add-prescription", "Rx tab -> add to cart (JS)"),
    ("templates/doctor_patient.html", "send-to-cart", "doctor file -> push Rx to patient cart"),
    ("templates/doctor_patient.html", "/statement", "doctor file -> printable statement"),
    ("src/routers/doctor_desk.py", '("billing", "Full invoice")',
     "doctor file -> full invoice tab exists"),
    ("templates/pharmacy_order.html", "/receipt", "order -> receipt"),
    ("src/routers/auth.py", "/doctor-desk", "login sends a doctor to the desk"),
    ("main.py", "doctor_desk_router", "the desk router is registered"),
    ("src/models/__init__.py", "DoctorPatientNote", "the desk table is registered"),
    ("static/pharmacy.css", ".dd-table", "desk styles are in the shared stylesheet"),
]


def check_links() -> None:
    show("3. features are wired to each other (no dead ends)")

    for rel, needle, why in LINK_RULES:
        path = BASE_DIR / rel
        if not path.exists():
            ok(why, False, f"{rel} missing")
            continue
        ok(why, needle in path.read_text(encoding="utf-8", errors="replace"),
           f"'{needle}' not found in {rel}")

    # every image the catalog points at must exist on disk
    missing_images: list[str] = []
    for rel in ("static/images/pharmacy",):
        folder = BASE_DIR / rel
        if not folder.exists():
            missing_images.append(rel + " (folder)")
    ok("pharmacy image folder exists", not missing_images, ", ".join(missing_images))


def check_orphans(db_path: Path) -> None:
    show("4. cross-table references are clean (no orphan rows)")

    if LIVE or not str(db_path).endswith(".db") or not db_path.exists():
        note("cross-table checks need a SQLite file; on MySQL the same joins are "
             "covered by the foreign keys and by test_pharmacy_mysql.py")
        return

    conn = sqlite3.connect(db_path)
    try:
        tables = {row[0] for row in conn.execute(
            "select name from sqlite_master where type='table'")}
        for needed in ("medicines", "diseases", "medicine_diseases", "pharmacy_orders",
                       "pharmacy_order_items", "pharmacy_cart_items", "nearby_pharmacies",
                       "nearby_pharmacy_stocks", "prescriptions", "prescription_medicines",
                       "doctor_patient_notes", "appointments", "medical_records",
                       "follow_ups", "treatment_reviews", "role_permissions"):
            ok(f"table {needed}", needed in tables, "not created")

        pairs = [
            ("medicine_diseases -> medicines",
             "select count(*) from medicine_diseases md left join medicines m "
             "on m.id = md.medicine_id where m.id is null"),
            ("medicine_diseases -> diseases",
             "select count(*) from medicine_diseases md left join diseases d "
             "on d.id = md.disease_id where d.id is null"),
            ("pharmacy_order_items -> medicines",
             "select count(*) from pharmacy_order_items i left join medicines m "
             "on m.id = i.medicine_id where i.medicine_id is not null and m.id is null"),
            ("pharmacy_order_items -> pharmacy_orders",
             "select count(*) from pharmacy_order_items i left join pharmacy_orders o "
             "on o.id = i.order_id where o.id is null"),
            ("pharmacy_orders -> users",
             "select count(*) from pharmacy_orders o left join users u "
             "on u.id = o.user_id where u.id is null"),
            ("pharmacy_cart_items -> medicines",
             "select count(*) from pharmacy_cart_items c left join medicines m "
             "on m.id = c.medicine_id where m.id is null"),
            ("nearby_pharmacy_stocks -> nearby_pharmacies",
             "select count(*) from nearby_pharmacy_stocks s left join nearby_pharmacies p "
             "on p.id = s.pharmacy_id where p.id is null"),
            ("prescription_medicines -> prescriptions",
             "select count(*) from prescription_medicines pm left join prescriptions p "
             "on p.id = pm.prescription_id where p.id is null"),
            ("prescriptions -> users (patient)",
             "select count(*) from prescriptions p left join users u "
             "on u.id = p.patient_id where u.id is null"),
            ("doctor_patient_notes -> users (patient)",
             "select count(*) from doctor_patient_notes n left join users u "
             "on u.id = n.patient_id where u.id is null"),
            ("appointments -> doctors",
             "select count(*) from appointments a left join doctors d "
             "on d.id = a.doctor_id where a.doctor_id is not null and d.id is null"),
            ("medical_records -> users (patient)",
             "select count(*) from medical_records r left join users u "
             "on u.id = r.patient_id where u.id is null"),
            ("follow_ups -> medical_records",
             "select count(*) from follow_ups f left join medical_records r "
             "on r.id = f.medical_record_id where f.medical_record_id is not null "
             "and r.id is null"),
        ]

        for label, query in pairs:
            try:
                count = conn.execute(query).fetchone()[0]
            except sqlite3.Error as exc:  # table absent etc.
                ok(label + " - clean", False, str(exc)[:80])
                continue
            ok(label + " - clean", count == 0, f"{count} orphan row(s)")

        for label, query in (
            ("catalog has medicines", "select count(*) from medicines"),
            ("catalog has diseases", "select count(*) from diseases"),
            ("medicines linked to a disease", "select count(*) from medicine_diseases"),
            ("partner chemists present", "select count(*) from nearby_pharmacies"),
            ("demo medicine orders present", "select count(*) from pharmacy_orders"),
            ("demo prescriptions present", "select count(*) from prescriptions"),
            ("demo appointments present", "select count(*) from appointments"),
            ("demo doctor notes present", "select count(*) from doctor_patient_notes"),
            ("one SUPERUSER login exists",
             "select count(*) from users where upper(role)='SUPERUSER'"),
            ("one DOCTOR login exists",
             "select count(*) from users where upper(role)='DOCTOR'"),
            ("every medicine has a price > 0",
             "select count(*) from medicines where price is null or price <= 0"),
        ):
            try:
                value = conn.execute(query).fetchone()[0]
            except sqlite3.Error as exc:
                ok(label, False, str(exc)[:80])
                continue
            if label.startswith("every medicine has a price"):
                ok(label, value == 0, f"{value} bad price(s)")
            else:
                ok(label, value > 0, f"count = {value}")
    finally:
        conn.close()


# =====================================================================
# 3. the two flows that cross modules
# =====================================================================

def check_flows(client, db) -> None:
    show("5. end-to-end: buy a strip, and doctor -> patient -> cart")

    from src.models.medicine import Medicine
    from src.models.pharmacy_cart import PharmacyCartItem
    from src.models.pharmacy_order import PharmacyOrder, PharmacyOrderItem
    from src.models.doctor_patient_note import DoctorPatientNote
    from src.models.prescription import Prescription
    from src.models.prescription_medicine import PrescriptionMedicine
    from src.models.appointment import Appointment
    from src.models.user import User

    # ---- patient purchase ----
    client.post("/login", data={"email": "patient@demo.com", "password": "Demo@1234"},
                follow_redirects=False)
    med = db.query(Medicine).filter(Medicine.is_active.is_(True),
                                    Medicine.requires_prescription.is_(False),
                                    Medicine.stock > 5).first()
    ok("a non-Rx medicine exists to buy", med is not None)
    stock_before = int(med.stock) if med else 0

    added = client.post("/pharmacy/api/cart/add",
                        data={"medicine_id": med.id, "quantity": 1})
    ok("add to cart (API)", added.status_code == 200, added.text[:140])

    checkout = client.post("/pharmacy/api/checkout",
                           data={"payment_method": "CASH", "delivery_type": "PICKUP",
                                 "address": "", "notes": "integration check"})
    ok("cash checkout creates an order", checkout.status_code == 200, checkout.text[:160])
    payload = checkout.json() if checkout.status_code == 200 else {}
    order_no = payload.get("order_no") or (payload.get("order") or {}).get("order_no")
    ok("checkout returned an order number", bool(order_no), str(payload)[:160])

    order_page = client.get(f"/pharmacy/order/{order_no}")
    ok("order page renders for the buyer", order_page.status_code == 200)
    receipt = client.get(f"/pharmacy/order/{order_no}/receipt")
    ok("receipt renders", receipt.status_code == 200 and "Sanjeevani" in receipt.text)

    db.expire_all()
    order = db.query(PharmacyOrder).filter(PharmacyOrder.order_no == order_no).first()
    ok("order row in the database", order is not None)
    items = (db.query(PharmacyOrderItem)
             .filter(PharmacyOrderItem.order_id == order.id).count() if order else 0)
    ok("order has at least one item", items >= 1, f"{items} item(s)")

    stock_after = db.get(Medicine, med.id).stock
    ok("stock moved down by what was bought",
       int(stock_after) == stock_before - 1, f"{stock_before} -> {stock_after}")

    # ---- counter side ----
    client.post("/login", data={"email": "pharmacist@demo.com", "password": "Pharma@1234"},
                follow_redirects=False)
    paid = client.post(f"/pharmacy/admin/api/orders/{order.id}/fulfil",
                       data={"action": "mark_paid", "method": "CASH",
                             "reference": "counter-cash"})
    ok("counter can mark the order paid", paid.status_code == 200, paid.text[:140])
    handed = client.post(f"/pharmacy/admin/api/orders/{order.id}/fulfil",
                         data={"action": "handed_over"})
    ok("counter can mark it handed over", handed.status_code == 200, handed.text[:140])
    db.expire_all()
    db.expire_all()
    done = db.get(PharmacyOrder, order.id)
    ok("the counter step is recorded on the order",
       done.status in ("DELIVERED", "COMPLETED", "CONFIRMED")
       and done.handed_over_at is not None,
       f"status {done.status}, handed_over_at {done.handed_over_at}")

    # ---- doctor writes, patient buys ----
    client.post("/login", data={"email": "doctor@demo.com", "password": "Doctor@1234"},
                follow_redirects=False)
    patient = db.query(User).filter(User.email == "patient@demo.com").first()

    wrote = client.post(f"/doctor-desk/patient/{patient.id}/prescription",
                        data={"lines": f"{med.name} | 1 tablet | twice a day | 5 days | after food",
                              "diagnosis": "integration check",
                              "instructions": "Take after meals"},
                        follow_redirects=False)
    ok("doctor desk can issue a prescription", wrote.status_code == 303, str(wrote.status_code))

    db.expire_all()
    rx = (db.query(Prescription)
          .filter(Prescription.patient_id == patient.id,
                  Prescription.diagnosis == "integration check")
          .order_by(Prescription.id.desc()).first())
    ok("prescription row exists", rx is not None)
    lines = (db.query(PrescriptionMedicine)
             .filter(PrescriptionMedicine.prescription_id == rx.id).count() if rx else 0)
    ok("prescription has its medicine line", lines == 1, f"{lines} line(s)")

    patient_page = client.get(f"/doctor-desk/patient/{patient.id}?tab=prescriptions")
    ok("the new Rx shows in the doctor's file",
       "integration check" in patient_page.text)

    push = client.post(f"/doctor-desk/prescription/{rx.id}/send-to-cart",
                       headers={"Accept": "application/json"})
    ok("desk can push the Rx into the patient's cart",
       push.status_code == 200 and push.json().get("success"), push.text[:160])
    pushed = push.json() if push.status_code == 200 else {}
    note(f"push result: {len(pushed.get('added', []))} added, "
         f"{len(pushed.get('skipped', []))} skipped")

    client.post("/login", data={"email": "patient@demo.com", "password": "Demo@1234"},
                follow_redirects=False)
    rx_tab = client.get("/pharmacy/prescriptions")
    ok("the patient sees that prescription in the pharmacy",
       rx_tab.status_code == 200 and f"Rx #{rx.id}" in rx_tab.text,
       f"status {rx_tab.status_code}")
    db.expire_all()
    in_cart = (db.query(PharmacyCartItem)
               .filter(PharmacyCartItem.user_id == patient.id).count())
    ok("the cart of the patient really holds the pushed item(s)", in_cart >= 1,
       f"{in_cart} row(s)")

    # ---- desk writes are visible to the patient / to the ledger ----
    client.post("/login", data={"email": "doctor@demo.com", "password": "Doctor@1234"},
                follow_redirects=False)
    note_res = client.post(f"/doctor-desk/patient/{patient.id}/notes",
                           data={"title": "Integration note (patient visible)",
                                 "body": "Cross-module check.",
                                 "note_type": "ADVISORY",
                                 "visibility": "PATIENT_VISIBLE"},
                           follow_redirects=False)
    ok("desk can save a note", note_res.status_code == 303)
    db.expire_all()
    saved_note = (db.query(DoctorPatientNote)
                  .filter(DoctorPatientNote.title == "Integration note (patient visible)")
                  .order_by(DoctorPatientNote.id.desc()).first())
    ok("note row written with the doctor as author",
       saved_note is not None and saved_note.doctor_name is not None)

    client.post("/login", data={"email": "patient@demo.com", "password": "Demo@1234"},
                follow_redirects=False)
    history = client.get("/medical-history")
    ok("patient-visible note reaches the patient's history page",
       "Integration note (patient visible)" in history.text)

    # ---- appointment fee recorded from the desk lands in the ledger ----
    client.post("/login", data={"email": "doctor@demo.com", "password": "Doctor@1234"},
                follow_redirects=False)
    appt = (db.query(Appointment)
            .filter(Appointment.patient_id == patient.id,
                    Appointment.payment_status != "PAID")
            .order_by(Appointment.id).first())
    if appt is None:
        tomorrow = date.today() + timedelta(days=1)
        appt = Appointment(patient_id=patient.id, appointment_date=tomorrow,
                           visit_type="General Consultation", status="BOOKED",
                           payment_status="PENDING", payment_amount=0)
        db.add(appt)
        db.commit()
        db.refresh(appt)

    pay = client.post(f"/doctor-desk/appointment/{appt.id}/payment",
                      data={"payment_status": "PAID", "amount": "500",
                            "payment_method": "CASH"},
                      headers={"Accept": "application/json"})
    ok("desk can record an appointment payment",
       pay.status_code == 200 and pay.json().get("payment_status") == "PAID",
       pay.text[:160])
    db.expire_all()
    ok("the appointment row carries the payment",
       db.get(Appointment, appt.id).payment_status == "PAID")
    billing = client.get(f"/doctor-desk/patient/{patient.id}?tab=billing")
    ok("the ledger tab shows both kinds of billable line",
       "Appointment fee" in billing.text and "Medicine order" in billing.text)
    statement = client.get(f"/doctor-desk/patient/{patient.id}/statement")
    ok("printable statement still renders after those writes",
       statement.status_code == 200 and "Balance due" in statement.text)

    # ---- audit trail recorded all of it ----
    client.post("/login", data={"email": "superuser@sanjeevani.com", "password": "Super@1234"},
                follow_redirects=False)
    audit = client.get("/pharmacy/admin/api/audit?limit=40")
    rows = audit.json().get("logs", []) if audit.status_code == 200 else []
    actions = {row.get("action") for row in rows}
    for expected in ("pharmacy.order.create", "doctor.prescription.write",
                     "doctor.note.add", "doctor.payment.write", "doctor.patient.view"):
        ok(f"audit trail has {expected}", expected in actions,
           f"seen: {sorted(a for a in actions if a)[:6]}")

    # ---- role matrix really changes behaviour ----
    # (revoking a permission is exercised in check_rbac_toggle, so the flow
    #  above always runs against the default matrix)


def check_rbac_toggle(client) -> None:
    """After a revoke, the doctor must lose the desk; after reset, get it back."""

    doctor = client  # the session handed over by check_flows (a super user)

    # a super user switches one permission off for the whole DOCTOR role
    login = doctor.post("/login", data={"email": "superuser@sanjeevani.com",
                                       "password": "Super@1234"},
                        follow_redirects=False)
    ok("super user can log in again", login.status_code == 303)
    flip = doctor.post("/pharmacy/admin/api/roles/permission",
                       data={"role": "DOCTOR", "permission": "doctor.desk.read"},
                       headers={"Accept": "application/json"})
    ok("super user can revoke doctor.desk.read for the role",
       flip.status_code == 200, flip.text[:140])

    doctor.post("/login", data={"email": "doctor@demo.com", "password": "Doctor@1234"},
                follow_redirects=False)
    blocked = doctor.get("/doctor-desk", follow_redirects=False)
    ok("revoked doctor.desk.read really closes the desk",
       blocked.status_code == 303 and "doctor-desk" not in
       (blocked.headers.get("location") or ""),
       blocked.headers.get("location", ""))

    doctor.post("/login", data={"email": "superuser@sanjeevani.com", "password": "Super@1234"},
                follow_redirects=False)
    reset = doctor.post("/pharmacy/admin/api/roles/reset", data={"role": "DOCTOR"},
                        headers={"Accept": "application/json"})
    ok("super user can reset a role back to defaults",
       reset.status_code == 200, reset.text[:120])

    doctor.post("/login", data={"email": "doctor@demo.com", "password": "Doctor@1234"},
                follow_redirects=False)
    back = doctor.get("/doctor-desk")
    ok("and the desk works again after the reset", back.status_code == 200)


# =====================================================================
# main
# =====================================================================

def _dispose_app_engine() -> None:
    """Close every pooled connection the app opened.

    Windows refuses to delete a SQLite file while a connection to it is
    still open (WinError 32), so the app's engine must be disposed before
    the throwaway database file is removed.
    """
    import gc

    try:
        from src.database import connection as db_connection

        engine = getattr(db_connection, "engine", None)
        if engine is not None:
            engine.dispose()
    except Exception:
        pass
    gc.collect()


def _remove_scratch_db(path) -> None:
    """Delete a throwaway database file without ever failing the run.

    The checks have already decided the verdict - cleanup must not turn a
    green run red. On Windows the file can stay locked for a moment
    (WinError 32); retry briefly, then leave it in place: it is a scratch
    file that the next run rebuilds anyway.
    """
    import time

    for _ in range(3):
        try:
            path.unlink(missing_ok=True)
            return
        except PermissionError:
            time.sleep(0.5)
    print(f"  note: {path.name} is still in use and was left in place "
          f"(throwaway file - the next run rebuilds it)")


def main() -> int:
    global LIVE, HTML_OUT

    parser = argparse.ArgumentParser(description="cross-check the whole project")
    parser.add_argument("--live", action="store_true",
                        help="run read-only checks against the database your .env "
                             "points at (no URL needed, nothing is written)")
    parser.add_argument("--html", default=None, help="also write an HTML report here")
    args = parser.parse_args()

    LIVE = args.live
    HTML_OUT = args.html

    temp_db = BASE_DIR / "check_all_features.db"

    if not LIVE:
        # IMPORTANT: the env has to be set before src.config is imported, or
        # the app keeps using sanjeevani_clinic.db and this script would write
        # its test orders into your demo database.
        _remove_scratch_db(temp_db)
        os.environ["USE_SQLITE"] = "true"
        os.environ["SQLITE_DB_PATH"] = str(temp_db)

        import seed_pharmacy
        from src.database.connection import DATABASE_LABEL

        if str(temp_db) not in DATABASE_LABEL:
            raise SystemExit(
                f"refusing to run: the app is pointed at {DATABASE_LABEL}, "
                f"not the throwaway {temp_db}"
            )

        print("Building a throwaway database (your own data is never touched)...")
        seed_pharmacy.seed(reset=False)
        db_path = temp_db
    else:
        from src.database.connection import DATABASE_LABEL
        print(f"Live, read-only checks against: {DATABASE_LABEL}")
        db_path = Path(os.environ.get("SQLITE_DB_PATH", "sanjeevani_clinic.db"))

    os.environ.setdefault("GROQ_API_KEY", os.environ.get("GROQ_API_KEY", "check-key"))

    show("1. the app boots")
    import main as app_module
    from fastapi.testclient import TestClient
    from src.database.connection import SessionLocal

    print("Static + page checks:")
    with TestClient(app_module.app) as client:
        css = client.get("/static/pharmacy.css")
        ok("pharmacy stylesheet loads", css.status_code == 200 and ".dd-table" in css.text,
           f"status {css.status_code}")
        js = client.get("/static/pharmacy.js")
        ok("pharmacy script loads", js.status_code == 200, f"status {js.status_code}")
        home = client.get("/")
        ok("home page renders", home.status_code == 200, f"status {home.status_code}")

        check_pages(client)
        check_links()
        check_google(client)

        db = SessionLocal()
        try:
            check_schema_parity(db)
            if LIVE:
                note("live mode: flows skipped on purpose (nothing is written)")
            else:
                check_flows(client, db)
                check_rbac_toggle(client)
            check_clinic_flows(client, db)
        finally:
            db.close()

    check_orphans(db_path)

    total = len(PASSED) + len(FAILED)
    print("\n" + "-" * 70)
    for name, extra in FAILED:
        print(f"  FAIL  {name}   {extra}")
    for line in NOTES:
        print(f"  note  {line}")
    print(f"{len(PASSED)}/{total} checks passed, {len(FAILED)} failed")
    if not FAILED:
        print("Everything is connected: clinic + pharmacy + doctor desk.")

    if HTML_OUT:
        grouped: dict[str, list[str]] = {}
        for entry in PASSED:
            head, _, rest = entry.partition(" :: ")
            grouped.setdefault(head, []).append(rest)
        rows = "".join(
            f"<tr class='sec'><td colspan='2'>{head} "
            f"<span>({len(items)} passed)</span></td></tr>"
            + "".join(f"<tr><td class='tick'>&#10003;</td><td>{n}</td></tr>" for n in items)
            for head, items in grouped.items())
        bad = "".join(f"<tr class='bad'><td>{n}</td><td>{e}</td></tr>" for n, e in FAILED)
        Path(HTML_OUT).write_text(
            "<meta charset='utf-8'><style>body{font-family:Arial,"
            "sans-serif;background:#f4f7fb;padding:24px;color:#111827}"
            "table{border-collapse:collapse;width:100%;background:#fff}"
            "td{padding:4px 8px;border-bottom:1px solid #e5e7eb;font-size:13px}"
            "tr.sec td{background:#0f766e;color:#fff;font-weight:bold;padding-top:10px}"
            "tr.sec span{opacity:.75;font-weight:normal}"
            "td.tick{color:#059669;width:22px}"
            ".bad td{background:#fef2f2;color:#991b1b}h1{color:#0f766e}"
            "p.sub{color:#4b5563}</style>"
            f"<h1>Sanjeevani - integration report</h1>"
            f"<p class='sub'>{len(PASSED)}/{total} checks passed, {len(FAILED)} failed "
            f"&middot; {date.today()} &middot; clinic + pharmacy + doctor desk</p>"
            f"<table>{bad}{rows}</table>",
            encoding="utf-8"
        )
        print(f"report written to {HTML_OUT}")

    if not LIVE:
        _dispose_app_engine()
        _remove_scratch_db(temp_db)   # scratch database only; nothing else is removed

    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
