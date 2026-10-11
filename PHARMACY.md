# 💊 Pharmacy module — Sanjeevani Clinic

Poora feature: dukaan (catalog by disease, rate, photo) → cart → payment
(cash / online) → **CONFIRMED** order → doctor ki prescription se buy →
out-of-stock ho to **nearby chemist (Google Maps + SQL)** → aur upar
**Super User** console with role based access, audit log aur rollback/restore.
Upar se ek **Doctor Desk** (`/doctor-desk`) bhi add hua - doctor ko har enrolled
patient ka pura file dikhta hai, aur wo usme likh bhi sakta hai. Detail:
`DOCTOR_DESK.md`. (That is why the test count below is 173, not 103.)

Neeche exactly kaunsi files/folders add hui, kaunsi 4 files edit huwi, kaunse
commands chalane hain — sab verified hai (`python test_pharmacy.py` → **103
checks, 0 failed** on this build).

---

## 1. One-shot install (copy paste)
> **Also new:** the doctor desk (`/doctor-desk`) reuses this module's RBAC, audit
> log, catalog matching and cart services, and adds one table
> (`doctor_patient_notes`). See `DOCTOR_DESK.md` for the full list and workflow.


Terminal / PowerShell, repo ke root me:

```bash
git pull                                  # already-pulled files ke liye
python -m venv .venv                      # (already bana ho to skip)

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt             # no new package needed
python seed_pharmacy.py                     # diseases + 111 medicines + shops + logins
python test_pharmacy.py                     # 173 checks, must end with "0 failed"
uvicorn main:app --reload                   # or ./start.sh  /  start.bat
```

Open: <http://127.0.0.1:8000/pharmacy> · admin: <http://127.0.0.1:8000/pharmacy/admin>
Your existing project keeps running exactly as before — the pharmacy is additive.

If you use MySQL (your normal setup): keep `.env` as it is; the pharmacy tables
are created on the next app start (`Base.metadata.create_all`). Optional review
DDL: `pharmacy_setup.sql` (generated from the models, safe to run twice).

### Logins the seed creates

| Role | Email | Password | Kya kar sakta hai |
|---|---|---|---|
| `SUPERUSER` | `superuser@sanjeevani.com` | `Super@1234` | sab kuch + roles + rollback |
| `ADMIN` | `admin@demo.com` | `Admin@1234` | sab kuch **except** role editing |
| `PHARMACIST` | `pharmacist@demo.com` | `Pharma@1234` | orders, stock, nearby shops |
| `DOCTOR` | `doctor@demo.com` | `Doctor@1234` | pharmacy + catalog read |
| `PATIENT` | `patient@demo.com` | `Demo@1234` | browse, cart, buy, own orders |

(`patient@demo.com` / `admin@demo.com` already existed — only the role field is
refreshed, passwords are unchanged.)

---

## 2. NEW files / folders (58 files, 55 new)

