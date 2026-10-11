"""Catalog reads/writes for the pharmacy.

The pharmacy page, the search box, the prescription matching and every admin
edit of a medicine all come through this module, so stock rules and price
rounding are decided in exactly one place.
"""

import logging
import re
from datetime import datetime
from difflib import get_close_matches

from sqlalchemy import (
    func,
    or_,
    select
)
from sqlalchemy.orm import Session

from src.models.disease import Disease
from src.models.medicine import Medicine
from src.models.medicine_disease import MedicineDisease


logger = logging.getLogger(__name__)

FALLBACK_IMAGES = {
    "TABLET": "/static/images/pharmacy/tablet.svg",
    "CAPSULE": "/static/images/pharmacy/capsule.svg",
    "SYRUP": "/static/images/pharmacy/syrup.svg",
    "DROPS": "/static/images/pharmacy/drops.svg",
    "OINTMENT": "/static/images/pharmacy/ointment.svg",
    "INJECTION": "/static/images/pharmacy/injection.svg",
    "POWDER": "/static/images/pharmacy/powder.svg",
    "DEVICE": "/static/images/pharmacy/first-aid.svg",
}


# =========================================================
# TEXT HELPERS
# =========================================================

_STOPWORDS = {
    "tablet", "tablets", "tabs", "cap", "caps", "capsule", "capsules",
    "syr", "syrup", "mg", "ml", "tab", "strip", "pack", "of", "the", "and",
}


def normalize_name(value: str | None) -> str:
    if not value:
        return ""

    value = value.lower().strip()
    value = re.sub(r"\(.*?\)", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def name_tokens(value: str | None) -> list[str]:
    normalized = normalize_name(value)
    return [
        token for token in normalized.split(" ")
        if len(token) > 2 and token not in _STOPWORDS
    ]


def money(value) -> float:
    try:
        return round(float(value or 0), 2)
    except (TypeError, ValueError):
        return 0.0


# =========================================================
# DISEASES / CATEGORIES
# =========================================================

def list_diseases(
    db: Session,
    *,
    active_only: bool = True,
    with_counts: bool = True
) -> list[dict]:

    query = (
        db.query(Disease)
        .order_by(Disease.group_name.isnot(None).desc(), Disease.name)
    )

    if active_only:
        query = query.filter(Disease.is_active.is_(True))

    diseases = query.all()

    if not with_counts:
        return [
            {
                "id": d.id,
                "name": d.name,
                "slug": d.slug,
                "group_name": d.group_name,
                "icon": d.icon,
                "description": d.description,
                "count": 0,
            }
            for d in diseases
        ]

    counts = dict(
        db.execute(
            select(
                MedicineDisease.disease_id,
                func.count(MedicineDisease.id)
            )
            .select_from(MedicineDisease)
            .join(
                Medicine,
                Medicine.id == MedicineDisease.medicine_id
            )
            .where(Medicine.is_active.is_(True))
            .group_by(MedicineDisease.disease_id)
        ).all()
    )

    return [
        {
            "id": d.id,
            "name": d.name,
            "slug": d.slug,
            "group_name": d.group_name,
            "icon": d.icon,
            "description": d.description,
            "count": int(counts.get(d.id, 0)),
        }
        for d in diseases
    ]


def get_disease_by_slug(db: Session, slug: str | None) -> Disease | None:
    if not slug:
        return None
    return (
        db.query(Disease)
        .filter(func.lower(Disease.slug) == slug.lower())
        .first()
    )


def get_or_create_disease(
    db: Session,
    name: str,
    *,
    group_name: str | None = None,
    icon: str | None = None,
    description: str | None = None
) -> Disease:

    clean_name = (name or "").strip()

    if not clean_name:
        raise ValueError("Disease name is required")

    slug = re.sub(r"[^a-z0-9]+", "-", clean_name.lower()).strip("-")

    disease = (
        db.query(Disease)
        .filter(or_(Disease.slug == slug, func.lower(Disease.name) == clean_name.lower()))
        .first()
    )

    if disease is not None:
        return disease

    disease = Disease(
        name=clean_name[:120],
        slug=slug[:120],
        group_name=(group_name or None),
        icon=icon,
        description=description
    )

    db.add(disease)
    db.flush()

    return disease


def diseases_for(db: Session, medicine_id: int) -> list[dict]:
    rows = (
        db.query(Disease, MedicineDisease.is_primary)
        .join(MedicineDisease, MedicineDisease.disease_id == Disease.id)
        .filter(MedicineDisease.medicine_id == medicine_id)
        .order_by(MedicineDisease.is_primary.desc(), Disease.name)
        .all()
    )

    return [
        {
            "id": disease.id,
            "name": disease.name,
            "slug": disease.slug,
            "icon": disease.icon,
            "is_primary": bool(is_primary),
        }
        for disease, is_primary in rows
    ]


def set_diseases(db: Session, medicine: Medicine, names: list[str] | None) -> None:
    """Replace the disease tags of one medicine (case insensitive, deduped)."""

    db.query(MedicineDisease).filter(
        MedicineDisease.medicine_id == medicine.id
    ).delete(synchronize_session=False)

    db.flush()

    seen: set[int] = set()

    for index, raw in enumerate(names or []):
        name = (raw or "").strip()

        if not name:
            continue

        disease = get_or_create_disease(db, name)

        if disease.id in seen:
            continue

        seen.add(disease.id)

        db.add(MedicineDisease(
            medicine_id=medicine.id,
            disease_id=disease.id,
            is_primary=index == 0,
        ))

    db.flush()


# =========================================================
# MEDICINE LISTING
# =========================================================

def build_medicine_query(
    db: Session,
    *,
    disease_slug: str | None = None,
    search: str | None = None,
    form: str | None = None,
    only_available: bool = False,
    include_inactive: bool = False,
    requires_prescription: str | None = None,
    low_stock_only: bool = False
):

    query = db.query(Medicine)

    if not include_inactive:
        query = query.filter(Medicine.is_active.is_(True))

    disease = get_disease_by_slug(db, disease_slug)

    if disease is not None:
        query = (
            query
            .join(MedicineDisease, MedicineDisease.medicine_id == Medicine.id)
            .filter(MedicineDisease.disease_id == disease.id)
            .distinct()
        )

    if search:
        like = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Medicine.name.ilike(like),
                Medicine.generic_name.ilike(like),
                Medicine.brand.ilike(like),
                Medicine.sku.ilike(like),
                Medicine.strength.ilike(like),
            )
        )

    if form:
        query = query.filter(func.upper(Medicine.form) == form.upper())

    if only_available:
        query = query.filter(Medicine.stock > 0)

    if requires_prescription == "yes":
        query = query.filter(Medicine.requires_prescription.is_(True))
    elif requires_prescription == "no":
        query = query.filter(Medicine.requires_prescription.is_(False))

    if low_stock_only:
        query = query.filter(Medicine.stock <= Medicine.low_stock_alert)

    return query


