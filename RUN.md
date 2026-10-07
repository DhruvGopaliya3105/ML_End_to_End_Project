# Sanjeevani Clinic — run notes and change log

> **Start here instead:** `steps.txt` is the full start-to-finish VS Code
> walkthrough, `README.md` is the project overview, and `MYSQL_SETUP.md` covers
> MySQL specifics. This file records what was fixed and why.


## 1. Quick start (3 steps)

```bash
# 1. Create your .env and put in your MySQL password + Groq key
cp .env.example .env          # Windows: copy .env.example .env
#    then edit .env

# 2. Install dependencies (Python 3.11+; 3.13 is what the project targets)
python -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. Run
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Then open **http://127.0.0.1:8000**

Or just use the launcher, which does the `.env` copy and model training for you:

```bash
./start.sh          # Windows: start.bat
```

### Check it is healthy

Open **http://127.0.0.1:8000/health** — it now tells you exactly which database
is in use and whether AI features are on:

```json
{
  "status": "healthy",
  "database": "ready",
  "database_backend": "mysql",
  "database_target": "MySQL (localhost:3306/sanjeevani_clinic)",
  "ai_features": "enabled"
}
```

---

## 2. Using SQLite instead of MySQL

If you want to run with **no MySQL at all**, you have two options:

**Option A — let it fall back automatically.** If MySQL is unreachable the app
still starts on SQLite. You will now see a loud warning in the console:

```
WARNING | ACTIVE DATABASE: SQLite (/path/to/sanjeevani_clinic.db)
```

**Option B — be explicit.** In `.env`:

```
USE_SQLITE=true
```

To get a SQLite database with the same 20 doctors / schedules / visit types as
your MySQL setup, plus two demo logins:

```bash
python seed_sqlite_demo.py
```

Demo logins it creates:

| Role | Email | Password |
|---|---|---|
| Patient | `patient@demo.com` | `Demo@1234` |
| Admin | `admin@demo.com` | `Admin@1234` |

> `seed_sqlite_demo.py` deletes and rebuilds `sanjeevani_clinic.db`.
> It never touches MySQL.

---

## 3. Enable the AI features (optional)

The app runs completely without AI. If `GROQ_API_KEY` is empty, the AI pages
still load but tell you the AI is off instead of failing silently.

To turn them on, put a key in `.env`:

```
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxx
GROQ_MODEL=openai/gpt-oss-20b
GROQ_VISION_MODEL=qwen/qwen3.8-27b
```

Free keys: https://console.groq.com/keys

---

## 4. Rebuilding the ML model

The `/predict` (Covid screening) page needs `artifacts/model.pkl` and
`artifacts/preprocessor.pkl`. Those files are git-ignored, so they are **not**
in the GitHub repo — this zip includes them, but if they ever go missing:

```bash
python train_model.py
```

> **Honest note on this model:** it trains on `notebook/data/covid_toy.csv`, a
> 100-row practice dataset, and only reaches about 40–48% accuracy. It is a
> coursework demo, **not** a medical test. It now genuinely loads the model
> instead of quietly using a rule-based score, and the page no longer prints a
> fabricated "96% confidence".

---

## 5. What was actually broken, and what I changed

I ran the app and clicked through every route. Here is what I found and fixed.

### Real bugs fixed

| # | Problem | Effect on you | Fix |
|---|---|---|---|
| 1 | `GROQ_API_KEY` missing crashed the app **at import time** (`llm_service.py` raised, `injury_service.py` called `Groq(api_key=None)`) | The whole site was dead — even login, doctors and booking, which need no AI | New `src/services/groq_client.py`: the client connects lazily. The app always starts; only AI calls report the missing key |
| 2 | `artifacts/model.pkl` was never in the repo (git-ignored) | `/predict` silently fell back to a hand-written score while still printing "Model confidence: 96%" | Trained and shipped the artifacts, added `train_model.py`, removed the fabricated confidence number |
| 3 | SQLite fallback was silent | You could think you were on MySQL while every record went to a local file — "my data disappeared" | Startup now logs a loud warning; `/health` reports `database_backend` and the fallback reason |
| 4 | SQLite path was relative (`sqlite:///./sanjeevani_clinic.db`) | Starting the server from another folder created a second, empty database | Path is now absolute, from the project root |
| 5 | `Jinja2Templates(directory="templates")` in 11 files — relative | `TemplateNotFound` (500s) if you started uvicorn from any other directory | All 11 now use the absolute `TEMPLATES_DIR` from `src/config.py` |
| 6 | `artifacts/` and `uploads/` paths were relative | Uploads landed in random folders; predictions failed from other directories | Both now absolute via `src/config.py` |
| 7 | `visit_type` stored the **id as a string** (`"1"`) into a VARCHAR column | Appointment rows were unreadable and could never match `visit_types.name` | Now stores the real name, e.g. `"General Consultation"`, with a safe fallback |
| 8 | The "AI Health Screening" **never called the AI** — the result was a hard-coded f-string | The AI screening feature was fake | Now calls the LLM first (constrained to your real specialisations so doctor-matching still works). If AI is off, the page says so clearly |
| 9 | Injury analysis returned a generic **500** when the key was missing | Confusing "Something went wrong" | Returns **503** with the exact fix in the message |
| 10 | Duplicate dead code: `src/routers/__init__.py` held a second full appointment router; duplicate `prescription_service.py` in `src/security/` | Genuinely hard to tell which code runs | Left in place but documented — see "Still outstanding" below |

