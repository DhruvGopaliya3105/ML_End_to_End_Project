"""Snapshots + controlled rollback for the pharmacy data.

Why this exists
---------------
Medicine prices, stock and orders are edited from the admin screen, sometimes
in bulk. A snapshot is a JSON copy of the pharmacy tables; "restore" puts them
back exactly as they were. The rules that make it *controlled*:

* the snapshot payload is hashed (sha256). Restoring needs that hash echoed
  back, so a stale page or a mis-click cannot write the wrong state.
* ``preview`` shows row-by-row what would change (added / removed / modified)
  and writes nothing.
* before any restore, the *current* state is captured as a ``PRE_RESTORE``
  snapshot - so a wrong restore is itself undoable.
* only SUPERUSER holds ``pharmacy.snapshot.restore`` by default; every create
  and every restore lands in ``pharmacy_audit_logs``.
* bulk admin writes (price edit, stock import, medicine delete) automatically
  drop an ``AUTO_PRE_BULK`` snapshot first.

Tables covered per scope (see ``SCOPES``) - the snapshot table itself and the
audit table are deliberately never restored, otherwise a rollback could erase
the evidence that it happened.
"""

import hashlib
import json
import logging
from datetime import (
    date,
    datetime,
    time,
    timedelta
)
from decimal import Decimal

from fastapi import Request
from sqlalchemy import insert
from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy import update as sa_update
from sqlalchemy.orm import Session

from src.database.base import Base
from src.models.pharmacy_snapshot import PharmacySnapshot
from src.services import pharmacy_audit_service as audit


logger = logging.getLogger(__name__)


# =========================================================
# WHAT GETS SNAPSHOT
# =========================================================

CATALOG_TABLES = [
    "diseases",
    "medicines",
    "medicine_diseases",
]

STOCK_TABLES = [
    "medicines",
    "nearby_pharmacies",
    "nearby_pharmacy_stocks",
]

ORDER_TABLES = [
    "pharmacy_orders",
    "pharmacy_order_items",
    "pharmacy_cart_items",
]

# Insert order respects the foreign keys (parents first). Restore deletes in
# the exact reverse order, so MySQL never sees a dangling reference.
PHARMACY_TABLES = [
    "diseases",
    "medicines",
    "medicine_diseases",
    "nearby_pharmacies",
    "nearby_pharmacy_stocks",
    "pharmacy_orders",
    "pharmacy_order_items",
    "pharmacy_cart_items",
]

SCOPES = {
    "PHARMACY": PHARMACY_TABLES,
    "CATALOG": CATALOG_TABLES,
    "STOCK": STOCK_TABLES,
    "ORDERS": ORDER_TABLES,
}

MAX_ROWS_PER_TABLE = int(10000)


# =========================================================
# ENCODING
# =========================================================

