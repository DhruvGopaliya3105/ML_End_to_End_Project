# Running Sanjeevani Clinic on MySQL

You are using MySQL (not SQLite), which is the app's default and preferred mode.
This file is the MySQL-specific guide. General info is in `RUN.md`.

---

## 0. The one thing that was probably breaking it

`pymysql` — the driver your app uses — **cannot talk to MySQL 8 unless the
`cryptography` package is installed.** MySQL 8 made `caching_sha2_password` the
default authentication plugin, and PyMySQL refuses to use it without
`cryptography`. Without it you get:

```
RuntimeError: 'cryptography' package is required for
sha256_password or caching_sha2_password auth methods
```

…and because the app fell back to SQLite **silently**, the result looked like
"my features don't work / my data is gone" rather than a database error.

`cryptography` was **missing from `requirements.txt`**. It is added now, plus:

- MySQL failures are explained in plain English in the console (see §4).
- `/health` tells you which database is actually in use.

So: **delete your old `.venv` and reinstall** so `cryptography` gets pulled in:

```cmd
rmdir /s /q .venv
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Or, if you'd rather not rebuild the venv:
```cmd
pip install cryptography
```

---

## 1. Check your MySQL is running and has your data

```cmd
mysql -u root -p
```

```sql
USE sanjeevani_clinic;

SELECT COUNT(*) FROM doctors;          -- expect 20
SELECT COUNT(*) FROM doctor_schedules; -- expect 140
SELECT COUNT(*) FROM visit_types;      -- expect 5
SHOW COLUMNS FROM appointments;        -- should show visit_type, payment_*, refund_*, cancelled_*, razorpay_*
```

If any of those are missing, re-run your MySQL setup script.

> **Is your MySQL 8 or 5.7?** Run `SELECT VERSION();`
> - **8.0 or newer** → you almost certainly need `cryptography` (§0).
> - **5.7** → usually works without it.

### If your root user is socket-authenticated

Some MySQL installs (very common on Linux, and on macOS with Homebrew) have
`root` set to `auth_socket`, which a Python app cannot use. Create a normal
password user for the app instead:

```sql
CREATE USER 'sanjeevani'@'localhost' IDENTIFIED BY 'YourStrongPassword';
GRANT ALL PRIVILEGES ON sanjeevani_clinic.* TO 'sanjeevani'@'localhost';
FLUSH PRIVILEGES;
```

Then use `sanjeevani` / `YourStrongPassword` in `.env`.

---

## 2. Your `.env` file

Create it from the template and edit it:

```cmd
copy .env.example .env
notepad .env
```

Fill in the database section — this is the important part:

```ini
DB_USER=root
DB_PASSWORD=your_actual_mysql_password
DB_HOST=localhost
DB_PORT=3306
DB_NAME=sanjeevani_clinic

# Must be false (or absent) to use MySQL
USE_SQLITE=false
```

Common variations:

| Your situation | What to set |
|---|---|
| Default Windows MySQL installer | `DB_USER=root`, `DB_PASSWORD=<the password you set during install>` |
| Dedicated app user (recommended) | `DB_USER=sanjeevani`, `DB_PASSWORD=<that user's password>` |
| Non-standard port | `DB_PORT=3307` (or whatever you chose) |
| Remote/shared MySQL | `DB_HOST=<server ip>` |
| Local MySQL via socket, no TCP | Use `DB_HOST=localhost` (not `127.0.0.1`) |

Optional, same file — leave `GROQ_API_KEY` blank and the app still runs
(only the AI features switch off):

```ini
GROQ_API_KEY=
SESSION_SECRET=put_a_long_random_string_here
```

---

## 3. Run it

