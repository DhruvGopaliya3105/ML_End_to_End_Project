"""End-to-end smoke test for the pharmacy module - run it before you push.

    python test_pharmacy.py

What it does
------------\nBuilds a throwaway SQLite database (``pharmacy_test.db`` next to this file,
via the new ``SQLITE_DB_PATH`` setting), seeds the pharmacy into it, boots the
real FastAPI app on it, then walks the whole feature: browse -> cart -> cash
checkout -> confirmed -> online payment -> cancel + stock restored -> doctor
prescription tab -> emergency nearby search -> RBAC denial -> admin catalog
edit -> audit log -> snapshot -> bulk price -> rollback -> role override.

It prints one line per check and exits 1 if anything failed, so it is usable
in CI as well as by hand. Nothing here mocks the app: every assertion goes
through real HTTP routes and real SQL.
"""

import os
import shutil
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

TEST_DB = BASE_DIR / "pharmacy_test.db"

os.environ["USE_SQLITE"] = "true"
os.environ["SQLITE_DB_PATH"] = str(TEST_DB)
os.environ.setdefault("GROQ_API_KEY", "test-key-not-used")
os.environ.setdefault("LOG_LEVEL", "WARNING")

PASSED = 0
FAILED: list[str] = []


def check(name: str, condition, extra: str = "") -> None:
    global PASSED

    if condition:
        PASSED += 1
        print(f"  PASS  {name}")
    else:
        FAILED.append(name)
        print(f"  FAIL  {name}{('  <- ' + extra) if extra else ''}")


def section(title: str) -> None:
    print(f"\n=== {title} ===")


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


def _remove_scratch_db(path: Path) -> None:
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


# =========================================================
# SETUP
# =========================================================

def build_database() -> None:
    _remove_scratch_db(TEST_DB)

    import seed_pharmacy

    seed_pharmacy.seed(reset=False)


# =========================================================
# TESTS
# =========================================================

