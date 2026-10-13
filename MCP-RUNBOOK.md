# 🚀 MCP Platform — Complete Step-by-Step Runbook (Hinglish)

> Ye wohi ZIP hai jo maine diya: `Sanjeevani-Clinic-MCP-Platform.zip`
> Is runbook mein **har step pe command + kyun karna hai + kya dikhega** sab hai.
> Apne Windows PC pe neeche se upar follow karo — kuch bhi skip mat karo.

---

## 🧠 Pehle samajh lo — 3 cheezein chalti hain

| # | Cheez | Kya hai | Kaun sa command |
|---|-------|---------|-----------------|
| 1 | **MySQL database** | Tera data (users, appointments, medicines...) yahin hai | Workbench se migration |
| 2 | **10 MCP servers** | Naye AI/intelligence servers (ports 9101-9302) | `python -m src.mcp.run_all` |
| 3 | **FastAPI app** | Tera existing website (login, pharmacy, chatbot, /mcp console) | `python -m uvicorn main:app ...` |

**Flow:** Browser → FastAPI app → MCP gateway → 10 MCP servers → MySQL.
Browser kabhi directly MCP servers se nahi baat karta (security ✔).

---

## 📁 Step 0 — ZIP extract karo

```bat
:: Desktop pe ek folder banao, ZIP extract karo
:: Extract hone ke baad folder mein yeh dikhega:
::   main.py, src/, templates/, static/, migrations/, tests, MCP_PLATFORM.md, MCP-RUNBOOK.md (ye file), start_mcp.bat, .env.example
```

**Kyun:** Ye poora project hai — purana clinic + naya MCP platform dono.

---

## 🐍 Step 1 — Python venv banao aur install karo

```bat
:: Project folder mein jao (jahan main.py hai)
cd C:ilepath\Sanjeevani-Clinic-MCP-Platform

:: 1. Virtual environment banao (sirf ek baar)
python -m venv .venv

:: 2. Activate karo (har naye terminal mein karna padega)
.venv\Scripts\activate

:: 3. Saari dependencies install karo (fastmcp waghera sab yahin se aayenge)
pip install -r requirements.txt
```

**Kyun:** `.venv` ek alag jagah hai jahan sirf is project ke packages hain — system Python kharab nahi hota. `requirements.txt` mein ab `fastmcp` bhi hai (10 MCP servers ke liye zaroori).

**Check:** `.venv\Scripts\activate` ke baad prompt mein `(.venv)` likha aana chahiye.

---

## ⚙️ Step 2 — `.env` file: kya changes karne hain

`.env` **kabhi delete/nahi banana** — agar hai toh bas neeche ki lines check/edit karo. Agar nahi hai toh `.env.example` copy karke `.env` banao.

```bat
:: Agar .env nahi hai toh:
copy .env.example .env
:: Phir .env ko VS Code/Notepad mein kholo
```

**`.env` mein yeh lines aisi honi chahiye:**

```ini
# ---- Database (tera existing MySQL) ----
USE_SQLITE=false
DB_USER=sanjeevani_app
DB_PASSWORD=keshav123
DB_HOST=localhost
DB_PORT=3306
DB_NAME=sanjeevani_clinic

# ---- Session (login cookies ke liye secret) ----
SESSION_SECRET=yahan-koi-bhi-lamba-random-string-daal-de

# ---- MCP Platform (naya) ----
# Gateway aur 10 MCP servers ke beech ka shared secret.
# Local testing mein default chalega, PRODUCTION mein zaroor change karna.
MCP_SERVICE_TOKEN=yahan-bhi-koi-lamba-random-string
MCP_CALL_TIMEOUT=15

# ---- GROQ AI (tera existing key - chatbot AI ke liye) ----
GROQ_API_KEY=tera-purana-key-yahin-rahega
```

| Line | Kya hai | Kyun |
|---|---|---|
| `USE_SQLITE=false` | MySQL use karna hai | Tera data MySQL mein hai |
| `DB_USER / DB_PASSWORD` | Tera MySQL login | `sanjeevani_app` / `keshav123` (tera wala) |
| `DB_NAME=sanjeevani_clinic` | Tera existing database | Isi mein sab data hai |
| `SESSION_SECRET` | Login session ka secret | Naya hai — koi bhi lamba string chalega |
| `MCP_SERVICE_TOKEN` | **Naya** — MCP servers ka password | Gateway in servers ko prove karta hai ki woh asli hai |
| `MCP_CALL_TIMEOUT=15` | **Naya** — tool call timeout (seconds) | Slow server pe wait na kare |
| `GROQ_API_KEY` | Tera purana key | Chatbot ka AI part — **bina iske bhi** local evidence-grounded answers chalte hain ✔ |

