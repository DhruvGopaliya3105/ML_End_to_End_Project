"""Central, absolute paths for the project.

Every path here is derived from this file's own location, so the app behaves
identically no matter which directory it is started from. Previously several
modules used relative paths such as "templates", "artifacts" and
"./sanjeevani_clinic.db", which silently pointed at different (or missing)
files when the server was started from anywhere other than the repo root.
"""

import os
from pathlib import Path

# <repo root>/src/config.py  ->  <repo root>
BASE_DIR = Path(__file__).resolve().parent.parent

SRC_DIR = BASE_DIR / "src"
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

# Trained ML artifacts produced by src/components/model_trainer.py
ARTIFACTS_DIR = BASE_DIR / "artifacts"

# Uploaded medical reports
UPLOAD_DIR = BASE_DIR / "uploads" / "medical_reports"

# Fallback SQLite database (only used when MySQL is unavailable / USE_SQLITE=true)
# SQLITE_DB_PATH can be pointed at another file - used by test_pharmacy.py to run
# the pharmacy smoke test against a throwaway copy instead of your real data.
SQLITE_DB_PATH = Path(
    os.getenv("SQLITE_DB_PATH") or (BASE_DIR / "sanjeevani_clinic.db")
)

# Logs written by src/logger.py
LOGS_DIR = BASE_DIR / "logs"