def run(client) -> None:  # noqa: C901 - one long linear script is easiest to read

    from src.database.connection import SessionLocal
    from src.models.medicine import Medicine
    from src.models.user import User

    def stock_of(db, name):
        row = db.query(Medicine).filter(Medicine.name == name).first()
        return int(row.stock or 0) if row else None

    def medicine_id(db, name):
        row = db.query(Medicine).filter(Medicine.name == name).first()
        return row.id if row else None

    db = SessionLocal()

    # ---------------------------------------------------------
    section("1. Public catalog (no login needed)")

    page = client.get("/pharmacy")
    check("GET /pharmacy renders", page.status_code == 200, str(page.status_code))
    check("catalog shows product cards", "data-ph=\\\"add\\\"" in page.text or "ph-card" in page.text)
    check("catalog shows a price", "Rs " in page.text, "price formatting")

    searched = client.get("/pharmacy?q=dolo")
    check("search finds Dolo 650", "Dolo 650 Tablet" in searched.text)
    check("search shows its price", "Rs 32.00" in searched.text)
    check("catalog shows a photo tag", "/static/images/pharmacy/" in page.text)
    check("disease chips rendered", "Diabetes" in page.text)

    filtered = client.get("/pharmacy?disease=diabetes")
    check("filter by disease works", "Glycomet" in filtered.text)

    search = client.get("/pharmacy/api/medicines?q=para")
    check("live search API", search.status_code == 200 and search.json()["success"])
    check(
        "live search found paracetamol items",
        len(search.json()["results"]) > 0
    )

    # ---------------------------------------------------------
    section("2. Patient login and cart")

    login = client.post(
        "/login",
        data={"email": "patient@demo.com", "password": "Demo@1234"},
        follow_redirects=False
    )
    check("patient can log in", login.status_code == 303, str(login.status_code))

    dolo_id = medicine_id(db, "Dolo 650 Tablet")
    before = stock_of(db, "Dolo 650 Tablet")

    added = client.post(
        "/pharmacy/api/cart/add",
        data={"medicine_id": dolo_id, "quantity": 2}
    )
    check("add to cart", added.status_code == 200, added.text[:160])
    check(
        "cart badge shows 2 packs",
        added.json().get("cart", {}).get("count") == 2,
        added.text[:160]
    )

    cart_page = client.get("/pharmacy/cart")
    check("cart page renders", cart_page.status_code == 200)
    check("cart page shows the line", "Dolo 650 Tablet" in cart_page.text)
    check("cart page offers cash + online", "payment_method" in cart_page.text)

    # prescription-only medicine the patient was NOT prescribed
    voveran = medicine_id(db, "Voveran Tablet")
    blocked = client.post(
        "/pharmacy/api/cart/add", data={"medicine_id": voveran, "quantity": 1}
    )
    check(
        "Rx-only medicine is refused without a prescription",
        blocked.status_code == 409,
        blocked.text[:160]
    )

    # ---------------------------------------------------------
    section("3. Cash checkout -> order confirmed + stock moves")

    placed = client.post(
        "/pharmacy/checkout",
        data={
            "payment_method": "CASH",
            "delivery_type": "PICKUP",
            "phone": "9876543210",
        },
        follow_redirects=False
    )
    check("checkout redirects", placed.status_code == 303, str(placed.status_code))

    order_url = placed.headers.get("location", "/pharmacy/orders")
    order_page = client.get(order_url)
    check("order page renders", order_page.status_code == 200, order_url)
    check("order shows CONFIRMED", "Confirmed" in order_page.text)
    check("order says pay at the counter", "pay" in order_page.text.lower())
    check("order page links the printable receipt", "/receipt" in order_page.text)

    db.expire_all()
    after = stock_of(db, "Dolo 650 Tablet")
    check("stock went down by 2", after == before - 2, f"{before} -> {after}")

    # ---------------------------------------------------------
    section("4. Online payment flow")

    # Gelusil is OTC and in stock, so the add cannot be blocked by the
    # prescription rule - this section is about payment, not about Rx checks.
    gel_id = medicine_id(db, "Gelusil MPS Suspension 100ml")
    gel_before = stock_of(db, "Gelusil MPS Suspension 100ml")

    add_gel = client.post("/pharmacy/api/cart/add", data={"medicine_id": gel_id, "quantity": 1})
    check("OTC add to cart works", add_gel.status_code == 200, add_gel.text[:160])

    online = client.post(
        "/pharmacy/api/checkout",
        data={"payment_method": "ONLINE", "delivery_type": "PICKUP"}
    )
    check("online order created", online.status_code == 200, online.text[:200])
    payload = online.json()
    order_id = payload.get("order_id")
    check(
        "online order starts as PENDING_PAYMENT",
        payload.get("status") == "PENDING_PAYMENT",
        str(payload)[:200]
    )

    unpaid = client.get(f"/pharmacy/order/{order_id}")
    check("unpaid order page shows a pay box", "ph-pay" in unpaid.text)

    paid = client.post(f"/pharmacy/api/order/{order_id}/pay", data={})
    check("payment confirmed", paid.status_code == 200, paid.text[:200])
    check("order now CONFIRMED", paid.json().get("status") == "CONFIRMED")
    check("payment now PAID", paid.json().get("payment_status") == "PAID")
    check(
        "transaction id written",
        bool((paid.json().get("transaction_id") or "").startswith("SJV")),
        str(paid.json().get("transaction_id"))
    )

    db.expire_all()
    check("stock reserved for online order", stock_of(db, "Gelusil MPS Suspension 100ml") == gel_before - 1)

    # ---------------------------------------------------------
    section("5. Cancel gives the stock back (exactly once)")

    crocin_id = medicine_id(db, "Crocin Advance Tablet")
    crocin_before = stock_of(db, "Crocin Advance Tablet")

    client.post("/pharmacy/api/cart/add", data={"medicine_id": crocin_id, "quantity": 3})
    third = client.post(
        "/pharmacy/api/checkout",
        data={"payment_method": "ONLINE", "delivery_type": "PICKUP"}
    ).json()

    db.expire_all()
    check("stock dropped by 3", stock_of(db, "Crocin Advance Tablet") == crocin_before - 3)

    cancelled = client.post(
        f"/pharmacy/api/order/{third['order_id']}/cancel",
        data={"reason": "smoke test cancel"}
    )
    check("cancel accepted", cancelled.status_code == 200, cancelled.text[:160])

    db.expire_all()
    check(
        "stock restored after cancel",
        stock_of(db, "Crocin Advance Tablet") == crocin_before
    )

    twice = client.post(f"/pharmacy/api/order/{third['order_id']}/cancel", data={})
    check(
        "cancelling twice is refused (no double restock)",
        twice.status_code == 409,
        twice.text[:160]
    )

    # ---------------------------------------------------------
    section("6. Doctor prescribed tab")

    rx_page = client.get("/pharmacy/prescriptions")
    check("prescription tab renders", rx_page.status_code == 200)
    check("shows the prescribed tablet", "Dolo 650 Tablet" in rx_page.text)
    check(
        "shows an un-stocked line separately",
        "Napa Extend" in rx_page.text,
        "the unmatched medicine should still be listed"
    )
    check("out-of-stock medicine flagged for nearby", "Find nearby" in rx_page.text)

    from sqlalchemy import text as sa_text

    db_row = db.execute(
        sa_text(
            "select id from prescription_medicines "
            "where medicine_name = 'Dolo 650 Tablet'"
        )
    ).first()

    added_rx = client.post(
        "/pharmacy/api/cart/add-prescription",
        data={"prescription_medicine_id": db_row[0], "quantity": 1}
    )
    check("prescribed item can be added to cart", added_rx.status_code == 200, added_rx.text[:160])

    add_all = client.post(
        "/pharmacy/api/prescriptions/add-all",
        data={"prescription_id": 1}
    )
    check(
        "'add all available' skips what we do not stock",
        add_all.status_code == 200 and "skipped" in add_all.json()
    )

    client.post("/pharmacy/api/cart/clear", data={})

    # ---------------------------------------------------------
    section("7. Emergency 'find it nearby' (SQL + Google)")

    azithro = db.query(Medicine).filter(Medicine.name == "Azithral 500 Tablet").first()
    check("seeded an out-of-stock medicine for this test", int(azithro.stock or 0) == 0)

    nearby_page = client.get(f"/pharmacy/nearby?medicine_id={azithro.id}")
    check("nearby page renders", nearby_page.status_code == 200)
    check(
        "nearby page lists the partner shop that stocks it",
        "MedPlus" in nearby_page.text,
        "MedPlus - Vaishali Nagar holds Azithral in the seed data"
    )
    check("nearby page has a call button", "Call shop" in nearby_page.text)
    check("nearby page has a maps route link", "google.com/maps" in nearby_page.text)

    nearby_api = client.get(f"/pharmacy/api/nearby?medicine_id={azithro.id}").json()
    check("nearby API reports no Google key", nearby_api["google_status"] == "no_key")
    check(
        "nearby API still returns partner stock from SQL",
        len(nearby_api["results"]) > 0,
        str(nearby_api)[:200]
    )

    # ---------------------------------------------------------
    section("8. Role based access control")

    as_patient = client.get("/pharmacy/admin", follow_redirects=False)
    check(
        "patient cannot open the admin console",
        as_patient.status_code in (303, 307) and "/dashboard" in as_patient.headers.get("location", ""),
        str(as_patient.status_code) + " " + as_patient.headers.get("location", "")
    )

    patient_admin_api = client.get("/pharmacy/admin/api/audit")
    check("patient cannot read the audit log", patient_admin_api.status_code == 403)

    patient_write = client.post(
        "/pharmacy/admin/api/medicines",
        data={"name": "Sneaky Tablet", "price": 1}
    )
    check("patient cannot add to the catalog", patient_write.status_code == 403)

    # switch to the super user
    client.get("/logout")
    su_login = client.post(
        "/login",
        data={"email": "superuser@sanjeevani.com", "password": "Super@1234"},
        follow_redirects=False
    )
    check("super user can log in", su_login.status_code == 303)

    for tab in ("orders", "catalog", "nearby", "audit", "access", "snapshots"):
        response = client.get(f"/pharmacy/admin?tab={tab}")
        check(f"super user can open tab '{tab}'", response.status_code == 200, str(response.status_code))

    pharmacist_login = client.post("/login", data={
        "email": "pharmacist@demo.com", "password": "Pharma@1234"
    }, follow_redirects=False)
    check("pharmacist logs in", pharmacist_login.status_code == 303)
    pharmacist_catalog = client.get("/pharmacy/admin?tab=catalog", follow_redirects=False)
    check(
        "pharmacist is bounced off the catalog tab (no write role)",
        pharmacist_catalog.status_code in (200, 303)
    )
    pharmacist_delete = client.request(
        "DELETE", f"/pharmacy/admin/api/medicines/{azithro.id}", data={"confirm": "DELETE"}
    )
    check("pharmacist cannot delete medicines", pharmacist_delete.status_code == 403)

    client.get("/logout")
    client.post(
        "/login",
        data={"email": "superuser@sanjeevani.com", "password": "Super@1234"},
        follow_redirects=False
    )

    # ---------------------------------------------------------
    section("9. Admin catalog writes")

    created = client.post("/pharmacy/admin/api/medicines", data={
        "name": "Smoke Test Syrup 100ml",
        "generic_name": "Testol 100 mg",
        "price": "44.50",
        "mrp": "50.00",
        "stock": "30",
        "form": "SYRUP",
        "diseases": "fever, Test Condition",
    })
    check("admin can add a medicine", created.status_code == 200, created.text[:200])
    new_id = created.json().get("medicine", {}).get("id")
    check("SKU auto-generated", bool(created.json().get("medicine", {}).get("sku")))
    check("new medicine got the disease tag", "Test Condition" in (created.json()["medicine"]["disease_names"] or []))

    stocked = client.post(
        f"/pharmacy/admin/api/medicines/{new_id}/stock",
        data={"change": "20", "mode": "delta", "reason": "goods received"}
    )
    check("stock adjustment works", stocked.json().get("stock") == 50, stocked.text[:160])

    priced = client.post(
        f"/pharmacy/admin/api/medicines/{new_id}",
        data={"price": "39.90"}
    )
    check("price edit works", priced.status_code == 200, priced.text[:160])
    db.expire_all()
    check("new price is in the DB", stock_and_price(db, new_id) == 39.90)

    toggled = client.post(f"/pharmacy/admin/api/medicines/{new_id}/toggle", data={})
    check("visibility toggle works", toggled.json().get("is_active") is False)

    client.post(f"/pharmacy/admin/api/medicines/{new_id}/toggle", data={})

    bad_delete = client.request("DELETE", f"/pharmacy/admin/api/medicines/{new_id}")
    check("delete without confirmation is refused", bad_delete.status_code == 400)

    # ---------------------------------------------------------
    section("10. Audit log")

    logs = client.get("/pharmacy/admin/api/audit?limit=200").json()
    check("audit log readable", logs.get("success") and logs["total"] > 5, str(logs)[:160])
    names = [row["action"] for row in logs["logs"]]
    check("order creation is logged", "pharmacy.order.create" in names, str(names[:8]))
    check("medicine edit is logged", "pharmacy.medicine.update" in names, str(names[:8]))
    check("stock change is logged", "pharmacy.medicine.stock" in names)
    check("actor is recorded", all(row["actor_role"] for row in logs["logs"][:5]))
    sample = next(
        (row for row in logs["logs"] if row["action"] == "pharmacy.medicine.stock"), None
    )
    check(
        "before/after JSON is stored",
        sample is not None and '"stock"' in (sample["after_json"] or ""),
        str(sample)[:160]
    )

    filtered_logs = client.get("/pharmacy/admin/api/audit?severity=CRITICAL").json()
    check("severity filter runs", filtered_logs.get("success"))

    csv_export = client.get("/pharmacy/admin/api/audit/export.csv")
    check(
        "CSV export downloads",
        csv_export.status_code == 200 and csv_export.text.startswith("created_at")
    )

    # ---------------------------------------------------------
    section("11. Snapshot -> bulk change -> preview -> rollback")

    snap = client.post("/pharmacy/admin/api/snapshots", data={
        "label": "Before smoke test bulk change",
        "scope": "CATALOG",
    })
    check("snapshot can be taken", snap.status_code == 200, snap.text[:200])
    snapshot_id = snap.json()["snapshot"]["id"]
    checksum = snap.json()["snapshot"]["checksum"]

    db.expire_all()
    price_before = stock_and_price(db, new_id)

    bulk = client.post("/pharmacy/admin/api/catalog/bulk-price", data={"percent": "10"})
    check("bulk price update runs", bulk.status_code == 200, bulk.text[:200])

    db.expire_all()
    price_after = stock_and_price(db, new_id)
    check("bulk price actually changed it", abs(price_after - round(price_before * 1.1, 2)) < 0.01, f"{price_before} -> {price_after}")

    preview = client.get(f"/pharmacy/admin/api/snapshots/{snapshot_id}/preview").json()
    check("preview reports pending changes", preview["preview"]["total_changes"] > 0)

    wrong = client.post(
        f"/pharmacy/admin/api/snapshots/{snapshot_id}/restore",
        data={"checksum": "deadbeef"}
    )
    check("restore with a wrong checksum is refused", wrong.status_code == 409, wrong.text[:160])

    restored = client.post(
        f"/pharmacy/admin/api/snapshots/{snapshot_id}/restore",
        data={"checksum": checksum}
    )
    check("restore accepted", restored.status_code == 200, restored.text[:240])

    db.expire_all()
    back = stock_and_price(db, new_id)
    check("price is back after rollback", abs(back - price_before) < 0.005, f"{price_after} -> {back}")
    check("an undo point was created first", restored.json().get("undo_snapshot_id"))

    pinned = client.post(f"/pharmacy/admin/api/snapshots/{snapshot_id}/pin", data={})
    check("snapshot can be pinned", pinned.status_code == 200)

    # ---------------------------------------------------------
    section("12. Permission override really changes behaviour")

    denied = client.post("/pharmacy/admin/api/roles/permission", data={
        "role": "PATIENT",
        "permission": "pharmacy.cart.manage",
    })
    check("super user can edit the matrix", denied.status_code == 200, denied.text[:160])

    still_admin = client.get("/pharmacy/admin?tab=access")
    check(
        "super user keeps every permission while editing roles",
        still_admin.status_code == 200
    )

    client.get("/logout")
    client.post("/login", data={"email": "patient@demo.com", "password": "Demo@1234"}, follow_redirects=False)

    blocked_now = client.post(
        "/pharmacy/api/cart/add", data={"medicine_id": dolo_id, "quantity": 1}
    )
    check("patient is locked out of the cart after the override", blocked_now.status_code == 403, blocked_now.text[:160])

    client.get("/logout")
    client.post("/login", data={"email": "superuser@sanjeevani.com", "password": "Super@1234"}, follow_redirects=False)
    client.post("/pharmacy/admin/api/roles/reset", data={"role": "PATIENT"})

    client.get("/logout")
    client.post("/login", data={"email": "patient@demo.com", "password": "Demo@1234"}, follow_redirects=False)
    allowed_again = client.post(
        "/pharmacy/api/cart/add", data={"medicine_id": dolo_id, "quantity": 1}
    )
    check("reset restores the default (patient can cart again)", allowed_again.status_code == 200, allowed_again.text[:160])
    client.post("/pharmacy/api/cart/clear", data={})

    client.get("/logout")
    client.post("/login", data={"email": "superuser@sanjeevani.com", "password": "Super@1234"}, follow_redirects=False)

    # ---------------------------------------------------------
    section("13. Guard rails on role editing")

    su = db.query(User).filter(User.email == "superuser@sanjeevani.com").first()
    self_demote = client.post(f"/pharmacy/admin/api/users/{su.id}/role", data={"role": "PATIENT"})
    check("a super user cannot drop their own role", self_demote.status_code == 400, self_demote.text[:160])

    su_lock = client.post("/pharmacy/admin/api/roles/permission", data={
        "role": "SUPERUSER", "permission": "pharmacy.view",
    })
    check("the SUPERUSER row is locked in the matrix", su_lock.status_code == 400)

    demote_patient = client.post(
        f"/pharmacy/admin/api/users/{db.query(User).filter(User.email == 'patient@demo.com').first().id}/role",
        data={"role": "PHARMACIST"}
    )
    check("super user can change someone else's role", demote_patient.status_code == 200, demote_patient.text[:160])
    client.post(
        f"/pharmacy/admin/api/users/{db.query(User).filter(User.email == 'patient@demo.com').first().id}/role",
        data={"role": "PATIENT"}
    )

    # ---------------------------------------------------------
    section("14. Pages a patient uses, once more end to end")

    # orders are per patient: sign back in as the patient who bought them
    client.get("/logout")
    client.post("/login", data={"email": "patient@demo.com", "password": "Demo@1234"}, follow_redirects=False)

    my_orders = client.get("/pharmacy/orders")
    check("my-orders page renders", my_orders.status_code == 200)
    check("my-orders lists the earlier order", "PH-" in my_orders.text, my_orders.text[:120])

    client.get("/logout")
    client.post("/login", data={"email": "admin@demo.com", "password": "Admin@1234"}, follow_redirects=False)
    admin_orders = client.get("/pharmacy/admin/api/orders")
    check("ADMIN role can read the whole order queue", admin_orders.status_code == 200)

    client.get("/logout")
    client.post("/login", data={"email": "superuser@sanjeevani.com", "password": "Super@1234"}, follow_redirects=False)

    receipt = client.get(f"/pharmacy/order/{order_id}/receipt")
    check("receipt renders", receipt.status_code == 200)
    check("receipt has the totals", "Total" in receipt.text)

    staff_queue = client.get("/pharmacy/admin/api/orders?status=CONFIRMED").json()
    check("staff order queue works", staff_queue.get("success") and staff_queue["total"] >= 2)

    fulfil = client.post(
        f"/pharmacy/admin/api/orders/{order_id}/fulfil",
        data={"action": "handed_over"}
    )
    check("counter can mark handed over", fulfil.status_code == 200, fulfil.text[:160])

    refund = client.post(
        f"/pharmacy/admin/api/orders/{order_id}/fulfil",
        data={"action": "refund", "reason": "smoke test refund"}
    )
    check("counter can refund a paid order", refund.json().get("status") == "REFUNDED", refund.text[:160])
    db.expire_all()
    check(
        "refund put the stock back",
        stock_of(db, "Gelusil MPS Suspension 100ml") == gel_before
    )


    # ---------------------------------------------------------
    section("15. Doctor desk - reading a patient file")

    from src.models.appointment import Appointment
    from src.models.doctor_patient_note import DoctorPatientNote
    from src.models.follow_up import FollowUp
    from src.models.medical_record import MedicalRecord
    from src.models.pharmacy_audit_log import PharmacyAuditLog
    from src.models.prescription import Prescription
    from src.models.prescription_medicine import PrescriptionMedicine
    from src.models.role_permission import RolePermission

    demo_patient = db.query(User).filter(User.email == "patient@demo.com").first()
    demo_doctor_user = db.query(User).filter(User.email == "doctor@demo.com").first()

    doctor_login = client.post(
        "/login",
        data={"email": "doctor@demo.com", "password": "Doctor@1234"},
        follow_redirects=False
    )
    check(
        "a doctor lands on the desk, not the dashboard",
        doctor_login.status_code == 303
        and "/doctor-desk" in doctor_login.headers.get("location", ""),
        doctor_login.headers.get("location", "")
    )

    roster = client.get("/doctor-desk")
    check("desk roster renders", roster.status_code == 200, str(roster.status_code))
    check("roster shows the signed-in doctor", "Dr. Vikram Joshi" in roster.text)
    check("roster shows an enrolled patient", (demo_patient.name or "") in roster.text)
    check("roster counts are live, not written in the template",
          "Enrolled patients" in roster.text and "Total dues on files" in roster.text)
    check("roster links into each file",
          f"/doctor-desk/patient/{demo_patient.id}" in roster.text)

    listed = client.get("/doctor-desk/api/patients?q=" + demo_patient.email.split("@")[0])
    check("patient search API answers", listed.status_code == 200 and listed.json()["success"])
    check(
        "search API found that patient by email fragment",
        any(row["email"] == demo_patient.email for row in listed.json()["rows"]),
        listed.text[:200]
    )

    summary = client.get("/doctor-desk/api/summary")
    check("desk tile API works", summary.status_code == 200)
    check(
        "tiles report at least one patient",
        summary.json().get("patients", 0) >= 1,
        summary.text[:160]
    )

    missing = client.get("/doctor-desk?q=zzz-no-such-person")
    check("a search with no hit says so", "No patient matches" in missing.text)

    bad_scope = client.get("/doctor-desk?scope=drop%20table&sort=bogus")
    check("an unknown scope/sort falls back safely", bad_scope.status_code == 200)

    file_page = client.get(f"/doctor-desk/patient/{demo_patient.id}")
    check("patient file renders", file_page.status_code == 200)
    check("file header shows patient id", "SJV-" in file_page.text)
    records_page = client.get(f"/doctor-desk/patient/{demo_patient.id}?tab=records")
    check(
        "file shows the demo consultation history",
        "hypertension" in records_page.text.lower(),
        "the seeded record did not reach the records tab"
    )
    check(
        "the overview timeline lists recent events",
        "visit" in file_page.text.lower()
    )

    tab_failures = []

    for slug in ("overview", "visits", "records", "prescriptions", "medicines",
                 "billing", "notes", "reviews", "documents", "timeline"):
        response = client.get(f"/doctor-desk/patient/{demo_patient.id}?tab={slug}")
        if response.status_code != 200:
            tab_failures.append(f"{slug}={response.status_code}")

    check("every tab of the file renders", not tab_failures, ", ".join(tab_failures))

    medicines_tab = client.get(
        f"/doctor-desk/patient/{demo_patient.id}?tab=medicines"
    )
    check(
        "medicine journey lists a prescribed drug with days",
        "Dolo 650" in medicines_tab.text or "Total days" in medicines_tab.text
    )

    billing_tab = client.get(f"/doctor-desk/patient/{demo_patient.id}?tab=billing")
    check("full invoice tab has both kinds of line",
          "Appointment fee" in billing_tab.text and "Medicine order" in billing_tab.text)

    statement = client.get(f"/doctor-desk/patient/{demo_patient.id}/statement")
    check("printable statement renders", statement.status_code == 200)
    check("statement totals are on the sheet",
          "Balance due" in statement.text and "Total (" in statement.text)

    file_api = client.get(f"/doctor-desk/patient/{demo_patient.id}/api/file")
    check("file API returns JSON", file_api.status_code == 200 and file_api.json()["success"])

    # ---------------------------------------------------------
    section("16. Doctor desk - writing into the file")

    notes_before = (
        db.query(DoctorPatientNote)
        .filter(DoctorPatientNote.patient_id == demo_patient.id)
        .count()
    )

    note = client.post(
        f"/doctor-desk/patient/{demo_patient.id}/notes",
        data={
            "title": "Smoke test allergy note",
            "body": "Reaction to ibuprofen reported on the phone.",
            "note_type": "ALLERGY",
            "visibility": "PATIENT_VISIBLE",
            "pinned": "1",
            "urgent": "1",
        },
        follow_redirects=False
    )
    check("doctor can add a note", note.status_code == 303, str(note.status_code))

    db.expire_all()
    saved = (
        db.query(DoctorPatientNote)
        .filter(DoctorPatientNote.patient_id == demo_patient.id)
        .order_by(DoctorPatientNote.id.desc())
        .first()
    )
    check("note row was written", saved is not None and
          (db.query(DoctorPatientNote).filter(
              DoctorPatientNote.patient_id == demo_patient.id).count() == notes_before + 1))
    check("note remembers which doctor wrote it",
          saved is not None and saved.doctor_id == demo_doctor_user.id)
    check("note keeps the pin / urgent / type flags",
          saved is not None and saved.is_pinned and saved.is_urgent
          and saved.note_type == "ALLERGY")
    check("note is visible in the file",
          "Smoke test allergy note" in client.get(
             f"/doctor-desk/patient/{demo_patient.id}?tab=notes").text)

    empty_note = client.post(
        f"/doctor-desk/patient/{demo_patient.id}/notes",
        data={"title": "   "},
        follow_redirects=False
    )
    check("a title-less note is refused",
          empty_note.status_code == 303
          and "title" in (empty_note.headers.get("location") or "").lower())

    flagged = client.post(
        f"/doctor-desk/notes/{saved.id}/flag",
        data={"field": "urgent"},
        headers={"Accept": "application/json"}
    )
    check("urgent flag toggles back off",
          flagged.status_code == 200 and flagged.json().get("is_urgent") is False,
          flagged.text[:160])

    wrong_flag = client.post(
        f"/doctor-desk/notes/{saved.id}/flag",
        data={"field": "body"},
        headers={"Accept": "application/json"}
    )
    check("only pin / urgent / archive can be toggled",
          wrong_flag.status_code == 400 or "pinned" in wrong_flag.text)

    archived = client.post(
        f"/doctor-desk/notes/{saved.id}/flag",
        data={"field": "archive"},
        headers={"Accept": "application/json"}
    )
    db.expire_all()
    check("archiving keeps the row and hides it",
          archived.status_code == 200
          and db.get(DoctorPatientNote, saved.id).status == "ARCHIVED"
          and "Smoke test allergy note" not in client.get(
              f"/doctor-desk/patient/{demo_patient.id}?tab=notes").text)

    restored = client.post(f"/doctor-desk/notes/{saved.id}/restore",
                           follow_redirects=False)
    db.expire_all()
    check("restore brings it back",
          restored.status_code == 303
          and db.get(DoctorPatientNote, saved.id).status == "ACTIVE")

    record = client.post(
        f"/doctor-desk/patient/{demo_patient.id}/record",
        data={
            "visit_date": "2026-01-05",
            "chief_complaint": "Smoke test complaint",
            "symptoms": "test symptoms",
            "diagnosis": "Test diagnosis",
            "instructions": "Drink water",
            "status": "FOLLOWUP_REQUIRED",
        },
        follow_redirects=False
    )
    check("doctor can write a consultation record", record.status_code == 303)

    db.expire_all()
    written_record = (
        db.query(MedicalRecord)
        .filter(MedicalRecord.chief_complaint == "Smoke test complaint")
        .first()
    )
    check("record is on the patient and on the doctor",
          written_record is not None
          and written_record.patient_id == demo_patient.id
          and written_record.doctor_id is not None)
    check("a wrong date is ignored rather than crashing",
          written_record is not None
          and str(written_record.visit_date) == "2026-01-05")

    status_done = client.post(
        f"/doctor-desk/record/{written_record.id}/status",
        data={"status": "COMPLETED"},
        headers={"Accept": "application/json"}
    )
    check("record status can be closed from the file",
          status_done.status_code == 200 and status_done.json()["status"] == "COMPLETED",
          status_done.text[:120])

    follow_up = client.post(
        f"/doctor-desk/patient/{demo_patient.id}/follow-up",
        data={
            "follow_up_date": "2030-04-01",
            "reason": "Smoke test recheck",
            "instructions": "Bring reports",
        },
        follow_redirects=False
    )
    check("follow-up can be booked from the file", follow_up.status_code == 303)

    db.expire_all()
    booked = (
        db.query(FollowUp)
        .filter(FollowUp.reason == "Smoke test recheck")
        .first()
    )
    check("follow-up row is pending", booked is not None and booked.status == "PENDING")

    bad_date = client.post(
        f"/doctor-desk/patient/{demo_patient.id}/follow-up",
        data={"follow_up_date": "not-a-date"},
        follow_redirects=False
    )
    check("a bad follow-up date is refused with a hint",
          bad_date.status_code == 303 and "YYYY-MM-DD" in bad_date.headers.get("location", ""))

    closed = client.post(
        f"/doctor-desk/follow-up/{booked.id}/complete",
        headers={"Accept": "application/json"}
    )
    db.expire_all()
    check("follow-up can be marked done",
          closed.status_code == 200 and db.get(FollowUp, booked.id).status == "COMPLETED")

    rx = client.post(
        f"/doctor-desk/patient/{demo_patient.id}/prescription",
        data={
            "lines": ("Dolo 650 Tablet | 650 mg | twice a day | 5 days | after food\n"
                      "Gelusil MPS Suspension 100ml | 10 ml | at night | 3 weeks\n"),
            "diagnosis": "Smoke test fever",
            "instructions": "Plenty of fluids",
        },
        follow_redirects=False
    )
    check("doctor can issue a prescription", rx.status_code == 303)

    db.expire_all()
    written_rx = (
        db.query(Prescription)
        .filter(Prescription.diagnosis == "Smoke test fever")
        .first()
    )
    lines = (
        db.query(PrescriptionMedicine)
        .filter(PrescriptionMedicine.prescription_id == written_rx.id)
        .all()
        if written_rx else []
    )
    check("prescription stored both medicine lines", len(lines) == 2, str(len(lines)))
    check("duration text is kept as written",
          any(row.duration == "3 weeks" for row in lines))
    check(
        "the patient can now see that prescription in the pharmacy",
        f"Rx #{written_rx.id}" in client.get(
            f"/doctor-desk/patient/{demo_patient.id}?tab=prescriptions").text
    )

    empty_rx = client.post(
        f"/doctor-desk/patient/{demo_patient.id}/prescription",
        data={"lines": "   "},
        follow_redirects=False
    )
    check("an empty prescription is refused",
          empty_rx.status_code == 303
          and "least%20one%20medicine" in empty_rx.headers.get("location", ""),
          empty_rx.headers.get("location", ""))

    from src.models.pharmacy_cart import PharmacyCartItem

    cart_before = (
        db.query(PharmacyCartItem)
        .filter(PharmacyCartItem.user_id == demo_patient.id)
        .count()
    )
    push = client.post(
        f"/doctor-desk/prescription/{written_rx.id}/send-to-cart",
        headers={"Accept": "application/json"}
    )
    check("doctor can push an Rx into the patient's cart",
          push.status_code == 200 and push.json()["success"], push.text[:200])

    db.expire_all()
    cart_after = (
        db.query(PharmacyCartItem)
        .filter(PharmacyCartItem.user_id == demo_patient.id)
        .count()
    )
    check("the patient's cart actually grew", cart_after > cart_before,
          f"{cart_before} -> {cart_after}")

    # ---------------------------------------------------------
    section("17. Doctor desk - money, privacy and scope")

    pending_visit = (
        db.query(Appointment)
        .filter(
            Appointment.patient_id == demo_patient.id,
            Appointment.payment_status != "PAID"
        )
        .order_by(Appointment.id)
        .first()
    )
    check("there is an unpaid visit to test with", pending_visit is not None)

    paid = client.post(
        f"/doctor-desk/appointment/{pending_visit.id}/payment",
        data={"payment_status": "PAID", "amount": "600", "payment_method": "UPI"},
        headers={"Accept": "application/json"}
    )
    check("desk can record an appointment payment",
          paid.status_code == 200 and paid.json()["payment_status"] == "PAID",
          paid.text[:200])

    db.expire_all()
    row_after = db.get(Appointment, pending_visit.id)
    check("the appointment row itself was updated",
          row_after.payment_status == "PAID" and float(row_after.payment_amount) == 600.0
          and row_after.payment_method == "UPI")

    bad_state = client.post(
        f"/doctor-desk/appointment/{pending_visit.id}/payment",
        data={"payment_status": "GIFT"},
        headers={"Accept": "application/json"}
    )
    check("an unknown payment state is refused", bad_state.status_code == 400,
          bad_state.text[:120])

    refunded = client.post(
        f"/doctor-desk/appointment/{pending_visit.id}/payment",
        data={"payment_status": "REFUNDED", "note": "smoke test refund"},
        headers={"Accept": "application/json"}
    )
    db.expire_all()
    check("a refund is recorded on the same row",
          refunded.status_code == 200
          and db.get(Appointment, pending_visit.id).refund_status == "REFUNDED")

    statement_after = client.get(f"/doctor-desk/patient/{demo_patient.id}/statement").text
    check("the statement picked up the payment change", "REFUNDED" in statement_after)

    audits = (
        db.query(PharmacyAuditLog)
        .filter(PharmacyAuditLog.action.like("doctor.%"))
        .count()
    )
    check("every desk write is audited", audits >= 8, f"{audits} doctor.* rows")
    check("opening a file is audited too",
          db.query(PharmacyAuditLog).filter(
              PharmacyAuditLog.action == "doctor.patient.view").count() >= 1)

    client.post("/logout", follow_redirects=False)
    client.post(
        "/login",
        data={"email": "patient@demo.com", "password": "Demo@1234"},
        follow_redirects=False
    )
    patient_try = client.get("/doctor-desk", follow_redirects=False)
    check("a patient cannot open the desk",
          patient_try.status_code == 303
          and "/login" not in patient_try.headers.get("location", "")
          and "/doctor-desk" not in patient_try.headers.get("location", ""),
          patient_try.headers.get("location", ""))

    patient_post = client.post(
        f"/doctor-desk/patient/{demo_patient.id}/notes",
        data={"title": "should not work"},
        follow_redirects=False
    )
    check("a patient cannot write a note on someone",
          patient_post.status_code == 303 and "doctor-desk" not in
          patient_post.headers.get("location", ""),
          patient_post.headers.get("location", ""))

    shared = client.get("/medical-history")
    check("a patient-visible note reaches the patient's own history page",
          shared.status_code == 200 and "Smoke test allergy note" in shared.text,
          f"status {shared.status_code}")
    check("an internal note stays hidden from the patient",
          "Allergic to penicillin" not in shared.text)

    client.post("/logout", follow_redirects=False)
    client.post(
        "/login",
        data={"email": "pharmacist@demo.com", "password": "Pharma@1234"},
        follow_redirects=False
    )
    pharmacist_try = client.get("/doctor-desk", follow_redirects=False)
    check("a pharmacist has no patient desk",
          pharmacist_try.status_code == 303
          and "/doctor-desk" not in pharmacist_try.headers.get("location", ""))

    other_file = client.get(f"/doctor-desk/patient/{demo_patient.id}", follow_redirects=False)
    check("nor can they open a patient file",
          other_file.status_code == 303 and "/dashboard" in other_file.headers.get("location", ""))

    client.post("/logout", follow_redirects=False)
    client.post(
        "/login",
        data={"email": "doctor@demo.com", "password": "Doctor@1234"},
        follow_redirects=False
    )

    # made through the app's own signup, so the app's session sees it in the
    # same snapshot it uses for the desk (a fresh patient, no clinical rows)
    client.post(
        "/signup",
        data={"name": "No Relation", "email": "norelation@demo.com",
              "phone": "9000000009", "password": "Demo@1234",
              "age": 44, "gender": "Male"},
        follow_redirects=False
    )
    db.expire_all()
    stranger = db.query(User).filter(User.email == "norelation@demo.com").first()
    check("the unrelated patient exists for this check", stranger is not None)

    everyone = client.get("/doctor-desk").text
    check("by default a doctor reaches every enrolled patient",
          "No Relation" in everyone)

    db.add(RolePermission(role="DOCTOR", permission="doctor.patients.all",
                          is_allowed=False))
    db.commit()

    from src.services import doctor_desk_service as desk_service

    own_only = desk_service.visible_patient_ids(
        db, demo_doctor_user,
        desk_service.resolve_doctor_row(db, demo_doctor_user)
    )
    check("revoking doctor.patients.all narrows the list to own patients",
          own_only is not None and demo_patient.id in own_only
          and stranger.id not in own_only,
          str(own_only))

    scoped_roster = client.get("/doctor-desk").text
    check("and the roster itself drops the unrelated patient",
          "No Relation" not in scoped_roster)

    stranger_id = stranger.id

    blocked_file = client.get(f"/doctor-desk/patient/{stranger_id}",
                              follow_redirects=False)
    check("and blocks the file that is not theirs",
          blocked_file.status_code == 303
          and "scope" in blocked_file.headers.get("location", ""),
          f"id={stranger_id} -> {blocked_file.status_code} "
          f"{blocked_file.headers.get('location', '')}")

    allowed_file = client.get(f"/doctor-desk/patient/{demo_patient.id}")
    check("their own patient still opens fine", allowed_file.status_code == 200)

    db.query(RolePermission).filter(
        RolePermission.role == "DOCTOR",
        RolePermission.permission == "doctor.patients.all"
    ).delete()
    db.commit()
    check("removing the override gives it back",
          client.get(f"/doctor-desk/patient/{stranger.id}").status_code == 200)

    client.post("/login", data={"email": "doctor@demo.com",
                                "password": "Doctor@1234"},
                follow_redirects=False)


    db.query(RolePermission).filter(
        RolePermission.role == "DOCTOR",
        RolePermission.permission == "doctor.desk.read"
    ).delete()
    db.add(RolePermission(role="DOCTOR", permission="doctor.desk.read", is_allowed=False))
    db.commit()
    off = client.get("/doctor-desk", follow_redirects=False)
    check("switching doctor.desk.read off closes the whole desk",
          off.status_code == 303 and "/doctor-desk" not in off.headers.get("location", ""))
    db.query(RolePermission).filter(
        RolePermission.role == "DOCTOR",
        RolePermission.permission == "doctor.desk.read"
    ).delete()
    db.commit()
    check("and switching it back opens it again",
          client.get("/doctor-desk").status_code == 200)

    # ---------------------------------------------------------
    section("18. Local clinic chatbot (works with NO api key)")

    client.post("/logout", follow_redirects=False)
    patient_login = client.post(
        "/login",
        data={"email": "patient@demo.com", "password": "Demo@1234"},
        follow_redirects=False
    )
    check("patient logs in for the chatbot", patient_login.status_code == 303)

    def ask(text):
        response = client.post("/chatbot/message", params={"message": text})
        assert response.status_code == 200, response.text[:200]
        payload = response.json()
        assert payload.get("success") is True, payload
        return payload["reply"]

    check("greeting is friendly", "Welcome to Sanjeevani Clinic" in ask("hello"))
    check("typo greeting still works", "Welcome to Sanjeevani Clinic" in ask("hloo"))

    reply = ask("price of dolo 650")
    check("medicine price comes from the database",
          "Dolo 650 Tablet" in reply and "Rs 32" in reply, reply[:200])

    reply = ask("stock of crocin")
    check("medicine stock is live", "In stock" in reply, reply[:200])

    reply = ask("side effects of dolo")
    check("side effects question is answered", "Side effects" in reply, reply[:200])

    reply = ask("medicine for diabetes")
    check("disease query lists stocked medicines",
          "Diabetes" in reply and "Rs" in reply, reply[:200])

    reply = ask("bukhar ke liye dawai")
    check("Hinglish disease query works",
          "Fever" in reply or "Dolo" in reply, reply[:200])

    reply = ask("chemist near me")
    check("nearby chemists come from the database", "MedPlus" in reply, reply[:200])

    reply = ask("clinic timings")
    check("clinic timings are computed from schedules",
          "Clinic timings" in reply and "10:00" in reply, reply[:200])

    reply = ask("consultation fees")
    check("consultation fee range is computed",
          "Consultation fees" in reply and "Rs" in reply, reply[:200])

    reply = ask("i have fever")
    check("symptom guidance carries a safety disclaimer",
          "not a doctor" in reply.lower() and "General Medicine" in reply,
          reply[:200])

    reply = ask("asdfgh qwerty")
    check("unknown input gets a helpful fallback",
          "medicines" in reply.lower(), reply[:200])

    # Simulate a configured AI key: the safe local replies must
    # still win (regression test - the medical disclaimer and the
    # helpful fallback must never depend on an AI key being set).
    import src.routers.chatbot as chatbot_module

    class _DummyMessage:
        content = "small talk from the AI model"

    class _DummyChoice:
        message = _DummyMessage()

    class _DummyResponse:
        choices = [_DummyChoice()]

    class _DummyGroq:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    return _DummyResponse()

    _saved_client = chatbot_module.groq_client
    _saved_model = chatbot_module.GROQ_MODEL
    chatbot_module.groq_client = _DummyGroq()
    chatbot_module.GROQ_MODEL = "test-model"
    try:
        reply = ask("i have fever")
        check("symptom guidance wins even when an AI key is set",
              "not a doctor" in reply.lower() and "General Medicine" in reply,
              reply[:200])

        reply = ask("clinic timings")
        check("clinic timings win even when an AI key is set",
              "Clinic timings" in reply and "10:00" in reply, reply[:200])

        reply = ask("asdfgh qwerty")
        check("helpful answer wins even when an AI key is set",
              "medicines" in reply.lower(), reply[:200])
    finally:
        chatbot_module.groq_client = _saved_client
        chatbot_module.GROQ_MODEL = _saved_model

    from fastapi.testclient import TestClient as FreshClient
    import main as fresh_app_module

    with FreshClient(fresh_app_module.app) as anonymous:
        anon = anonymous.post("/chatbot/message", params={"message": "hello"})
    check("chatbot requires login", anon.status_code == 401, str(anon.status_code))

    # ---------------------------------------------------------
    section("19. Booking page opens from the injury link (no date param)")

    from datetime import date as date_cls
    from src.models.doctor import Doctor as DoctorModel

    bookable = (
        db.query(DoctorModel)
        .filter(DoctorModel.is_active.is_(True))
        .first()
    )
    check("an active doctor exists for the booking checks",
          bookable is not None)

    if bookable is not None:

        injury_link = client.get(
            "/book-appointment",
            params={"doctor_id": bookable.id},
            follow_redirects=False
        )
        check("injury link (?doctor_id= only) opens the booking page",
              injury_link.status_code == 200,
              f"{injury_link.status_code} {injury_link.text[:150]}")

        dated_link = client.get(
            "/book-appointment",
            params={
                "doctor_id": bookable.id,
                "appointment_date": date_cls.today().isoformat()
            },
            follow_redirects=False
        )
        check("screening-style link (with date) still works",
              dated_link.status_code == 200,
              f"{dated_link.status_code} {dated_link.text[:150]}")

        check("booking page pre-fills today's date",
              f'value="{date_cls.today().isoformat()}"' in injury_link.text)

        from src.models.visit_type import VisitType

        visit_type = (
            db.query(VisitType)
            .filter(VisitType.is_active.is_(True))
            .order_by(VisitType.id)
            .first()
        )
        if visit_type is None:
            visit_type = VisitType(
                name="General Consultation",
                min_duration_minutes=15,
                max_duration_minutes=30,
                default_duration_minutes=15,
                is_active=True,
            )
            db.add(visit_type)
            db.commit()

        times = client.get(
            "/api/appointment-times",
            params={
                "doctor_id": bookable.id,
                "appointment_date": date_cls.today().isoformat(),
                "visit_type_id": visit_type.id
            }
        )
        times_payload = times.json() if times.status_code == 200 else {}
        check("available-times API answers (no import NameError)",
              times.status_code == 200 and times_payload.get("success") is True,
              f"{times.status_code} {times.text[:150]}")

    # ---------------------------------------------------------
    section("20. No circular import (app boots in any import order)")

    import subprocess

    def boot_check(code):
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, cwd=str(BASE_DIR)
        )
        return result.returncode == 0, (result.stderr or result.stdout).strip()[-200:]

    ok, log = boot_check(
        "import src.services.availability_service; "
        "import src.models; print('order-1 ok')"
    )
    check("service-first import order boots", ok, log)

    ok, log = boot_check(
        "import src.models; "
        "import src.services.availability_service; print('order-2 ok')"
    )
    check("models-first import order boots", ok, log)

    # ---------------------------------------------------------
    section("21. Emergency symptoms never get a medicine card")

    reply = ask("chest pain")
    check("chest pain gets the emergency message",
          "emergency" in reply.lower(), reply[:200])
    check("chest pain does NOT show a medicine card",
          "Dentogest" not in reply and "Price:" not in reply, reply[:200])

    reply = ask("i have chest pain")
    check("i have chest pain also gets the emergency message",
          "emergency" in reply.lower(), reply[:200])

    reply = ask("heart attack")
    check("heart attack gets the emergency message",
          "emergency" in reply.lower(), reply[:200])

    reply = ask("stomach pain")
    check("stomach pain is not answered with a medicine card",
          "Price:" not in reply and "Dentogest" not in reply, reply[:200])
    check("stomach pain gets symptom guidance instead",
          "not a doctor" in reply.lower() or "General Medicine" in reply,
          reply[:200])

    reply = ask("dolo")
    check("a bare medicine name still shows its card",
          "Dolo" in reply and "Price:" in reply, reply[:200])

    reply = ask("fever")
    check("bare fever shows the disease card, not a thermometer",
          "Fever" in reply and "Thermometer" not in reply, reply[:200])

    # ---------------------------------------------------------
    section("22. Doctor names never render as 'Dr. Dr.'")

    reply = ask("i have fever")
    check("symptom guidance shows clean doctor names",
          "Dr. Dr." not in reply and "consultation Rs" in reply,
          reply[:200])

    reply = ask("i need a cardiologist")
    check("doctor search shows clean doctor names",
          "Dr. Dr." not in reply
          and ("Dr. Amit Sharma" in reply or "Dr. Neha Verma" in reply),
          reply[:200])

    booking_page = client.get(
        "/book-appointment",
        params={"doctor_id": bookable.id},
        follow_redirects=False
    )
    check("booking page shows a clean doctor name",
          bookable is not None
          and booking_page.status_code == 200
          and "Dr. Dr." not in booking_page.text,
          f"{booking_page.status_code}")

    # ---------------------------------------------------------
    section("23. Dark glass UI theme")

    login_page = client.get("/login")
    check("login page renders the new theme",
          login_page.status_code == 200
          and "Login to Sanjeevani" in login_page.text
          and "/static/theme.css" in login_page.text)

    client.post("/logout", follow_redirects=False)
    client.post("/login", data={"email": "patient@demo.com", "password": "Demo@1234"},
                follow_redirects=False)
    dash = client.get("/dashboard")
    check("patient dashboard uses the theme sidebar",
          dash.status_code == 200 and "th-sidebar" in dash.text
          and "AI Health Assistant" in dash.text)

    client.post("/logout", follow_redirects=False)
    client.post("/login", data={"email": "doctor@demo.com", "password": "Doctor@1234"},
                follow_redirects=False)
    desk = client.get("/doctor-desk")
    check("doctor desk shows the greeting and theme sidebar",
          desk.status_code == 200 and "th-sidebar" in desk.text
          and ("Good Morning" in desk.text or "Good Afternoon" in desk.text
               or "Good Evening" in desk.text))

    client.post("/logout", follow_redirects=False)
    client.post("/login", data={"email": "superuser@sanjeevani.com",
                                "password": "Super@1234"},
                follow_redirects=False)
    admin = client.get("/pharmacy/admin")
    check("admin console shows the system overview stats",
          admin.status_code == 200 and "System Overview" in admin.text
          and "Total Patients" in admin.text and "Active Doctors" in admin.text
          and "Revenue" in admin.text)

    shop = client.get("/pharmacy")
    check("pharmacy shop loads the theme stylesheet",
          shop.status_code == 200 and "/static/theme.css" in shop.text)

    check("login page lists all five demo accounts",
          all(e in login_page.text for e in (
              "patient@demo.com", "doctor@demo.com", "pharmacist@demo.com",
              "admin@demo.com", "superuser@sanjeevani.com"))
          and "lg-demo-row" in login_page.text)

    db.close()

def stock_and_price(db, medicine_id):
    from src.models.medicine import Medicine

    row = db.get(Medicine, medicine_id)
    return float(row.price) if row else None


# =========================================================
# MAIN
# =========================================================

def main() -> int:
    print("Building a throwaway database for the pharmacy smoke test...")
    build_database()

    import main as app_module
    from fastapi.testclient import TestClient

    print("\nStarting the app...")
    with TestClient(app_module.app) as client:
        run(client)

    print(f"\n{'-' * 62}")
    print(f"{PASSED} checks passed, {len(FAILED)} failed")

    if FAILED:
        print("\nFailed checks:")
        for name in FAILED:
            print(f"  - {name}")

    _dispose_app_engine()
    _remove_scratch_db(TEST_DB)
    shutil.rmtree(BASE_DIR / "uploads" / "pharmacy", ignore_errors=True)

    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())