**Kyun:** `.env` se app ko pata chalta hai ki kaunsa DB, kaunsa secret. Galat ho toh app SQLite fallback pe chala jata hai (warning log mein dikhega).

---

## 🗄️ Step 3 — MySQL Workbench: migration (SQL) kaise karein

Tera `sanjeevani_clinic` DB already hai. Ab usme **16 nayi tables** add hongi (MCP platform ki). Ye **additive** hai — purana kuch nahi delete hota ✔.

**Workbench mein yeh steps:**

1. **Workbench kholo** → apna connection (`sanjeevani_app`) se connect karo.
2. **Schema select karo:** left side `sanjeevani_clinic` pe click.
3. **Purana script pehle (agar nahi kiya toh):** `File → Open SQL Script → workbench_all_features.sql → Run (⚡)`.
4. **Naya script ab:** `File → Open SQL Script → migrations/mcp_platform.sql → Run (⚡)`.
5. **Verify karo** (neeche ki queries Result Grid mein chalani chahiye):

```sql
-- 10 MCP servers registry mein aa gaye?
SELECT COUNT(*) AS servers FROM mcp_servers;
-- Expected: 10

-- Nayi tables dikh rahi hain?
SHOW TABLES;
-- mcp_servers, audit_events, security_events, ai_requests, ai_evidence,
-- ai_claims, care_gaps, care_review_tasks, clinical_conflicts,
-- scenario_runs, change_requests, change_approvals, workflow_events,
-- recovery_attempts, ai_benchmark_runs, ai_benchmark_results

-- Dubara chalana safe hai? (paste-safe check)
-- migrations/mcp_platform.sql dobara Run karo -> koi error nahi aana chahiye
```

**Kyun:** MCP platform ko apni tables chahiye (audit, evidence, care gaps, benchmarks...). `CREATE TABLE IF NOT EXISTS` + `INSERT IGNORE` hai — isliye baar-baar paste karna bhi safe hai, kuch delete nahi hota. **Zero DROP** ✔.

**Agar error aaye:** `Cannot add foreign key constraint` → matlab `users` table pehle nahi bani → pehle `workbench_all_features.sql` run karo (step 3).

---

## 🤖 Step 4 — 10 MCP servers start karo (Terminal 1)

```bat
:: Terminal 1 kholo, project folder mein jao, venv activate karo
cd C:\filepath\Sanjeevani-Clinic-MCP-Platform
.venv\Scripts\activate

:: Option A: Windows shortcut
start_mcp.bat

:: Option B: direct command
python -m src.mcp.run_all
```

**Kya dikhega:**
```
Started 10 MCP servers: care-gap-intelligence, evidence-ai, health-timeline,
workflow-simulator, care-continuity, clinical-safety, hospital-intelligence,
change-approval, ai-reliability, flight-recorder
Press Ctrl+C to stop all.
```

**Kaise check karein ki sab up hain:**
- Console mein `/mcp → MCP Server Registry` section mein **10 ONLINE** dikhenge (Step 7 dekho).
- Ya PowerShell se ek server ka health check:

```powershell
# Ye 401 dega bina token ke - matlab server chal raha hai aur auth kaam kar raha hai ✔
curl.exe -s -o $null -w "%{http_code}" -X POST http://127.0.0.1:9101/mcp -H "Content-Type: application/json" -d '{}'
# Expected output: 401
```

**Kyun:** Ye 10 servers hi naye features hain — inke bina app chalta hai but console ke live sections "service unavailable" dikhayengi.

**Roko kaise:** Terminal 1 mein `Ctrl+C`.

---

## 🌐 Step 5 — FastAPI app start karo (Terminal 2)

```bat
:: Terminal 2 (naya) kholo, same folder, venv activate
cd C:\filepath\Sanjeevani-Clinic-MCP-Platform
.venv\Scripts\activate

:: App start karo
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

**Kya dikhega:**
```
ACTIVE DATABASE: MySQL (localhost:3306/sanjeevani_clinic)
Uvicorn running on http://0.0.0.0:8000
```

**Agar `ACTIVE DATABASE: SQLite` dikhe** → `.env` galat hai ya MySQL band hai → Step 2 dobara check karo.

**Kyun:** Ye tera existing website hai — login, pharmacy, appointments, chatbot, doctor desk — sab yahin se chalta hai. `--reload` ka matlab: code change karne pe auto-restart.

---

## ✅ Step 6 — Checks (kabhi bhi run kar sakte ho)

Koi bhi naya terminal (venv activated hona chahiye):

```bat
:: 1. MCP platform full test — 62 checks, 10 servers in-process start ho jaate hain
python test_mcp_platform.py
:: Expected end mein:
::   PASSED: 62 checks / FAILED: 0 / RESULT: ALL GREEN - platform verified.

