# Sanjeevani Clinic

An AI-assisted healthcare platform: FastAPI + MySQL + Jinja2 templates, plus a
scikit-learn ML pipeline for Covid screening triage.

Patients can sign up, browse 20 doctors, book / reschedule / cancel appointments
against real doctor schedules, keep medical history, upload medical reports,
get AI health screening and injury triage, chat with an AI assistant, and manage
prescriptions and treatment reviews.

There is also a full **pharmacy** (`/pharmacy`): medicines grouped by disease with
price and photo, a cart, cash / UPI payment, buying the tablets a doctor
prescribed, an emergency "which chemist near me has it" search (Google Maps +
partner shops stored in SQL), and a super user console with role based access,
an audit log and snapshot rollback. See **[PHARMACY.md](PHARMACY.md)**.

---

## ▶  Fastest way to run this project (extracted zip / fresh clone)

Nothing to configure — the app falls back to the bundled SQLite file
(`sanjeevani_clinic.db`, demo data included) when MySQL is not reachable, and
all pharmacy tables are created on first start.

```bash
# 1. from the project folder
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate        # macOS / Linux

# 2. install (no extra package needed for the pharmacy)
pip install -r requirements.txt

# 3. optional but recommended - fills the pharmacy catalog / chemists / logins
#    (the bundled .db is already seeded, so this only refreshes it)
python seed_pharmacy.py

# 4. prove the pharmacy + doctor desk work: 173 checks, must end with "0 failed"
python test_pharmacy.py
#    (on MySQL, also:  python test_pharmacy_mysql.py  -> 52 checks on the real DB)

# 5. prove BOTH halves work: the original clinic features AND the new ones.
#    One command, runs the project's own smoke scripts + the pharmacy suite +
#    the integration suite; ends with a summary table.
python verify_all.py

#    just the integration suite on its own (319 checks):
#    python check_all_features.py
#    write a printable report too:
python check_all_features.py --html check_report.html

# 6. run
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Open **http://127.0.0.1:8000** (clinic) — the pharmacy lives at
**/pharmacy**, its admin console at **/pharmacy/admin**.
If you want MySQL instead, open **`database_setup_with_pharmacy.sql`** in MySQL
Workbench (it adds the pharmacy without dropping anything), copy `.env.example`
to `.env`, set your password and `USE_SQLITE=false`. The app also creates the
pharmacy tables by itself on startup; `pharmacy_setup.sql` is that same DDL for
review, and `test_pharmacy_mysql.py` proves the MySQL path end to end.

---

---

## 🩺 Doctor Desk (`/doctor-desk`)

A doctor signs in on the **same login page** and lands on their own desk instead
of the patient dashboard. There they can open **any enrolled patient's complete
file** - and write into it.

* register: live search, 9 filter chips with counts, sorting, pagination; every
  row shows first visit, last visit (+ how long ago), how many visits, notes,
  Rx lines, billed / paid / due, and auto tags (`NEW`, `Follow-up overdue`,
  `Payment due`, `No review yet`, `No visit 90+d`, `Not your patient`)
* file (10 tabs): visits & payments · consultation notes · prescriptions ·
  medicines taken (which tablet, how many days, how many packs, from where,
  paid?) · full invoice (appointment fees **and** pharmacy orders in one ledger
  + item-by-item order lines + printable statement) · doctor notes ·
  patient reviews · uploaded reports + AI screening · one merged timeline
* writing: add note (pin / urgent / internal vs patient-visible), write a
  consultation record, book a follow-up, **issue a prescription** and push it
  into the patient's pharmacy cart, record / refund an appointment payment
* 12th table `doctor_patient_notes`; every read and write is audited
* 7 new permissions in `src/security/rbac.py` - admin can switch them off per
  role from Pharmacy admin → Access, no redeploy

Full list + workflow: **`DOCTOR_DESK.md`**

---

## What's in the box

| Path | What it is |
|---|---|
| `main.py` | FastAPI app — entry point, mounts all 14 routers |
| `database_setup.sql` | **Complete MySQL setup** — paste into MySQL Workbench and run |
| `steps.txt` | **Start-to-finish VS Code walkthrough** (venv → ML pipeline → run) |
| `MYSQL_SETUP.md` | MySQL-specific help and troubleshooting |
| `src/routers/` | HTTP layer — auth, profile, doctor, appointment, screening, … |
| `src/services/` | Business logic |
| `src/models/` | SQLAlchemy models (27 tables: 15 clinic + 12 pharmacy / doctor desk) |
| `src/components/` | ML pipeline: data ingestion → transformation → training |
| `src/pipeline/` | Training and prediction entry points |
| `notebook/data/covid_toy.csv` | Training dataset (100 rows, practice data) |
| `artifacts/` | Trained `model.pkl` + `preprocessor.pkl` — **not in git/zip**, run `python train_model.py` to build them; AI screening falls back to rule-based triage until they exist |
| `src/routers/pharmacy*.py` | Pharmacy shop, cart, checkout, nearby search + admin console |
| `src/security/rbac.py` | Roles and permissions (who may do what, everywhere) |
| `seed_pharmacy.py` | One command that fills the pharmacy: 32 diseases, 111 medicines, photos, partner chemists, demo logins |
| `test_pharmacy.py` | End-to-end smoke test for the pharmacy **and the doctor desk** (173 checks) |
| `check_all_features.py` | **Cross-check that every feature is connected** - 319 checks over pages, links, foreign keys, roles, schema-vs-code, the 2 new-feature flows and **43 end-to-end steps through the ORIGINAL clinic features** (`--html report.html`, `--live` = read-only run on the database in your `.env`) |
| `verify_all.py` | **One command that runs every check** - the project's own smoke scripts + the pharmacy suite (173) + the integration suite (319) + the MySQL suite (52) when `.env` says MySQL; prints a summary table, exits 1 if anything failed |
| `workbench_all_features.sql` | **The complete file to paste in MySQL Workbench** - all **27 tables** (15 clinic + 12 new: pharmacy, cart, orders, audit/snapshots, role matrix, doctor-desk notes) + the 5 demo logins + the clinic seed data, no DROP, re-runnable. The 111-medicine catalogue is loaded by `python seed_pharmacy.py` |
| `workbench_pharmacy.sql` | **The file to paste in MySQL Workbench** - 12 pharmacy tables + the 5 demo logins, no DROP, re-runnable |
| `mysql_upgrade_existing_db.sql` | **Paste this if your database already has the older pharmacy tables** - adds `doctor_patient_notes` + `role_permissions`, adds the `treatment_reviews.updated_at` column the old `database_setup.sql` forgot (guarded `ALTER`), and `INSERT IGNORE`s the SUPERUSER login. Deletes nothing |
| `database_setup_with_pharmacy.sql` | **One safe Workbench script** — 15 clinic + 12 pharmacy tables + demo data, no DROP, re-runnable |
| `pharmacy_seed.sql` | Just the pharmacy INSERTs (diseases, 111 medicines, chemists, logins, demo Rx) |
| `build_workbench_sql.py` | Regenerates both files above from the models + your seeded data |
| `test_pharmacy_mysql.py` | Runs 52 checks against your real MySQL database (SKIPs if MySQL is unreachable) |
| `PHARMACY.md` | Everything about the pharmacy module |
| `templates/`, `static/` | Frontend (Jinja2 + CSS) |

---

## Quick start

**1. Create the database.** Open `database_setup.sql` in MySQL Workbench and run
it (lightning-bolt button). It creates the 15 clinic tables, 20 doctors, 140
schedules, 5 visit types and two demo logins. The pharmacy adds 12 more tables
(`diseases`, `medicines`, `medicine_diseases`, `pharmacy_cart_items`,
`pharmacy_orders`, `pharmacy_order_items`, `nearby_pharmacies`,
`nearby_pharmacy_stocks`, `pharmacy_snapshots`, `pharmacy_audit_logs`,
`role_permissions`, `doctor_patient_notes`) — those are created automatically on
the next app start, or paste `workbench_pharmacy.sql` (same 12 tables + demo
data, no DROP) if you prefer to do it in Workbench.

**2. Set up Python.**

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
```