SORTS = {
    "popular": Medicine.name.asc(),
    "price_low": Medicine.price.asc(),
    "price_high": Medicine.price.desc(),
    "name_asc": Medicine.name.asc(),
    "stock_low": Medicine.stock.asc(),
    "newest": Medicine.id.desc(),
}


def list_medicines(
    db: Session,
    *,
    sort: str = "popular",
    limit: int = 60,
    offset: int = 0,
    **filters
) -> tuple[list[Medicine], int]:

    query = build_medicine_query(db, **filters)

    try:
        total = query.count()
    except Exception:  # noqa: BLE001 - COUNT over a DISTINCT join on MySQL
        db.rollback()
        total = len(query.all())

    medicines = (
        query
        .order_by(SORTS.get(sort, SORTS["popular"]))
        .offset(max(0, offset))
        .limit(min(max(1, limit), 300))
        .all()
    )

    return medicines, total


def search_medicines(
    db: Session,
    search: str | None,
    *,
    limit: int = 12
) -> list[Medicine]:

    if not search or not search.strip():
        return []

    return (
        build_medicine_query(db, search=search, only_available=False)
        .order_by(Medicine.stock.desc(), Medicine.name.asc())
        .limit(limit)
        .all()
    )


def get_medicine(db: Session, medicine_id: int) -> Medicine | None:
    return db.get(Medicine, medicine_id)


def get_medicine_by_sku(db: Session, sku: str) -> Medicine | None:
    return (
        db.query(Medicine)
        .filter(func.upper(Medicine.sku) == sku.upper())
        .first()
    )


def next_sku(db: Session) -> str:
    highest = db.query(func.max(Medicine.id)).scalar() or 0
    return f"MED-{int(highest) + 1:05d}"


def unique_sku(db: Session, wanted: str | None) -> str:
    wanted = (wanted or "").strip()

    if not wanted:
        return next_sku(db)

    base = re.sub(r"[^A-Za-z0-9-]", "-", wanted.upper())[:36]
    candidate = base
    counter = 1

    while get_medicine_by_sku(db, candidate) is not None:
        counter += 1
        candidate = f"{base}-{counter}"[:36]

    return candidate