:: 2. Existing features regression — 233 checks
python test_pharmacy.py
:: Expected: "233 checks passed, 0 failed"

:: 3. Real MySQL pe integration — 58 checks (tera actual DB use karta hai)
python test_pharmacy_mysql.py
:: Expected: "58 checks passed, 0 failed"
```

**Kyun:** Ye prove karta hai ki (a) naya MCP platform sahi kaam kar raha hai, (b) purane features nahi toote. `test_mcp_platform.py` apne aap 10 servers start kar leta hai — alag se start_mcp.bat ki zaroorat nahi.

---

## 🔐 Step 7 — Browser: login page se shuru (step-by-step)

1. Browser kholo: **http://localhost:8000/login**
2. **Login page khulna chahiye** — 5 demo accounts dikhenge (🧪 demo panel).
3. **Patient login:** `patient@demo.com` / `Demo@1234` → dashboard khulega.
4. Sidebar mein **🤖 AI Assistant** ya direct **http://localhost:8000/mcp** → **Intelligence Console** khulega.
5. Console mein apne role ke hisaab se sections dikhenge (PATIENT: Overview, Patient Journey, What-If Simulator).
6. **Doctor login:** `doctor@demo.com` / `Doctor@1234` → `/doctor-desk` bhi chalega ✔ (purana feature) + console mein Clinical Safety section bhi dikhega.
7. **Admin login:** `admin@demo.com` / `Admin@1234` → console mein Registry, AI Safety, Access Control, Audit, Change, Recovery sections.
8. **Superuser login:** `superuser@sanjeevani.com` / `Super@1234` → sab sections + "Run safety benchmarks" button.

**Har login ke baad browser refresh = `Ctrl+F5`** (cache purana na le).

**Kyun:** Alag-alag roles se alag-alag sections dikhte hain — ye RBAC ka live demo hai.

---

## 🧪 Step 8 — Har MCP server ka use case + kaise check karein

Console (`/mcp`) ke sections hi sabse aasaan check hain. Har server kya karta hai + kahan dikhega:

| Server | Kya karta hai (use case) | Kaise check karein | Kya dikhega |
|---|---|---|---|
| **U1 care-gap-intelligence** | Patient ke records mein missing steps dhoondhta hai (follow-up nahi hua, report pending) | Patient login → console → **Patient Journey** → apna Patient ID → **Load journey** | Timeline + "Missing steps / care gaps" list |
| **U2 evidence-ai** | Chatbot ke answers ko DB se verify karta hai (hallucination nahi hone deta) | Chatbot mein `price of dolo 650` likho → sahi answer aayega; galat cheez pucho → "Verified information is not available..." | Chatbot mein verified answers; console → **AI Safety** mein evidence stats |
| **U3 health-timeline** | Patient ki poori timeline banata hai (visits, prescriptions, follow-ups) | Patient login → **Patient Journey** → Load journey | Chronological timeline, har entry pe record ID + date |
| **U4 workflow-simulator** | "What-if" scenarios — synthetic data pe (doctor chutti le le, reschedule wave) | Console → **What-If Simulator** → scenario chuno → **Simulate** | Outcomes + assumptions + **SYNTHETIC** badge (real data nahi badalta ✔) |
| **U5 care-continuity** | Patient ke pending steps bataata hai (follow-ups, gaps, treatments) | Patient login → **Patient Journey** | Pending follow-ups, open care gaps, active treatments |
| **A1 clinical-safety** | Clinical records mein conflicts dhoondhta hai (same medicine alag dosage, prescription without diagnosis) | Doctor/Admin login → **Clinical Safety** → **Scan for conflicts** | Conflicts list; review assign karne ka option |
| **A2 hospital-intelligence** | Hospital ke aggregate stats (completion rates, drop-offs) — patient data nahi dikhata | Admin login → **Overview** stats + Registry | User counts, completion rates, denied events |
| **A3 change-approval** | Bade changes se pehle impact dekhata hai (doctor deactivate karne se kya hoga) | Admin login → **Change & Approval** → Doctor deactivation → Doctor ID → **Preview impact** | "would_affect: upcoming_appointments" + **Request approval** button |
| **S1 ai-reliability** | AI ki safety benchmarks chalata hai (grounding, refusal, IDOR tests) | Superuser login → **AI Safety** → **Run safety benchmarks** | Pass rate, grounding accuracy, refusal accuracy + per-test results |
| **S2 flight-recorder** | Failed payments/appointments ko recover karta hai (idempotent — duplicate nahi banata) | Admin login → **Recovery** → correlation ID → **Reconstruct** / **Reconcile** | Incident timeline + recovery attempts + status |

**Direct API check (PowerShell) — bina console ke:**

```powershell
# Pehle login karo (cookie save hogi)
curl.exe -s -c ck.txt -o $null -X POST http://localhost:8000/login -d "email=patient@demo.com&password=Demo@1234"

