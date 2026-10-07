# Sanjeevani Clinic

An AI-assisted healthcare platform: FastAPI + MySQL + Jinja2 templates, plus a
scikit-learn ML pipeline for Covid screening triage.

Patients can sign up, browse 20 doctors, book / reschedule / cancel appointments
against real doctor schedules, keep medical history, upload medical reports,
get AI health screening and injury triage, chat with an AI assistant, and manage
prescriptions and treatment reviews.

---

## What's in the box

| Path | What it is |
|---|---|
| `main.py` | FastAPI app — entry point, mounts all 12 routers |
| `database_setup.sql` | **Complete MySQL setup** — paste into MySQL Workbench and run |
| `steps.txt` | **Start-to-finish VS Code walkthrough** (venv → ML pipeline → run) |
| `MYSQL_SETUP.md` | MySQL-specific help and troubleshooting |
| `src/routers/` | HTTP layer — auth, profile, doctor, appointment, screening, … |
| `src/services/` | Business logic |
| `src/models/` | SQLAlchemy models (15 tables) |
| `src/components/` | ML pipeline: data ingestion → transformation → training |
| `src/pipeline/` | Training and prediction entry points |
| `notebook/data/covid_toy.csv` | Training dataset (100 rows, practice data) |
| `artifacts/` | Trained `model.pkl` + `preprocessor.pkl` (already included) |
| `templates/`, `static/` | Frontend (Jinja2 + CSS) |

---

## Quick start

**1. Create the database.** Open `database_setup.sql` in MySQL Workbench and run
it (lightning-bolt button). It creates all 15 tables, 20 doctors, 140 schedules,
5 visit types and two demo logins.

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