### Cleanup

- `main_backup_current.py`, `src/routers/documents_backup.py`,
  `templates/reschedule_app.py`, `templates/medical_reports_backup.html`
  moved to `_deprecated/` (nothing imports them; safe to delete).

### Added

- `.env.example` — every setting documented, with explanations
- `RUN.md` — this file
- `start.sh` / `start.bat` — one-command start
- `train_model.py` — rebuild the ML artifacts
- `seed_sqlite_demo.py` — a ready SQLite database with demo logins
- `src/config.py` — one place for all paths

### Verified working after the fixes

Every route was requested and every write flow was exercised:

login, signup, logout, dashboard, doctors list, doctor detail, booking a slot,
`/api/appointment-times`, appointments list, reschedule, cancel, profile,
edit profile, notifications, medical history, medical reports (list, upload,
view, download, read, analyze), screening, chatbot, chatbot message, injury page,
injury analyze, prescriptions (create + history), treatment reviews, and
`/predict`.

All of these now boot and respond correctly **even with no `GROQ_API_KEY` and no
MySQL running**.

---

## 6. Still outstanding (not bugs — designs you may want to change)

These are real issues I chose **not** to change, because they alter behaviour you
may have intended. Say the word and I'll do them:

1. **`src/routers/__init__.py`** contains a complete second copy of the
   appointment router (485 lines). It is never mounted, but because it lives in
   the package `__init__`, it is imported as a side effect and is easy to
   mistake for the live code — `src/routers/appointment.py` is the real one.
2. **`src/security/prescription_service.py`** duplicates
   `src/services/prescription_service.py`. Only the `services` one is used.
3. **Committed `sanjeevani_clinic.db`** is in git. If you and a teammate run on
   different databases this causes confusion. Consider removing it from git and
   keeping it git-ignored.
4. **Screening severity ordering** — the rule-based fallback checks keywords in
   order, so "fever and headache" used to be routed to Neurology simply because
   *headache* appeared earlier in the chain than *fever*. With AI on this is no
   longer used, but the fallback ordering is still worth tuning.
5. **Passwords** — `SESSION_SECRET` defaults to a well-known string. Set a real
   one in `.env` before deploying anywhere public.
6. **Doctor schedules assume Monday = 0.** Your SQL inserts need the same
   convention, otherwise every doctor looks unavailable on the wrong day.