```
├── seed_pharmacy.py                     ← data: 32 diseases, 111 medicines + photos,
│                                          partner chemists, 5 role logins, sample Rx
├── test_pharmacy.py                     ← 103-check end-to-end smoke test (throwaway DB)
├── database_setup_with_pharmacy.sql     ← ONE safe Workbench script: 15 clinic +
│                                          12 pharmacy tables + demo data, no DROP,
│                                          re-runnable (regenerate: build_workbench_sql.py)
├── pharmacy_setup.sql                    ← only the 12 pharmacy CREATE TABLEs
├── workbench_pharmacy.sql                ← THE FILE TO PASTE IN WORKBENCH: 12 tables +
│                                          5 logins, preflight guard, no DROP, re-runnable
├── workbench_all_features.sql            ← ALL 27 tables (existing clinic + every new
│                                          feature) in one paste, no DROP, re-runnable
├── mysql_upgrade_existing_db.sql         ← smallest paste for a database that already
│                                          has the older tables: desk table + role table +
│                                          guarded treatment_reviews.updated_at + SUPERUSER
├── pharmacy_seed.sql                     ← only the pharmacy INSERTs
├── build_workbench_sql.py                ← regenerates the 5 .sql files above
├── test_pharmacy_mysql.py                ← 52 checks against your REAL MySQL
├── pharmacy_schema_export.py             ← regenerates pharmacy_setup.sql
├── PHARMACY.md                           ← ye file

src/
├── models/                              ← 11 NEW tables (SQLAlchemy + SQL both)
│   ├── disease.py                         diseases (filter chips on /pharmacy)
│   ├── medicine.py                        medicines: rate, MRP, stock, photo, Rx flag
│   ├── medicine_disease.py                medicine ↔ disease (many-to-many)
│   ├── pharmacy_cart.py                   cart, stored per user in SQL
│   ├── pharmacy_order.py                   orders + order items (price frozen at buy)
│   ├── nearby_pharmacy.py                  partner chemists + their stock
│   ├── pharmacy_audit_log.py               append-only audit trail
│   ├── pharmacy_snapshot.py                rollback/restore snapshots
│   └── role_permission.py                  role → permission overrides (RBAC)
│
├── security/
│   └── rbac.py                            roles, 18 permissions, matrix, guards
│
├── services/
│   ├── pharmacy_catalog_service.py        list/filter/search, Rx-name matching, admin CRUD
│   ├── pharmacy_cart_service.py           cart rules: stock, Rx-required, price copy
│   ├── pharmacy_order_service.py          checkout, payment confirm, cancel/refund, stock move
│   ├── pharmacy_nearby_service.py         SQL partner stock + Google Places import
│   ├── pharmacy_payment_service.py        cash / UPI-QR / Razorpay signature verify
│   ├── pharmacy_audit_service.py          log_activity(), filters, CSV
│   └── pharmacy_snapshot_service.py       snapshot, preview, restore, prune, bulk ops
│
├── routers/
│   ├── pharmacy.py                        patient pages + JSON API  (/pharmacy…)
│   └── pharmacy_admin.py                   super user console + API (/pharmacy/admin…)

templates/
├── pharmacy.html                          shop: disease chips, search, rate, photo, add/buy
├── pharmacy_cart.html                       cart + payment method + place order
├── pharmacy_prescription.html              doctor ke tablets → price → buy
├── pharmacy_orders.html                     my orders + status
├── pharmacy_order.html                      order detail: CONFIRMED, pay, cancel, refund
├── pharmacy_receipt.html                    printable bill
├── pharmacy_nearby.html                      emergency: kaunsi shop pe available hai
├── pharmacy_admin.html                        6-tab admin console (orders/catalog/nearby/audit/access/snapshots)
└── partials/
    ├── pharmacy_head.html                    shared <head> (css/js)
    └── pharmacy_nav.html                       shared navbar, cart badge, role-aware links

static/
├── pharmacy.css                              one stylesheet for all pharmacy pages
├── pharmacy.js                                add-to-cart / pay / admin actions (delegation)
└── images/pharmacy/
    ├── tablet.jpg  capsule.jpg  syrup.jpg  drops.jpg
    ├── ointment.jpg  injection.jpg  powder.jpg  first-aid.jpg     ← product photos
    └── tablet.svg … not-found.svg                                   ← fallbacks (no photo)
```

> `git status` after `git add -A` is the authoritative list: **58 files
> changed, 55 added** — the tree above is that list, grouped.

## 3. EXISTING files edited (only 4 + docs)

| File | What changed | Why |
|---|---|---|
| `main.py` | 3 imports + 2 `include_router` + `import src.models` | registers `/pharmacy` and `/pharmacy/admin`, and makes sure **every** table is known to `create_all()` |
| `src/models/__init__.py` | imports all 16 clinic models + 12 pharmacy models, adds `__all__` | fixes a real bug: on a **fresh** database `create_all()` failed with `NoReferencedTableError: appointments.slot_id → doctor_slots` because the slot/schedule/notification models were only imported by routers. Seeds/scripts now always see the full schema |
| `src/config.py` | `SQLITE_DB_PATH` honours an env var | lets `test_pharmacy.py` run on a throwaway DB instead of your `sanjeevani_clinic.db` |
| `templates/dashboard.html` | 2 new quick-cards: **Pharmacy** and **My Medicine Orders** | entry point from your existing dashboard |
| `.env.example` | new section 5: `GOOGLE_MAPS_API_KEY`, `CLINIC_LATITUDE/LONGITUDE/CITY`, `RAZORPAY_KEY_ID/SECRET`, `PHARMACY_UPI_ID`, `SQLITE_DB_PATH` | all optional — app works with none of them |
| `sanjeevani_clinic.db` | got the pharmacy tables + seed data (binary) | your local demo DB now includes the module. `git checkout sanjeevani_clinic.db` if you want the old file back |