**3. Create your `.env`.**

```bash
cp .env.example .env      # Windows: copy .env.example .env
```

Set your MySQL password:

```ini
DB_USER=root
DB_PASSWORD=your_mysql_password
DB_HOST=localhost
DB_PORT=3306
DB_NAME=sanjeevani_clinic
USE_SQLITE=false
```

**4. Run.**

```bash
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Open **http://127.0.0.1:8000**

**Demo logins** (created by `database_setup.sql`):

| Role | Email | Password |
|---|---|---|
| Patient | `patient@demo.com` | `Demo@1234` |
| Admin | `admin@demo.com` | `Admin@1234` |
| Super user (pharmacy console) | `superuser@sanjeevani.com` | `Super@1234` |
| Pharmacist | `pharmacist@demo.com` | `Pharma@1234` |
| Doctor | `doctor@demo.com` | `Doctor@1234` — lands on **/doctor-desk**, the patient desk |

The last three exist once you have run `python seed_pharmacy.py`.
Or click **Sign up** to create your own account.

> See **`steps.txt`** for the full VS Code walkthrough including the ML pipeline.

---

## Check it's healthy

Open **http://127.0.0.1:8000/health**:

```json
{
  "status": "healthy",
  "database": "ready",
  "database_backend": "mysql",
  "database_target": "MySQL (localhost:3306/sanjeevani_clinic)",
  "ai_features": "enabled"
}
```

If `database_backend` says `sqlite`, the app could not reach MySQL and fell back
to a local file. The console prints the exact reason — see `MYSQL_SETUP.md`.

---

## ✅ Cross-check that everything is connected (one command)

`test_pharmacy.py` proves the pharmacy works. **`check_all_features.py`** proves
nothing is an island - that every feature you can see is actually joined to the
others, and that the roles really behave differently. It seeds its own throwaway
database (`check_all_features.db`, deleted on `--live` it never writes), so you
can run it any time, even while the server is running.

```bash
python check_all_features.py                      # 319 checks, console report
python check_all_features.py --html report.html   # same thing, printable HTML
python check_all_features.py --live              # read-only, against the database in your .env
#    (--live needs no URL and no server: it reads your real .env settings, runs only
#     GET requests, skips the write flows, and prints the same style of report)
#     (319 checks on SQLite, 320 when your .env points at MySQL)
```

What it looks at, in order:

| Section | Checks | What it proves |
|---|---|---|
| 1. boot + static | 3 | the app imports with the real code, and `pharmacy.css` / `pharmacy.js` really get served (a 404 there = your templates load dead assets) |
| 2. pages per role | 159 | 13 clinic pages + 7 pharmacy pages + all 6 admin tabs + **all 10 doctor-desk tabs**, walked as PATIENT / DOCTOR / PHARMACIST / ADMIN / SUPERUSER; that each login lands on the right page (doctor → `/doctor-desk`); and that a patient is bounced off `/pharmacy/admin` |
| 2b. JSON APIs | 8 | the APIs the JS actually calls answer `success: true` (`/api/medicines?q=`, `/api/cart`, `/api/nearby`, admin `orders` / `audit` / `snapshots`, desk `api/patients` / `api/summary`) - the 173-check suite covers the other writes |
| 3. link rules | 18 | greps the shipped templates/JS, so a dead button is caught even when the page renders: dashboard → `/pharmacy` **and** → `/doctor-desk`, nav Cart / Orders / Nearby, receipt → order, doctor file → invoice tab, `pharmacy.js` → `add-prescription`, … |
| 6. Google wiring | 8 | `/pharmacy/api/nearby` answers with or without `GOOGLE_MAPS_API_KEY`, always carries `google_status`, and the admin sync endpoint is mounted (details below) |
| 4. cross-table integrity | 40 | 13 LEFT JOIN orphan checks (order items ↔ orders ↔ medicines, cart ↔ users, Rx lines ↔ Rx ↔ medicines, desk notes ↔ patients, appointments ↔ doctors, records ↔ follow-ups…), 13 table-presence checks and the data every feature assumes (111 medicines, 32 diseases, the 5 demo logins, exactly one SUPERUSER, 0 rows in `role_permissions` on a clean install) |
| 5. end-to-end flows | 36 | sign up a patient → browse by disease → add to cart → checkout → order + items + audit row + stock drop → counter marks paid → handed over → receipt prints → cancel → stock back; and doctor → writes a note → issues an Rx → "send to cart" → the patient's cart holds exactly that medicine → patient buys that Rx (Rx-only medicine is refused in the shop) |
| 7. schema parity | 4 | **the SQL you pasted really matches the code**: every model table exists, no model column is missing, keys are there, and the module tables' foreign keys are real FKs. This is the check that catches a paste that is one column behind (e.g. the old `treatment_reviews` without `updated_at`) - the failure that otherwise only shows up later as `Unknown column ... in 'field list'`. Columns your database has that the code does not use are reported as a harmless note (your payment-gateway columns). |
| 8. original clinic features | 43 | **the features that existed before the pharmacy, exercised for real**: signup → wrong password refused → login → doctors list → slot lookup → book appointment → it shows on `/appointments` → cancel it (refund path checked) → profile update → follow-up complete → treatment review → AI screening → report upload (file on disk) → notifications. Rendering a page is not proof - every step is written and read back from the database |
| 4b. access control | 5 | a SUPERUSER revokes `doctor.desk.read` → the doctor's desk really closes for them → `POST /pharmacy/admin/api/roles/reset` → it opens again; and ADMIN can never write the role matrix |

Two lines of output are worth knowing:

```
319/319 checks passed, 0 failed
Everything is connected: clinic + pharmacy + doctor desk.
```

Anything else prints each failing check with the response body, so you know
which file to look at. `--live` prints the same checks but never a write, and
its login checks are skipped (it does not know your passwords).

---

## 🗺️ Google Maps / Places (optional - the app runs without it)

Nothing in the pharmacy needs a key. The emergency **"find it nearby"** page reads
the partner chemists from `nearby_pharmacies` + `nearby_pharmacy_stocks`, so it
works offline and in a viva with no internet. A Google key only adds *live*
results (real shops, phone number, open-now) and the **Import from Google** button.

```
1. https://console.cloud.google.com/apis/credentials -> Create credentials -> API key
2. APIs & Services -> Library -> enable "Places API" (Text Search + Place Details)
   (optionally "Maps Embed API" too, if you want the map image)
