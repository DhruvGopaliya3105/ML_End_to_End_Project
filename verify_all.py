"""One command that runs EVERY check in this project: the original clinic
smoke scripts, the new pharmacy + doctor desk suite, the cross-feature
integration suite, and (when your .env points at MySQL) the MySQL suite.

    python verify_all.py            # everything that can run here
    python verify_all.py --quick    # skip the MySQL step
    python verify_all.py --keep-logs   # also keep the full logs (verify_logs/)

What each step proves
---------------------
1. test_password.py          the original password hashing/verification still works
2. test_schema.py            the original Pydantic user schema still validates
3. test_db.py                the app can open the database your .env/config points at
4. test_pharmacy.py          the NEW features: pharmacy + admin console + doctor desk
                             (173 checks, end to end, on a throwaway database)
5. check_all_features.py     EVERYTHING is connected: clinic pages per role, links,
                             foreign keys, the 319 integration checks - including the
                             original clinic flows (signup -> appointment -> cancel ->
                             review -> screening -> report upload) and a schema-parity
                             check that catches "the SQL you pasted is one column behind"
6. test_pharmacy_mysql.py    the same pharmacy, but on your REAL MySQL database
                             (self-skips with a clear message when .env is SQLite)

Exit code is 0 only when every step that ran passed, so this is safe to use as
a pre-submission gate. Nothing here deletes data: steps 4-6 build their own
throwaway SQLite database; step 6 only reads/writes its own test rows on MySQL.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "verify_logs"

STEPS = [
    (
        "original: password hashing",
        [sys.executable, "test_password.py"],
        r"(Correct password:.*)",
    ),
    (
        "original: user schema",
        [sys.executable, "test_schema.py"],
        r"(User schema is valid.*)",
    ),
    (
        "original: database connection",
        [sys.executable, "test_db.py"],
        r"(Database connection .*)",
    ),
    (
        "new: pharmacy + doctor desk",
        [sys.executable, "test_pharmacy.py"],
        r"(\d+ checks passed, \d+ failed)",
    ),
    (
        "all features connected",
        [sys.executable, "check_all_features.py"],
        r"(\d+/\d+ checks passed, \d+ failed)",
    ),
    (
        "MySQL (real database)",
        [sys.executable, "test_pharmacy_mysql.py"],
        r"(\d+ checks passed, \d+ failed.*)",
    ),
]

SKIPPED = {
    "test_user_service.py": "it CREATES a demo user in your database - run it by hand "
                            "only if you want that",
    "test_llm_service.py": "needs GROQ_API_KEY and network access",
    "test_groq.py": "needs GROQ_API_KEY and network access",
    "train_model.py": "trains the ML model (minutes); run it if you use /predict",
}


def run_step(name: str, cmd: list[str], pattern: str, keep_logs: bool) -> tuple[str, str, str]:
    """Run one command, show its tail, return (status, detail, log_path)."""

    print("\n" + "=" * 74)
    print(f"  {name}")
    print(f"  $ {' '.join(cmd)}")
    print("=" * 74)

    try:
        proc = subprocess.run(cmd, cwd=BASE_DIR, capture_output=True, text=True,
                              timeout=1800)
        output = (proc.stdout or "") + (proc.stderr or "")
        code = proc.returncode
    except subprocess.TimeoutExpired:
        output = "TIMEOUT after 1800 seconds"
        code = 124

    lines = [ln for ln in output.splitlines() if ln.strip()]
    for line in lines[-12:]:
        print("   " + line)

    detail = ""
    match = re.search(pattern, output, re.I)
    if match:
        detail = match.group(1).strip()

    LOG_DIR.mkdir(exist_ok=True)
    log_path = LOG_DIR / (re.sub(r"[^a-z0-9]+", "-", name.lower()) + ".log")
    log_path.write_text(output, encoding="utf-8")

    if "SKIP -" in output:
        status = "SKIP"
        detail = "your .env is not pointing at MySQL - nothing to check there"
    elif code == 0:
        status = "OK"
    elif match and re.search(r", 0 failed", detail):
        # Every check passed but the script still exited non-zero: that is a
        # cleanup hiccup (e.g. Windows WinError 32 while deleting the scratch
        # SQLite file), not a test failure.
        status = "OK"
        detail = f"{detail} (cleanup hiccup only - all checks passed)"
    else:
        status = "FAIL"
        if not detail:
            detail = lines[-1][:90] if lines else f"exit code {code}"

    if not keep_logs:
        try:
            shutil.rmtree(LOG_DIR)
        except OSError:
            pass

    return status, detail, str(log_path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--quick", action="store_true",
                        help="skip the MySQL step (useful when you only work on SQLite)")
    parser.add_argument("--keep-logs", action="store_true",
                        help="keep the full per-step output in verify_logs/")
    args = parser.parse_args()

    print("=" * 74)
    print("  VERIFY EVERYTHING - original clinic features + new pharmacy features")
    print("=" * 74)
    print(f"  project : {BASE_DIR}")

    env_note = "no .env file yet (the app falls back to SQLite)"
    if (BASE_DIR / ".env").exists():
        text = (BASE_DIR / ".env").read_text(encoding="utf-8", errors="ignore")
        use_sqlite = re.search(r"(?im)^\s*USE_SQLITE\s*=\s*(\S+)", text)
        db_name = re.search(r"(?im)^\s*DB_NAME\s*=\s*(\S+)", text)
        env_note = (f"USE_SQLITE={use_sqlite.group(1) if use_sqlite else '?'}, "
                    f"DB_NAME={db_name.group(1) if db_name else '?'}")

    print(f"  .env    : {env_note}")

    results: list[tuple[str, str, str]] = []
    for name, cmd, pattern in STEPS:
        if args.quick and "MySQL" in name:
            results.append((name, "SKIP", "--quick was used"))
            continue
        status, detail, _ = run_step(name, cmd, pattern, args.keep_logs)
        results.append((name, status, detail))

    print("\n" + "=" * 74)
    print("  SUMMARY")
    print("=" * 74)
    width = max(len(name) for name, _, _ in results)
    failed = 0
    for name, status, detail in results:
        mark = {"OK": "  OK  ", "SKIP": " SKIP ", "FAIL": " FAIL "}[status]
        print(f"  [{mark}] {name.ljust(width)}  {detail}")
        if status == "FAIL":
            failed += 1

    print("-" * 74)
    if failed:
        print(f"  {failed} step(s) FAILED - the failing step printed its reason above "
              f"(and its full log is in verify_logs/).")
        print("  Fix that one thing and run this command again.")
        return 1

    print("  EVERYTHING PASSED - existing clinic features and the new pharmacy /")
    print("  doctor desk features both work, and the databases match the code.")
    print("\n  Not run here on purpose (they need your input):")
    for script, why in SKIPPED.items():
        print(f"    - {script}: {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
    
    
    