"""Regenerate ``pharmacy_setup.sql`` (the MySQL DDL for the pharmacy module).

You normally do NOT need to run this: ``main.py`` calls
``Base.metadata.create_all()`` on every startup, so the pharmacy tables appear
by themselves in both MySQL and SQLite. This script exists for the two cases
where hand-written SQL is handy:

* you want to read / review the exact DDL before it touches your MySQL schema,
  or run it in MySQL Workbench next to ``database_setup.sql``;
* you want a schema snapshot in git that shows what the module owns.

    python pharmacy_schema_export.py        # rewrites pharmacy_setup.sql

The file it writes is derived from the models in ``src/models/``, so it can
never drift from the code.
"""

import os
import re
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("USE_SQLITE", "true")
os.environ.setdefault("GROQ_API_KEY", "schema-export")

import src.models  # noqa: F401,E402  (registers every table on Base.metadata)
from src.database.base import Base  # noqa: E402

from sqlalchemy.dialects import mysql  # noqa: E402
from sqlalchemy.schema import (  # noqa: E402
    CreateIndex,
    CreateTable
)


# Tables the pharmacy module owns, in dependency order (parents first).
PHARMACY_TABLES = [
    "diseases",
    "medicines",
    "medicine_diseases",
    "pharmacy_cart_items",
    "nearby_pharmacies",
    "nearby_pharmacy_stocks",
    "pharmacy_snapshots",
    "pharmacy_orders",
    "pharmacy_order_items",
    "pharmacy_audit_logs",
    "role_permissions",
    "doctor_patient_notes",
]

HEADER = """-- ============================================================================
--  SANJEEVANI CLINIC - PHARMACY MODULE SCHEMA (MySQL)
-- ============================================================================
--
--  GENERATED FILE - do not edit by hand.
--  Source of truth: src/models/*.py
--  Regenerate with:  python pharmacy_schema_export.py
--  Generated on:    {generated}
--
--  YOU USUALLY DO NOT NEED THIS FILE. main.py runs Base.metadata.create_all()
--  at startup, which creates every table below automatically (MySQL and
--  SQLite). Use this script when you prefer to review / apply the DDL in
--  MySQL Workbench yourself.
--
--  HOW TO RUN
--  ----------
--  1. Open MySQL Workbench, connect to your local server.
--  2. File -> Open SQL Script -> this file.
--  3. Run it. It is safe to run more than once: every statement is
--     CREATE TABLE IF NOT EXISTS, so existing pharmacy data is never touched.
--     (There is deliberately NO DROP DATABASE / DROP TABLE here, unlike
--     database_setup.sql, because this file may be run against a live pharmacy.)
--  4. Then load the catalog + demo data:
--         python seed_pharmacy.py
--
--  12 tables:
--    medicines, diseases, medicine_diseases      - the catalog the patient shops from
--    pharmacy_cart_items                          - cart, stored per user in SQL
--    pharmacy_orders, pharmacy_order_items        - purchases + frozen price snapshots
--    nearby_pharmacies, nearby_pharmacy_stocks    - partner chemists for the emergency search
--    pharmacy_snapshots                           - rollback / restore points (super user)
--    pharmacy_audit_logs                          - append-only trail (super user)
--    role_permissions                             - role -> permission overrides (RBAC)
--    doctor_patient_notes                         - the doctor desk: notes kept on a patient file
--
--  Foreign keys point at the existing `users`, `doctors`, `prescriptions`,
--  `prescription_medicines` and `medicines` tables, so run database_setup.sql
--  first if this is a brand new database.
-- ============================================================================


USE sanjeevani_clinic;

SET NAMES utf8mb4;

"""


def quote_name(name: str) -> str:
    return f"`{name}`"


