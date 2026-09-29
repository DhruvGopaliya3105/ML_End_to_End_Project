# Sanjeevani Clinic API

## Run locally

Use Python 3.13 or newer, install the project dependencies, and start the app
from the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

The API uses MySQL for database-backed routes. Set `DB_USER`, `DB_PASSWORD`,
`DB_HOST`, `DB_PORT` (defaults to `3306`), and `DB_NAME` in the environment or
in a local `.env` file. Set `SESSION_SECRET` to a long random value before
using sessions outside local development. `GROQ_API_KEY` is needed for AI
features.

The API starts even when MySQL is unavailable so that `/`, `/health`, and the
interactive API docs remain accessible. The startup log and `/health` response
report the database state; database-backed routes require the database to be
available. Tables are created automatically when the database is reachable.
Open `/docs` for the interactive API documentation.