# =========================================================
# SERIALIZATION
# =========================================================

def medicine_image(medicine: Medicine | None) -> str:
    if medicine is None:
        return "/static/images/pharmacy/not-found.svg"

    if medicine.image_url:
        return medicine.image_url

    if medicine.image_path:
        path = medicine.image_path
        return path if path.startswith("/") else f"/static/{path.lstrip('/')}"

    return FALLBACK_IMAGES.get(
        (medicine.form or "TABLET").upper(),
        "/static/images/pharmacy/tablet.svg"
    )


def medicine_to_dict(
    db: Session,
    medicine: Medicine,
    *,
    with_diseases: bool = True,
    max_qty: int | None = None
) -> dict:

    stock = int(medicine.stock or 0)
    price = money(medicine.price)
    mrp = money(medicine.mrp)

    data = {
        "id": medicine.id,
        "sku": medicine.sku,
        "name": medicine.name,
        "generic_name": medicine.generic_name,
        "brand": medicine.brand,
        "form": medicine.form,
        "strength": medicine.strength,
        "pack_size": medicine.pack_size,
        "price": price,
        "mrp": mrp or None,
        "savings_pct": (
            max(0, round((mrp - price) / mrp * 100))
            if mrp > price else 0
        ),
        "stock": stock,
        "available": bool(medicine.is_active and stock > 0),
        "low_stock": 0 < stock <= int(medicine.low_stock_alert or 0),
        "low_stock_alert": int(medicine.low_stock_alert or 0),
        "requires_prescription": bool(medicine.requires_prescription),
        "warning": medicine.warning,
        "description": medicine.description,
        "dosage_info": medicine.dosage_info,
        "side_effects": medicine.side_effects,
        "is_active": bool(medicine.is_active),
        "image": medicine_image(medicine),
        "max_qty": max_qty if max_qty is not None else max(0, min(stock, 20)),
    }

    data["diseases"] = (
        diseases_for(db, medicine.id) if with_diseases else []
    )

    data["disease_names"] = [d["name"] for d in data["diseases"]]

    return data


# =========================================================
# PRESCRIPTION MATCHING
# =========================================================

def match_medicine(db: Session, medicine_name: str) -> Medicine | None:
    """Best-effort link between a doctor's free-text line and our catalog.

    Order of attempts: exact normalized name -> exact generic name -> first
    distinctive token -> closest string in the catalog. Never returns a
    random product: if the match is weak the caller shows "not in our stock"
    and offers the nearby-shop search instead.
    """

    normalized = normalize_name(medicine_name)

    if not normalized:
        return None

    active = Medicine.is_active.is_(True)

    exact = (
        db.query(Medicine)
        .filter(active)
        .filter(or_(
            func.lower(Medicine.name) == normalized,
            func.lower(Medicine.generic_name) == normalized,
        ))
        .order_by(Medicine.stock.desc())
        .first()
    )

    if exact is not None:
        return exact

    contains = (
        db.query(Medicine)
        .filter(active)
        .filter(
            or_(
                func.lower(Medicine.name).like(f"%{normalized}%"),
                func.lower(Medicine.generic_name).like(f"%{normalized}%"),
            )
        )
        .order_by(Medicine.stock.desc(), Medicine.name.asc())
        .first()
    )

    if contains is not None:
        return contains

    tokens = name_tokens(medicine_name)

    for token in tokens:
        hit = (
            db.query(Medicine)
            .filter(active)
            .filter(
                or_(
                    func.lower(Medicine.name).like(f"{token}%"),
                    func.lower(Medicine.generic_name).like(f"%{token}%"),
                )
            )
            .order_by(Medicine.stock.desc(), Medicine.name.asc())
            .first()
        )

        if hit is not None:
            return hit

    names = [
        (medicine.name, medicine.id)
        for medicine in db.query(Medicine.id, Medicine.name).filter(active).all()
    ]

    if names:
        best = get_close_matches(
            normalized,
            [name for name, _id in names],
            n=1,
            cutoff=0.72
        )
        if best:
            wanted = best[0]
            for name, medicine_id in names:
                if name == wanted:
                    return db.get(Medicine, medicine_id)

    return None


# =========================================================
# ADMIN WRITES
# =========================================================

MUTABLE_FIELDS = (
    "name", "generic_name", "brand", "form", "strength", "pack_size",
    "mrp", "description", "dosage_info", "side_effects", "warning",
    "image_path", "image_url", "is_active",
)