def render_table(table) -> list[str]:
    """Pretty-print one CREATE TABLE with one column per line."""

    compiled = str(
        CreateTable(table).compile(dialect=mysql.dialect())
    ).strip()

    open_at = compiled.index("(")
    close_at = compiled.rindex(")")

    head = f"CREATE TABLE IF NOT EXISTS {quote_name(table.name)} ("

    # Re-split on commas that are not inside parentheses.
    inner = compiled[open_at + 1:close_at]
    parts = []
    depth = 0
    current = ""

    for char in inner:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1

        if char == "," and depth == 0:
            parts.append(current.strip())
            current = ""
        else:
            current += char

    if current.strip():
        parts.append(current.strip())

    # Move table-level constraints (PRIMARY KEY / UNIQUE / FOREIGN KEY) to the
    # end, which is what MySQL Workbench produces and what makes a review
    # readable.
    constraints = [
        part for part in parts
        if part.upper().startswith((
            "PRIMARY KEY", "UNIQUE", "CONSTRAINT", "FOREIGN KEY", "KEY"
        ))
    ]
    columns = [part for part in parts if part not in constraints]

    body = [part for part in columns + constraints]
    body = [
        "  " + " ".join(part.split()) + ("," if index < len(body) - 1 else "")
        for index, part in enumerate(body)
    ]

    # SQLAlchemy compiles table-level constraints (UNIQUE / FOREIGN KEY) into
    # the body already, but it keeps single-column unique=True / index=True in
    # separate objects that would need their own CREATE INDEX statements - and
    # MySQL has no "CREATE INDEX IF NOT EXISTS". So those are appended here as
    # table-level clauses, which keeps this file to one statement per table and
    # therefore re-runnable. Anything the compiler already wrote is detected
    # below and skipped, otherwise MySQL fails with error 1061 (duplicate key
    # name).
    body_text = "\n".join(body)

    def names(raw):
        return frozenset(part.strip().strip("`") for part in raw.split(",") if part.strip())

    already = set()
    for match in re.finditer(r"UNIQUE(?:\s+KEY)?(?:\s+`?\w+`?)?\s*\(([^)]*)\)", body_text):
        already.add(names(match.group(1)))
    for match in re.finditer(r"FOREIGN KEY\s*\(([^)]*)\)", body_text):
        pass  # FK indexes are created by MySQL itself, nothing to add

    extra_by_key: dict[frozenset, str] = {}

    def add(kind, raw_columns, name):
        columns = names(raw_columns)
        if columns in already or columns in extra_by_key:
            return
        quoted = ", ".join(f"`{column}`" for column in columns)
        keyword = "UNIQUE KEY" if kind == "unique" else "INDEX"
        extra_by_key[columns] = f"  {keyword} `{name}` ({quoted})"

    pk_columns = {column.name for column in table.primary_key.columns}

    for index in sorted(table.indexes, key=lambda item: item.name or ""):
        # an index on the primary key alone is noise in MySQL (the PK already is
        # one), so skip it and keep the file short
        if (
            not index.unique
            and len(index.columns) == 1
            and index.columns[0].name in pk_columns
        ):
            continue
        cols = ", ".join(f"`{column.name}`" for column in index.columns)
        add("unique" if index.unique else "index",
            cols,
            index.name or f"{'uq' if index.unique else 'ix'}_{table.name}")

    for column in table.columns:
        if column.unique:
            add("unique", f"`{column.name}`", f"{table.name}_{column.name}_key")

    extra = list(extra_by_key.values())

    if extra:
        body[-1] = body[-1] + ","
        body.extend(
            line + ("," if position < len(extra) - 1 else "")
            for position, line in enumerate(extra)
        )

    tail = (
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 "
        "COLLATE=utf8mb4_unicode_ci;"
    )

    out = [head, *body, tail]

    # No separate CREATE INDEX statements: every index (and every UNIQUE
    # constraint) is already part of the CREATE TABLE above, and MySQL has no
    # "CREATE INDEX IF NOT EXISTS", so repeating them would break a re-run.

    return out


def main() -> int:

    missing = [
        name for name in PHARMACY_TABLES if name not in Base.metadata.tables
    ]

    if missing:
        print(f"unknown tables in the model list: {missing}")
        return 1

    statements = [HEADER.format(generated=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"))]

    for name in PHARMACY_TABLES:
        table = Base.metadata.tables[name]
        statements.append(f"-- ---- {name} " + "-" * max(4, 66 - len(name)))
        statements.append("\n".join(render_table(table)))
        statements.append("")

    statements.append("""
-- ============================================================================
--  OPTIONAL: verify it worked
-- ============================================================================

SELECT
    (SELECT COUNT(*) FROM medicines)          AS medicines,
    (SELECT COUNT(*) FROM diseases)           AS diseases,
    (SELECT COUNT(*) FROM medicine_diseases)  AS links,
    (SELECT COUNT(*) FROM nearby_pharmacies)  AS nearby_shops,
    (SELECT COUNT(*) FROM pharmacy_orders)    AS orders,
    (SELECT COUNT(*) FROM pharmacy_snapshots) AS snapshots,
    (SELECT COUNT(*) FROM pharmacy_audit_logs) AS audit_rows;

-- If every count is 0, the tables were created but not filled yet:
--     python seed_pharmacy.py
-- ============================================================================
""")

    target = BASE_DIR / "pharmacy_setup.sql"
    target.write_text("\n".join(statements), encoding="utf-8")

    print(f"wrote {target} ({target.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