```cmd
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Then open **http://127.0.0.1:8000/health**. It must say:

```json
{
  "status": "healthy",
  "database": "ready",
  "database_backend": "mysql",
  "database_target": "MySQL (localhost:3306/sanjeevani_clinic)"
}
```

**If `database_backend` says `sqlite`, you are NOT on MySQL.** See §4.

Sign in with an account you already created — or click **Sign up** on the login
page. (The demo logins `patient@demo.com` / `Demo@1234` are only created by
`seed_sqlite_demo.py`, which is for the SQLite path — they do not exist in your
MySQL database.)

---

## 4. Troubleshooting — the console now tells you exactly what's wrong

On startup, if MySQL cannot be reached you'll see a block like this:

```
WARNING | ==============================================================================
WARNING | ACTIVE DATABASE: SQLite (/path/to/sanjeevani_clinic.db)
WARNING | Reason for fallback: MySQL connection failed (localhost:3306/sanjeevani_clinic) -- <reason>
WARNING | ==============================================================================
```

Here's what each reason means and how to fix it:

| Message in console | Cause | Fix |
|---|---|---|
| *"'cryptography' package is required for sha256_password or caching_sha2_password"* | MySQL 8 auth plugin | `pip install cryptography` (now in `requirements.txt`) |
| *"MySQL rejected the username or password"* | Wrong `DB_USER` / `DB_PASSWORD` | Fix `.env`, restart |
| *"Nothing is listening on that MySQL host/port"* | MySQL service not started, or wrong `DB_PORT` | Start MySQL; on Windows: `net start MySQL80` |
| *"The database 'x' is missing, or user 'y' has no privileges on it"* | Database not created, or user lacks a GRANT | Re-run your setup script, or `GRANT ALL PRIVILEGES ON sanjeevani_clinic.* TO 'user'@'localhost';` |
| *"This MySQL user authenticates via the operating-system socket (auth_socket)"* | `auth_socket` plugin | Create a password user — see §1 |

### Quick manual connection test

Before blaming the app, check the driver can connect at all:

```cmd
python -c "import pymysql; c=pymysql.connect(host='localhost',user='root',password='YOURPASS',database='sanjeevani_clinic'); print('connection OK'); c.close()"
```

If that fails, it's a MySQL settings problem, not an app problem.

---

## 5. What I verified against a real MySQL server

I installed a MySQL-compatible server, rebuilt your schema (20 doctors, 140
schedules, 5 visit types, plus all your `ALTER`ed appointment columns) and ran
the whole app against it:

- ✅ Connects and reads your data — 20 doctors, 5 visit types, 140 schedules
- ✅ Signup and login — user written to MySQL and verified in the table
- ✅ Booking a slot, `/api/appointment-times` (correctly excludes booked slots)
- ✅ Reschedule and cancel
- ✅ Profile update
- ✅ Prescriptions + medicines, screening history, notifications
- ✅ `visit_type` now saves as `General Consultation` (not `"1"`)
- ✅ Times stored as real MySQL `TIME` values
- ✅ `/health` reports `database_backend: mysql`
- ✅ Wrong password / server down / missing database each produce a clear,
  specific message instead of failing silently

Two MySQL-specific notes worth knowing:

1. **`slot_id` foreign key.** Your SQL created `appointments.slot_id` with
   `ON DELETE CASCADE`, but the model declares `ON DELETE SET NULL`.
   `create_all()` never alters existing tables, so **your MySQL keeps CASCADE** —
   deleting a slot would delete the appointment. If you want the model's
   behaviour, run:
   ```sql
   ALTER TABLE appointments DROP FOREIGN KEY fk_appt_slot;
   ALTER TABLE appointments ADD CONSTRAINT fk_appt_slot
     FOREIGN KEY (slot_id) REFERENCES doctor_slots(id) ON DELETE SET NULL;
   ```
2. **The Razorpay columns are unused.** `transaction_id`, `payment_gateway`,
   `paid_at`, `razorpay_order_id`, `razorpay_payment_id`, `payment_provider`
   and `payment_failure_reason` exist in your MySQL table but **no Python code
   references them anywhere** — there is no payment gateway integration in the
   project. They're just unused columns. Also, `create_all()` will not add them
   to a fresh database, since the model doesn't declare them.