def create_medicine(
    db: Session,
    data: dict,
    *,
    diseases: list[str] | None = None
) -> Medicine:

    medicine = Medicine(
        sku=unique_sku(db, data.get("sku")),
        name=(data.get("name") or "").strip()[:200],
        generic_name=data.get("generic_name"),
        brand=data.get("brand"),
        form=(data.get("form") or "TABLET").upper()[:40],
        strength=data.get("strength"),
        pack_size=data.get("pack_size"),
        price=money(data.get("price")),
        mrp=money(data.get("mrp")) or None,
        stock=max(0, int(data.get("stock") or 0)),
        low_stock_alert=int(data.get("low_stock_alert") or 10),
        requires_prescription=bool(data.get("requires_prescription")),
        warning=data.get("warning"),
        image_path=data.get("image_path"),
        image_url=data.get("image_url"),
        description=data.get("description"),
        dosage_info=data.get("dosage_info"),
        side_effects=data.get("side_effects"),
        is_active=data.get("is_active", True),
    )

    if not medicine.name:
        raise ValueError("Medicine name is required")

    db.add(medicine)
    db.flush()

    set_diseases(db, medicine, diseases or [medicine.form or "General"])

    db.commit()
    db.refresh(medicine)

    return medicine


def update_medicine(
    db: Session,
    medicine: Medicine,
    data: dict,
    *,
    diseases: list[str] | None = None,
    set_stock: bool | None = None
) -> Medicine:

    for field in MUTABLE_FIELDS:
        if field in data and data[field] is not None:
            setattr(medicine, field, data[field])

    if "price" in data and data["price"] is not None:
        medicine.price = money(data["price"])

    if set_stock is not None:
        medicine.stock = max(0, int(set_stock))
    elif "stock" in data and data["stock"] is not None:
        medicine.stock = max(0, int(data["stock"]))

    if "requires_prescription" in data and data["requires_prescription"] is not None:
        medicine.requires_prescription = bool(data["requires_prescription"])

    if "is_active" in data and data["is_active"] is not None:
        medicine.is_active = bool(data["is_active"])

    if diseases is not None:
        set_diseases(db, medicine, diseases)

    medicine.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(medicine)

    return medicine


def adjust_stock(
    db: Session,
    medicine: Medicine,
    delta: int,
    *,
    absolute: bool = False
) -> Medicine:

    if absolute:
        medicine.stock = max(0, int(delta))
    else:
        medicine.stock = max(0, int(medicine.stock or 0) + int(delta))

    medicine.updated_at = datetime.utcnow()

    db.flush()

    return medicine


def set_active(db: Session, medicine: Medicine, is_active: bool) -> Medicine:
    medicine.is_active = bool(is_active)
    medicine.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(medicine)
    return medicine


def delete_medicine(db: Session, medicine: Medicine) -> None:
    """Hard delete. Callers must snapshot first (the admin route does)."""

    db.query(MedicineDisease).filter(
        MedicineDisease.medicine_id == medicine.id
    ).delete(synchronize_session=False)

    db.delete(medicine)
    db.commit()


# =========================================================
# DASHBOARD NUMBERS
# =========================================================

def catalog_stats(db: Session) -> dict:
    total = db.query(func.count(Medicine.id)).filter(
        Medicine.is_active.is_(True)
    ).scalar() or 0

    out_of_stock = db.query(func.count(Medicine.id)).filter(
        Medicine.is_active.is_(True),
        Medicine.stock <= 0
    ).scalar() or 0

    low_stock = db.query(func.count(Medicine.id)).filter(
        Medicine.is_active.is_(True),
        Medicine.stock > 0,
        Medicine.stock <= Medicine.low_stock_alert
    ).scalar() or 0

    stock_value = db.query(
        func.coalesce(func.sum(Medicine.stock * Medicine.price), 0)
    ).filter(Medicine.is_active.is_(True)).scalar() or 0

    disease_count = db.query(func.count(Disease.id)).scalar() or 0

    return {
        "medicines": int(total),
        "diseases": int(disease_count),
        "out_of_stock": int(out_of_stock),
        "low_stock": int(low_stock),
        "stock_value": money(stock_value),
    }


def low_stock_rows(db: Session, limit: int = 10) -> list[Medicine]:
    return (
        db.query(Medicine)
        .filter(Medicine.is_active.is_(True))
        .filter(Medicine.stock <= Medicine.low_stock_alert)
        .order_by(Medicine.stock.asc(), Medicine.name.asc())
        .limit(limit)
        .all()
    )