# U1 ka tool direct call karo (gateway se)
curl.exe -s -b ck.txt -X POST http://localhost:8000/mcp/api/call -H "Content-Type: application/json" -d '{"server":"care-gap-intelligence","tool":"detect_care_gaps","params":{"patient_id":5}}'

# Dusre patient ka try karo -> ACCESS_DENIED aana chahiye (IDOR protection ✔)
curl.exe -s -b ck.txt -X POST http://localhost:8000/mcp/api/call -H "Content-Type: application/json" -d '{"server":"care-gap-intelligence","tool":"detect_care_gaps","params":{"patient_id":7}}'
```

**Kyun:** Ye dikhata hai ki har server alag kaam karta hai aur sab gateway se jude hain.

---

## 🛠️ Step 9 — Common problems + fix

| Problem | Kyun hota hai | Fix |
|---|---|---|
| `ACTIVE DATABASE: SQLite` | `.env` galat ya MySQL band | `.env` check karo; MySQL service start karo |
| Migration mein FK error | `users` table nahi hai | Pehle `workbench_all_features.sql` run karo |
| Console sections "service unavailable" | MCP servers nahi chal rahe | Terminal 1 mein `python -m src.mcp.run_all` chalao |
| Port 9101 busy | Koi aur process use kar raha | `netstat -ano \| findstr 9101` → PID dekho → Task Manager se band karo |
| 401 on /mcp/api/call | Login nahi kiya ya session expired | Phir se login karo |
| ACCESS_DENIED on own data | Dusre ka patient_id daal diya | Apna hi patient_id (patient login pe apna ID pehle se bhara hai) |
| `ModuleNotFoundError: fastmcp` | pip install nahi hua | `pip install -r requirements.txt` dobara |
| Chatbot "Unable to connect" | App band hai | Terminal 2 mein uvicorn check karo |

---

## 📋 Quick command cheat-sheet

```bat
:: Setup (ek baar)
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env          & rem .env edit karo

:: Har baar (2 terminals)
:: Terminal 1:
.venv\Scripts\activate
python -m src.mcp.run_all          (ya start_mcp.bat)
:: Terminal 2:
.venv\Scripts\activate
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

:: Checks (koi bhi naya terminal, venv active)
python test_mcp_platform.py       :: 62 checks - MCP platform
python test_pharmacy.py           :: 233 checks - existing features
python test_pharmacy_mysql.py     :: 58 checks - real MySQL

:: Browser
http://localhost:8000/login       :: login page
http://localhost:8000/mcp         :: intelligence console
http://localhost:8000/pharmacy    :: pharmacy (purana feature ✔)
http://localhost:8000/doctor-desk :: doctor desk (doctor login) ✔
```

---

## 🎯 Yaad rakhne wali baat

1. **Pehle MCP servers** (Terminal 1), **phir app** (Terminal 2) — order zaroori nahi hai but dono chahiye.
2. **Workbench migration** ek baar kaam hai — baad mein dobara chala sakte ho, safe hai.
3. **`.env` mein sirf 2 nayi lines hain** — `MCP_SERVICE_TOKEN` aur `MCP_CALL_TIMEOUT`. Baaki tera purana hi hai.
4. **Har check green hone ka matlab:** naya platform sahi hai **aur** purana project nahi toota.
5. **Koi bhi doubt** → `MCP_PLATFORM.md` (architecture + inventory) aur ye runbook padho.

**Sab kuch ready hai — bas upar se neeche follow karo!** 💪😊