`requirements.txt` needs **no change**: no new package is used (Google calls go
through `urllib`, HMAC through `hashlib`).

---

## 4. Requirement → where it is implemented

| Aapki requirement | Kahan bana |
|---|---|
| Saari tablets, disease ke hisaab se | `/pharmacy` — disease chips (`diseases` + `medicine_diseases`), search by salt/brand, form + price sort, 111 medicines seeded across 32 conditions |
| Rate unke samne | `medicines.price` + `mrp` with "9% off" badge; `Rs 32.00` style everywhere (`pharmacy_payment_service.format_inr`) |
| Photo bhi | `medicines.image_path` → `static/images/pharmacy/*.jpg` (per form), `image_url` for a real product photo, admin **Upload photo** endpoint, `not-found.svg` fallback |
| Cart | `/pharmacy/cart`, table `pharmacy_cart_items` (SQL, per user) — quantity stepper, remove, empty, price-change warning |
| Payment option wahin | CASH (pay at counter) / ONLINE (UPI-QR) radios on the cart page; Razorpay auto-detected from `.env` |
| Buy ke baad **CONFIRMED** | `pharmacy_orders.status = CONFIRMED`, big green banner + progress timeline on `/pharmacy/order/{no}` |
| Cash + online dono | `payment_method` + `payment_status` (PENDING/PAID/FAILED/REFUNDED), staff "Cash received" button |
| Available nahi to **nearby shop, Google API, emergency** | `/pharmacy/nearby` + `pharmacy_nearby_service.py`: Google Places Text Search + Details when a key exists, red **Find nearby** button on every out-of-stock card, `is_emergency` flag on the order |
| **SQL se connected** (ye zaroori tha) | `nearby_pharmacies` + `nearby_pharmacy_stocks` — partner chemists aur unka stock DB me; Google results bhi wahi cache hote hain, so offline bhi chalta hai |
| Doctor ne jo tablets di wo yaha show + buy | `/pharmacy/prescriptions`: existing `prescriptions`/`prescription_medicines` rows are matched to the catalog (name/salt fuzzy match) with price + stock + "Add"/"Add all available"; **Add to cart** stores `source=PRESCRIPTION` |
| Super user, saari permission | `src/security/rbac.py`: `SUPERUSER = *`; 24 named permissions (17 pharmacy + 7 doctor desk); `/pharmacy/admin?tab=access` matrix |
| Role based access | 6 roles (`PATIENT/DOCTOR/PHARMACIST/STAFF/ADMIN/SUPERUSER`) checked in **every** route + `role_permissions` table for live overrides (no redeploy) - 24 permission keys, 7 of them for the doctor desk |
| Audit logs | `pharmacy_audit_logs`: who/what/when/IP/UA/path + **before/after JSON**; viewer at `?tab=audit`; CSV export; append-only (no edit/delete API) |
| Controlled rollback / restore | `pharmacy_snapshots`: snapshot → `preview` (row-level diff, writes nothing) → restore **only with matching sha256 checksum**; automatic `PRE_RESTORE` undo point; auto snapshots before bulk price change / stock import / delete; pinned snapshots survive prune |

---

## 5. Routes (what you can call)

Pages: `/pharmacy` · `/pharmacy/cart` · `/pharmacy/prescriptions` ·
`/pharmacy/orders` · `/pharmacy/order/{order_no|id}` ·
`/pharmacy/order/{no}/receipt` · `/pharmacy/nearby` · `/pharmacy/admin?tab=…`

Patient JSON API:

```
GET  /pharmacy/api/medicines?q=para
POST /pharmacy/api/cart/add                medicine_id, quantity
POST /pharmacy/api/cart/add-prescription   prescription_medicine_id, quantity
POST /pharmacy/api/prescriptions/add-all   prescription_id
POST /pharmacy/api/cart/quantity           item_id, quantity
POST /pharmacy/api/cart/remove | /clear    item_id
GET  /pharmacy/api/cart
POST /pharmacy/checkout            (form)  payment_method, delivery_type, address, phone, notes, emergency
POST /pharmacy/api/checkout        (same, JSON)
POST /pharmacy/api/buy-now                 medicine_id, quantity, payment_method
POST /pharmacy/api/order/{id}/pay          (+ razorpay_* fields when a gateway is configured)
POST /pharmacy/api/order/{id}/cancel       reason
POST /pharmacy/api/order/{id}/mark-paid    staff
GET  /pharmacy/api/nearby?medicine_id=1&lat=&lng=&radius=
```

Admin JSON API (`/pharmacy/admin/api/…`, every route permission-checked):

```
GET  /orders?status=&payment=&search=&urgent=      POST /orders/{id}/fulfil  action=mark_paid|handed_over|cancel|refund
GET  /orders/export.csv
GET  /medicines?q=&disease=&low_stock=              POST /medicines
POST/PUT /medicines/{id}                            POST /medicines/{id}/stock   change, mode=delta|set
POST /medicines/{id}/toggle                        DELETE /medicines/{id}       confirm=DELETE
POST /medicines/{id}/image                          (multipart upload → static/images/pharmacy/custom/)
POST /catalog/bulk-price   percent|flat, disease    POST /catalog/stock-import   csv_text, mode=set|delta
POST /nearby/shops · /nearby/shops/{id}/toggle · /nearby/stock · /nearby/sync-google
GET  /audit?...  ·  /audit/export.csv
POST /roles/permission  role, permission, allowed   POST /roles/reset
POST /users/{id}/role   role, is_active             (SUPERUSER only for SUPERUSER changes)
GET  /snapshots · POST /snapshots · /snapshots/{id}/pin · /snapshots/prune
GET  /snapshots/{id}/preview · /snapshots/{id}/export.json
POST /snapshots/{id}/restore    checksum=<from preview>
```

---

## 6. Rules the code enforces (so nothing "silently" breaks)

* **Stock** — checkout is one transaction with a guarded
  `UPDATE medicines SET stock = stock - n WHERE stock >= n`; 0 rows affected →
  the whole order aborts with *"Only N packs left"*. Cancel/refund gives stock
  back **exactly once** (`pharmacy_orders.stock_adjusted`).
* **Prescription-only medicines** — `requires_prescription=True` can only enter
  the cart if the patient actually has a matching prescription line
  (`patient_has_valid_prescription`), otherwise 409 with a clear message.
* **Prices** — cart copies the price at add-time; checkout re-reads the live
  price and shows "price updated from X to Y" instead of surprising the
  patient. Order items store a **frozen copy** (name, rate, photo, Rx
  directions) so an old bill still prints what was actually paid — even after
  a catalog rollback.
* **Unmatched prescription lines** are never substituted with a random
  medicine: they are listed as "not stocked here" and pushed to the nearby
  search.
* **Payment** — the browser is never trusted: Razorpay mode verifies
  `HMAC_SHA256(order_id|payment_id)` with the server-side secret; without keys
  the simulated flow is explicitly labelled "Demo mode" in the UI.
* **Sessions** — `rbac.get_session_user()` re-reads the user from SQL on every
  request (a stale/edited session cookie cannot grant rights); inactive users
  are bounced.
* **Locked doors** — SUPERUSER can't be denied a permission in the matrix, a
  super user can't demote themselves while using that role, and only a super
  user can create/remove a super user.
* **Audit writes never roll back an order** (`log_activity` catches its own
  failures and logs to the app logger).

---

## 7. Rollback / restore, the intended workflow

1. `Pharmacy admin → Snapshots → Take snapshot now` before any risky bulk edit
   (scope: `PHARMACY` / `CATALOG` / `STOCK` / `ORDERS`).
2. Something went wrong? **Preview restore** → the page shows per table
   `+N new, -N removed, ~N modified` (nothing written yet).
3. Confirm → the app first captures the current state as `PRE_RESTORE`, then
   replays the snapshot rows, then writes a `CRITICAL` audit entry.