def _encode(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return {"__dt__": value.isoformat()}
    if isinstance(value, date):
        return {"__date__": value.isoformat()}
    if isinstance(value, time):
        return {"__time__": value.isoformat()}
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value


def _decode(column_type, value):
    if isinstance(value, dict):
        if "__dt__" in value:
            return datetime.fromisoformat(value["__dt__"])
        if "__date__" in value:
            return date.fromisoformat(value["__date__"])
        if "__time__" in value:
            return time.fromisoformat(value["__time__"])
    if value is None:
        return None
    if isinstance(value, float) and _is_numeric(column_type):
        return Decimal(str(round(value, 2)))
    return value


def _is_numeric(column_type) -> bool:
    return "NUMERIC" in str(column_type).upper() or "DECIMAL" in str(column_type).upper()


def _tables(names: list[str]) -> list:
    return [
        Base.metadata.tables[name]
        for name in names
        if name in Base.metadata.tables
    ]


# =========================================================
# CAPTURE
# =========================================================

def capture(db: Session, scope: str = "PHARMACY") -> tuple[dict, dict, int]:

    scope = (scope or "PHARMACY").upper()
    names = SCOPES.get(scope, PHARMACY_TABLES)

    payload: dict[str, list[dict]] = {}
    counts: dict[str, int] = {}
    total = 0

    for table in _tables(names):

        rows = db.execute(
            select(table).limit(MAX_ROWS_PER_TABLE)
        ).mappings().all()

        encoded = [
            {key: _encode(value) for key, value in dict(row).items()}
            for row in rows
        ]

        payload[table.name] = encoded
        counts[table.name] = len(encoded)
        total += len(encoded)

    return payload, counts, total


def payload_hash(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# =========================================================
# CREATE / LIST
# =========================================================

def create_snapshot(
    db: Session,
    *,
    label: str | None = None,
    description: str | None = None,
    scope: str = "PHARMACY",
    actor: dict | None = None,
    trigger: str = "MANUAL",
    is_pinned: bool = False,
    request: Request | None = None,
    commit: bool = True
) -> PharmacySnapshot:

    scope = (scope or "PHARMACY").upper()

    if scope not in SCOPES:
        raise ValueError(f"Unknown snapshot scope: {scope}")

    payload, counts, total = capture(db, scope)

    body = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False
    )

    created = datetime.utcnow()

    snapshot = PharmacySnapshot(
        label=(label or f"{scope} snapshot {created:%d %b %Y %H:%M}")[:160],
        description=(description or "")[:500] or None,
        scope=scope,
        payload_json=body,
        row_counts_json=json.dumps(counts, sort_keys=True),
        tables_json=json.dumps(SCOPES[scope]),
        row_count=total,
        size_bytes=len(body.encode("utf-8")),
        checksum=payload_hash(payload),
        created_by_user_id=(actor or {}).get("user_id"),
        created_by_name=(actor or {}).get("name") or "System",
        created_by_role=(actor or {}).get("role") or "SYSTEM",
        trigger=trigger[:20],
        is_pinned=bool(is_pinned),
        created_at=created
    )

    db.add(snapshot)

    if commit:
        db.flush()

        audit.log_activity(
            db,
            action="pharmacy.snapshot.create",
            entity_type="snapshot",
            entity_id=snapshot.id,
            description=(
                f"Snapshot '{snapshot.label}' taken ({total} row(s), "
                f"{snapshot.size_bytes} bytes, scope {scope})"
            ),
            actor=actor,
            request=request,
        )
        db.commit()
        db.refresh(snapshot)

    return snapshot


def snapshot_to_dict(snapshot: PharmacySnapshot, *, with_payload: bool = False) -> dict:
    data = {
        "id": snapshot.id,
        "label": snapshot.label,
        "description": snapshot.description,
        "scope": snapshot.scope,
        "trigger": snapshot.trigger,
        "row_count": snapshot.row_count,
        "row_counts": json.loads(snapshot.row_counts_json or "{}"),
        "tables": json.loads(snapshot.tables_json or "[]"),
        "size_bytes": snapshot.size_bytes,
        "checksum": snapshot.checksum,
        "created_by_name": snapshot.created_by_name,
        "created_by_role": snapshot.created_by_role,
        "is_pinned": bool(snapshot.is_pinned),
        "restore_count": snapshot.restore_count,
        "last_restored_at": (
            snapshot.last_restored_at.isoformat()
            if snapshot.last_restored_at else None
        ),
        "last_restored_by": snapshot.last_restored_by,
        "created_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
        "created_at_display": (
            snapshot.created_at.strftime("%d %b %Y, %I:%M %p")
            if snapshot.created_at else ""
        ),
    }

    if with_payload:
        data["payload"] = json.loads(snapshot.payload_json)

    return data


def list_snapshots(db: Session, *, limit: int = 30) -> list[PharmacySnapshot]:
    return (
        db.query(PharmacySnapshot)
        .order_by(PharmacySnapshot.created_at.desc(), PharmacySnapshot.id.desc())
        .limit(limit)
        .all()
    )


def get_snapshot(db: Session, snapshot_id: int) -> PharmacySnapshot | None:
    return db.get(PharmacySnapshot, snapshot_id)


# =========================================================
# PREVIEW (read only)
# =========================================================

def preview_restore(db: Session, snapshot: PharmacySnapshot) -> dict:

    payload = json.loads(snapshot.payload_json)

    tables = []
    changed_rows = 0

    for name, rows in payload.items():

        if name not in Base.metadata.tables:
            tables.append({
                "table": name,
                "error": "this table does not exist in this database anymore",
                "would_add": 0, "would_remove": 0, "would_modify": 0,
            })
            continue

        table = Base.metadata.tables[name]

        snapshot_rows = {
            str(row.get("id")): json.dumps(row, sort_keys=True)
            for row in rows
        }

        current = db.execute(select(table)).mappings().all()

        current_rows = {
            str(dict(row).get("id")): json.dumps(
                {k: _encode(v) for k, v in dict(row).items()}, sort_keys=True
            )
            for row in current
        }

        to_add = len(set(snapshot_rows) - set(current_rows))
        to_remove = len(set(current_rows) - set(snapshot_rows))
        to_modify = len([
            key for key in (set(snapshot_rows) & set(current_rows))
            if snapshot_rows[key] != current_rows[key]
        ])

        changed_rows += to_add + to_remove + to_modify

        tables.append({
            "table": name,
            "would_add": to_add,
            "would_remove": to_remove,
            "would_modify": to_modify,
            "snapshot_rows": len(snapshot_rows),
            "current_rows": len(current_rows),
            "sample_added": sorted(set(snapshot_rows) - set(current_rows))[:5],
            "sample_removed": sorted(set(current_rows) - set(snapshot_rows))[:5],
        })

    return {
        "snapshot_id": snapshot.id,
        "label": snapshot.label,
        "scope": snapshot.scope,
        "checksum": snapshot.checksum,
        "created_at_display": (
            snapshot.created_at.strftime("%d %b %Y, %I:%M %p")
            if snapshot.created_at else ""
        ),
        "tables": tables,
        "total_changes": changed_rows,
        "dangerous": changed_rows > 0,
    }


# =========================================================
# RESTORE
# =========================================================


def _set_foreign_key_checks(db: Session, enable: bool) -> bool:
    """Turn MySQL/SQLite foreign key enforcement off for one bulk write.

    A restore deletes and re-adds the same ids. MySQL enforces foreign keys and
    refuses that in the middle of the transaction (SQLite does not enforce them
    at all by default, which is exactly why this problem only shows up on a
    real MySQL server). The keys are switched back on in a ``finally`` block, and
    the ids themselves are preserved, so rows in tables that are *not* part of
    the snapshot - order items, for example - still point at a real medicine.
    """

    dialect = db.get_bind().dialect.name

    try:
        if dialect == "mysql":
            db.execute(text("SET FOREIGN_KEY_CHECKS = " + ("1" if enable else "0")))
        elif dialect.startswith("sqlite"):
            db.execute(text("PRAGMA foreign_keys = " + ("ON" if enable else "OFF")))
        else:
            return False
    except Exception:  # noqa: BLE001 - never let bookkeeping break the rollback
        logger.warning("could not change foreign key checks on %s", dialect,
                       exc_info=True)
        return False

    return True


def restore_snapshot(
    db: Session,
    snapshot: PharmacySnapshot,
    *,
    checksum: str,
    actor: dict | None = None,
    request: Request | None = None
) -> dict:

    if (checksum or "").strip() != snapshot.checksum:
        raise ValueError(
            "Checksum did not match - the restore was rejected. Reload the "
            "page and confirm again (the snapshot may have been replaced)."
        )

    # Undo point first: if this restore turns out to be the wrong one, restore
    # this row instead.
    safety = create_snapshot(
        db,
        label=f"Before restore of #{snapshot.id} ({snapshot.label})",
        description=(
            f"Automatic undo point taken by {(actor or {}).get('name', 'system')} "
            f"before restoring snapshot #{snapshot.id}."
        ),
        scope=snapshot.scope,
        actor=actor,
        trigger="PRE_RESTORE",
        request=request,
        is_pinned=False,
        commit=False
    )

    db.commit()
    db.refresh(safety)

    payload = json.loads(snapshot.payload_json)

    stats: dict[str, dict] = {}

    # Only the tables inside this snapshot are touched, and inside them a row is
    # updated (not deleted + re-inserted) whenever its id still exists. That
    # keeps ids stable for rows in other tables that point at them.
    checks_off = _set_foreign_key_checks(db, False)

    try:
        for name, rows in payload.items():

            if name not in Base.metadata.tables:
                stats[name] = {"restored": 0, "skipped": "table missing"}
                continue

            table = Base.metadata.tables[name]
            pk_name = list(table.primary_key.columns)[0].name

            wanted: dict = {}

            for row in rows:
                values = {
                    column.name: _decode(column.type, row.get(column.name))
                    for column in table.columns
                }
                wanted[values[pk_name]] = values

            live_ids = {
                value for (value,) in db.execute(select(table.c[pk_name]))
            }

            extra = sorted(live_ids - set(wanted))

            if extra:
                # rows created after the snapshot: a rollback removes them again
                db.execute(sa_delete(table).where(table.c[pk_name].in_(extra)))

            to_update = [values for key, values in wanted.items() if key in live_ids]
            to_insert = [values for key, values in wanted.items() if key not in live_ids]

            # One UPDATE per row, with the id in the WHERE clause. Feeding a
            # list of dicts to update() is not enough: without an explicit WHERE
            # every row would be written with the same values, which then blows
            # up on the primary key ("UNIQUE constraint failed: diseases.id").
            for values in to_update:
                pk_value = values.pop(pk_name)
                db.execute(
                    sa_update(table).where(table.c[pk_name] == pk_value).values(**values)
                )

            for start in range(0, len(to_insert), 200):
                db.execute(insert(table), to_insert[start:start + 200])

            stats[name] = {
                "restored": len(wanted),
                "updated": len(to_update),
                "inserted": len(to_insert),
                "deleted": len(extra),
            }
    finally:
        if checks_off:
            _set_foreign_key_checks(db, True)

    # the objects already loaded in this session are now out of date
    db.expire_all()

    snapshot.restore_count = int(snapshot.restore_count or 0) + 1
    snapshot.last_restored_at = datetime.utcnow()
    snapshot.last_restored_by = (actor or {}).get("name")

    audit.log_activity(
        db,
        action="pharmacy.snapshot.restore",
        entity_type="snapshot",
        entity_id=snapshot.id,
        description=(
            f"Restored '{snapshot.label}' ({json.dumps(stats)}) - undo point "
            f"snapshot #{safety.id} created"
        ),
        severity="CRITICAL",
        actor=actor,
        request=request,
        rollback_available=True,
        snapshot_id=safety.id,
    )

    db.commit()

    return {
        "restored_snapshot_id": snapshot.id,
        "undo_snapshot_id": safety.id,
        "tables": stats,
        "checksum": snapshot.checksum,
    }


# =========================================================
# CLEANUP
# =========================================================

def prune(
    db: Session,
    *,
    keep: int = 20,
    older_than_days: int | None = None,
    actor: dict | None = None,
    request: Request | None = None
) -> dict:

    query = (
        db.query(PharmacySnapshot)
        .filter(PharmacySnapshot.is_pinned.is_(False))
    )

    if older_than_days:
        cutoff = datetime.utcnow() - timedelta(days=int(older_than_days))
        query = query.filter(PharmacySnapshot.created_at < cutoff)

    candidates = query.order_by(PharmacySnapshot.created_at.asc()).all()

    if keep:
        # Whatever happens, the newest `keep` snapshots stay recoverable.
        keep_ids = {
            row.id
            for row in db.query(PharmacySnapshot.id)
            .filter(PharmacySnapshot.is_pinned.is_(False))
            .order_by(PharmacySnapshot.created_at.desc())
            .limit(int(keep))
            .all()
        }
        candidates = [row for row in candidates if row.id not in keep_ids]

    removed = 0

    for row in candidates:
        db.delete(row)
        removed += 1

    if removed:
        audit.log_activity(
            db,
            action="pharmacy.snapshot.prune",
            entity_type="snapshot",
            entity_id=None,
            description=f"Removed {removed} old snapshot(s) (newest {keep} kept)",
            severity="WARN",
            actor=actor,
            request=request,
        )

    db.commit()

    return {"removed": removed, "kept": keep}


def delete_snapshot(
    db: Session,
    snapshot: PharmacySnapshot,
    *,
    actor: dict | None = None,
    request: Request | None = None
) -> None:

    if snapshot.is_pinned:
        raise ValueError("Pinned snapshots cannot be deleted. Unpin it first.")

    label = snapshot.label
    snapshot_id = snapshot.id

    db.delete(snapshot)

    audit.log_activity(
        db,
        action="pharmacy.snapshot.delete",
        entity_type="snapshot",
        entity_id=snapshot_id,
        description=f"Snapshot '{label}' deleted",
        severity="CRITICAL",
        actor=actor,
        request=request,
    )

    db.commit()


# =========================================================
# SMALL EXTRAS
# =========================================================

def export_snapshot_json(snapshot: PharmacySnapshot) -> str:
    """Same bytes a restore would write, handy as a manual backup file."""

    body = json.loads(snapshot.payload_json)

    return json.dumps({
        "exported_at": datetime.utcnow().isoformat(),
        "snapshot": snapshot_to_dict(snapshot),
        "data": body,
    }, indent=2, ensure_ascii=False)


def bulk_price_update(
    db: Session,
    *,
    percent: float | None = None,
    flat: float | None = None,
    disease_slug: str | None = None,
    only_active: bool = True
) -> dict:
    """Used by the admin 'bulk price change' box.

    Always snapshots first, and returns the snapshot id so the change can be
    rolled back from the same screen.
    """

    from src.models.medicine import Medicine
    from src.services import pharmacy_catalog_service as catalog

    if percent is None and flat is None:
        raise ValueError("Give either a percentage or a flat amount.")

    safety = create_snapshot(
        db,
        label="Before bulk price change",
        description=(
            f"Automatic: percent={percent}, flat={flat}, "
            f"disease={disease_slug}"
        ),
        scope="CATALOG",
        trigger="AUTO_PRE_BULK",
        commit=False
    )

    db.commit()
    db.refresh(safety)

    query = db.query(Medicine)

    if only_active:
        query = query.filter(Medicine.is_active.is_(True))

    if disease_slug:
        disease = catalog.get_disease_by_slug(db, disease_slug)
        if disease is None:
            raise ValueError("That disease/category does not exist.")
        from src.models.medicine_disease import MedicineDisease
        query = query.filter(
            Medicine.id.in_(
                db.query(MedicineDisease.medicine_id)
                .filter(MedicineDisease.disease_id == disease.id)
            )
        )

    changed = 0

    for medicine in query.all():

        old_price = float(medicine.price or 0)

        if percent is not None:
            new_price = round(old_price * (1 + float(percent) / 100.0), 2)
        else:
            new_price = round(old_price + float(flat or 0), 2)

        new_price = max(0.0, new_price)

        if abs(new_price - old_price) < 0.005:
            continue

        medicine.price = new_price
        changed += 1

    db.commit()

    return {
        "changed": changed,
        "snapshot_id": safety.id,
        "undo": f"POST /pharmacy/admin/snapshots/{safety.id}/restore",
    }