3. restrict the key to the HTTP referrers of your machine if you like; no OAuth needed
4. put it in .env:
       GOOGLE_MAPS_API_KEY=AIzaSy...
       CLINIC_LATITUDE=26.9124
       CLINIC_LONGITUDE=75.7873
       CLINIC_CITY=Jaipur
       PHARMACY_NEARBY_RADIUS_M=5000
5. restart uvicorn  (the key is read once at startup)
```

Then: **Pharmacy admin → Nearby → "Sync from Google"**, or as a patient open
`/pharmacy/nearby?medicine=<id>&query=<your area>` and tick "include Google".

How to know it is wired, without guessing:

```bash
curl "http://127.0.0.1:8000/pharmacy/api/nearby?query=Jaipur"      # google_used: false, still 200 + rows
python check_all_features.py --only google                          # prints the same check
```

* `GOOGLE_MAPS_API_KEY` empty -> `google_status = "not configured"`, page still
  works from the SQL list. **No crash, no blank page.**
* key set + Places enabled -> `google_status = "ok"` and imported shops appear in
  the Nearby table with `source = GOOGLE`.
* key set but the API is not enabled / quota out -> `google_status =`
  the Google error text (e.g. `REQUEST_DENIED`), and the module falls back to the
  SQL list so the patient still sees chemists.

The call is plain `urllib.request` (stdlib) - **no extra pip package**, so
`requirements.txt` does not change.

---

## ↩️ Rollback / "I broke it" list

| Symptom | Fix |
|---|---|
| pharmacy page says a table does not exist | start the app once (`python -m uvicorn main:app`) - `create_all()` adds missing tables, or paste `workbench_pharmacy.sql` again (it is `IF NOT EXISTS`, so nothing is lost) |
| you changed the role matrix and a role can no longer see its page | **Pharmacy admin → Access → "Reset to defaults"** per role, or `POST /pharmacy/admin/api/roles/reset`. The defaults live in `src/security/rbac.py`, so a reset always gets you back to a known state |
| demo data got messy (test orders, notes) | `python seed_pharmacy.py` again - it only refreshes the catalog/logins and never deletes your patients' rows |
| the throwaway check DB is in the way | `del check_all_features.db` (Windows) / `rm check_all_features.db` - it is a scratch file, safe to delete any time |
| MySQL user gets `ERROR 1142 command denied` | re-run the GRANT lines in `MYSQL_SETUP.md`, then log out / in |
| you want your pre-pharmacy project back | keep the `pharmacy-patch.diff` + the old zip: `git apply -R pharmacy-patch.diff` (or just re-extract the old zip) - the module is 12 tables + 6 new files, deleting the folder and the `.db` is enough to be clean again |

---

## AI features (optional)

The app runs fully without an AI key. Chatbot replies, AI health screening and
injury analysis simply stay switched off and say so on the page.

To enable them, add a free Groq key to `.env`:

```ini
GROQ_API_KEY=gsk_your_key_here
GROQ_MODEL=openai/gpt-oss-20b
GROQ_VISION_MODEL=qwen/qwen3.8-27b
```

Get a key at https://console.groq.com/keys

---

## ML pipeline

Three stages, all runnable from the repo root:

```bash
python -m src.components.data_ingestion        # load + split data
python -m src.components.data_transformation   # encode + save preprocessor
python -m src.pipeline.train_pipeline          # train and save best model
```

Or all three in one command:

```bash
python train_model.py
```

This writes `artifacts/model.pkl` and `artifacts/preprocessor.pkl`, which the
`/predict` page uses.

> **Honest note about this model.** It trains on `notebook/data/covid_toy.csv`,
> a 100-row practice dataset, and reaches only about 40–48% accuracy. It is a
> coursework demo of the ML plumbing, **not** a medical test. The numbers shown
> on the page come from this model's real output.

> **Run the training step after installing.** Scikit-learn pickles are not
> portable between scikit-learn versions, so the bundled `artifacts/*.pkl` may
> not load if your pip resolves a different version. If that happens the
> `/predict` page shows a yellow warning instead of pretending, and
> `python train_model.py` fixes it. `start.sh` / `start.bat` retrain
> automatically in that case.

---

## Password auth

Passwords are hashed with Argon2 (`pwdlib`). Set a real `SESSION_SECRET` in
`.env` before deploying anywhere public — it signs the login cookie:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## Project layout

```
main.py                     FastAPI entry point
database_setup.sql          full MySQL schema + seed data
steps.txt                   VS Code walkthrough, start to finish
MYSQL_SETUP.md              MySQL help / troubleshooting
RUN.md                      general run notes
requirements.txt            Python dependencies
.env.example                environment template
start.sh / start.bat        one-command launchers

src/
  config.py                 all absolute paths in one place
  database/                 engine + session (MySQL, SQLite fallback)
  models/                   15 SQLAlchemy models
  schemas/                  Pydantic request models
  security/                 password hashing
  services/                 business logic
  routers/                  route handlers (auth, doctor, appointment, …)
  components/               ML: ingestion, transformation, training
  pipeline/                 train_pipeline.py, predict_pipeline.py
  exception.py, logger.py   error handling + logging
  utils.py                  save/load pickle, evaluate models

templates/                  24 Jinja2 pages
static/style.css            stylesheet
notebook/data/covid_toy.csv training data
artifacts/                  trained model + preprocessor
uploads/medical_reports/    uploaded patient documents
_deprecated/                unused backups (safe to delete)
```

---

## Tech stack

FastAPI · Uvicorn · SQLAlchemy 2 · PyMySQL · MySQL · Jinja2 · Pydantic ·
pwdlib (Argon2) · scikit-learn · pandas · Groq (LLM) · pytesseract / pypdf (OCR)

Requires Python 3.11+ (the project targets 3.13).

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError: No module named 'fastapi'` | venv not active — you should see `(.venv)` in the prompt |
| Anything MySQL-related | See `MYSQL_SETUP.md` — the console prints the exact cause |
| `TemplateNotFound` | Start the app from the folder that contains `main.py` |
| Port 8000 in use | `--port 8001`, then open `http://127.0.0.1:8001` |
| AI pages say "not enabled" | `GROQ_API_KEY` is blank in `.env` — the app still works |
| OCR fails on scanned reports | Install the **Tesseract** program separately; plain PDFs/text work without it |