4. Wrong snapshot? Restore the undo point it just printed (`#N`). Pinned
   snapshots are never removed by **Prune old**.
5. Prefer a file backup? `export.json` of any snapshot downloads the exact
   bytes a restore would write.

Bulk price change, stock import and medicine **delete** all take an automatic
snapshot first (delete pins it; and if the medicine already appears in past
orders it is *hidden* instead of destroyed — invoices stay valid).

---

## 8. Optional keys (nothing breaks if you skip them)

| Key | Without it | With it |
|---|---|---|
| `GOOGLE_MAPS_API_KEY` | nearby page = partner chemists from SQL (works offline) | + live chemists, phone no., open-now; imported rows cached in `nearby_pharmacies` |
| `RAZORPAY_KEY_ID` + `RAZORPAY_KEY_SECRET` | UPI/QR simulated, order confirmed by "I have paid" | real Razorpay Checkout, signature verified server side |
| `CLINIC_LATITUDE/LONGITUDE/CITY` | Jaipur defaults (26.9124, 75.7873) | correct distance + search centre for your city |

---

## 9. Verified / not verified (honest list)

Ran on this build:

* `python check_all_features.py` → **319 checks passed, 0 failed** - the whole
  project cross-checked: every page per role, the link rules between features,
  orphan-row queries over every foreign key, and two end-to-end flows. It runs on
  its own throwaway database, so it never touches your data (`--live` = read-only
  on your real DB, `--html report.html` = printable)
* `python test_pharmacy.py` → **173 checks passed, 0 failed** (real HTTP + real
  SQL: catalog, cart, Rx rejection, cash + online checkout, stock moves,
  cancel/refund restore, prescription tab, nearby search, patient-blocked-from-
  admin, per-tab admin access, catalog CRUD, stock adjust, audit read/filter/CSV,
  snapshot → bulk change → preview → checksum-guard → **rollback restored the old
  price**, permission override actually locked the cart out then restored it,
  SUPERUSER guard rails, receipt, staff queue, hand-over, refund).
* Every pre-existing page (`/`, `/dashboard`, `/doctors`, `/appointments`,
  `/prescription`, `/chatbot`, …) still returns 200 — no route collisions.
* `test_password.py`, `test_schema.py`, `test_user_service.py` still pass.
* `python test_pharmacy_mysql.py` → 52 checks passed, 0 failed (needs MySQL;
  prints SKIP and exits 0 when it is not reachable, so it is safe to leave in
  the repo).
* `pharmacy_setup.sql` parses under a MySQL-dialect SQL parser (11 CREATE
  TABLE + USE + SET + a verification SELECT).

**MySQL, for real.** A MariaDB/MySQL server was started in the sandbox and the
whole stack was run against it: `database_setup_with_pharmacy.sql` executed
three times in a row (0 errors, identical row counts — idempotent), then
`python test_pharmacy_mysql.py` → **52 checks passed, 0 failed** on MySQL
(catalog read, purchase, stock move, cancel + stock back, all 6 admin tabs,
audit rows, snapshot → bulk price → preview → **rollback**). `seed_pharmacy.py`
was also run twice on MySQL (`0 added, 111 refreshed`).

That run found and fixed a real MySQL-only bug: `restore_snapshot()` used to
empty each table and re-insert every row. SQLite never enforces foreign keys,
so the tests passed — MySQL rejected it (`fk_…/medicine_diseases` and the order
items pointing at medicines), and the admin "Restore" button would have failed
on your machine with *"Restore failed and the transaction was rolled back"*.
The restore now (a) diffs rows instead of delete-all/insert-all, keeping ids
stable for anything outside the snapshot, and (b) switches
`SET FOREIGN_KEY_CHECKS` off around the write and always back on in a
`finally`.

Still not verified here: a live Google Maps / Razorpay call (no keys). Both
paths fail soft by design — the app logs the reason (`/health`, the nearby page)
instead of erroring.

---

## 10. Commit it

```bash
git add -A
git commit -m "Add pharmacy module: catalog by disease, cart, cash/UPI payment,
prescription buying, nearby-chemist emergency search, super user console with
RBAC + audit log + snapshot rollback"
git push origin main
```
