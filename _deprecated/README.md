# Unused / superseded files

Nothing in this folder is imported by the running application. They were moved
out of the live source tree because they shadowed or duplicated real modules and
made it hard to tell which code was actually in use.

| File | Why it is here |
|---|---|
| `main_backup_current.py` | Older copy of the app entry point. `main.py` is the real one. |
| `src/routers/documents_backup.py` | Older copy of the medical-reports router. `src/routers/documents.py` is the real one and is the only one mounted in `main.py`. |
| `templates/reschedule_app.py` | A Python file that had been dropped inside the templates folder. Not a template, never used. |
| `templates/medical_reports_backup.html` | Older copy of `medical_reports.html`. |
| `templates/__init__.py` | Not needed; Jinja2 does not use an `__init__.py` in the template dir. |

Delete this folder whenever you like - nothing references it.
