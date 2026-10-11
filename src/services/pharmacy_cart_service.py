"""Cart for the pharmacy, stored in SQL against the logged in user.

Rules kept here (so the cart page, the API and checkout agree):

* quantity is always 1..min(stock, MAX_PER_ITEM)
* a medicine with ``requires_prescription`` can only enter the cart if the
  patient actually has a prescription line for it
* the price is copied from the catalog when the line is added; checkout
  re-reads the live price and reports the difference instead of silently
  charging a new amount
* prescription lines keep their prescription ids, so the pharmacist can see
  exactly which doctor ordered what
"""

from datetime import datetime

from sqlalchemy import func  # noqa: F401  (kept for future aggregate helpers)
from sqlalchemy.orm import Session

from src.models.doctor import Doctor
from src.models.medicine import Medicine
from src.models.pharmacy_cart import PharmacyCartItem
from src.models.prescription import Prescription
from src.models.prescription_medicine import PrescriptionMedicine
from src.models.user import User
from src.services import pharmacy_catalog_service as catalog


MAX_PER_ITEM = 20
DELIVERY_FEE = 40.00
FREE_DELIVERY_OVER = 999.00


class CartError(ValueError):
    """Raised for anything the patient can fix by changing the cart."""


# =========================================================
# PRESCRIPTION HELPERS
# =========================================================

def patient_prescription_medicines(db: Session, patient_id: int) -> list[dict]:
    """All prescription lines of one patient, newest prescription first,
    with the catalog match (and its price / stock) attached."""

    rows = (
        db.query(PrescriptionMedicine, Prescription)
        .join(Prescription, Prescription.id == PrescriptionMedicine.prescription_id)
        .filter(Prescription.patient_id == patient_id)
        .order_by(Prescription.created_at.desc(), PrescriptionMedicine.id.asc())
        .all()
    )

    out: list[dict] = []

    doctor_cache: dict[int, str | None] = {}

    for item, prescription in rows:

        medicine = catalog.match_medicine(db, pm_name := item.medicine_name)

        doctor_name = None

        if prescription.doctor_id:
            if prescription.doctor_id not in doctor_cache:
                doctor_cache[prescription.doctor_id] = (
                    db.query(Doctor.name)
                    .filter(Doctor.id == prescription.doctor_id)
                    .scalar()
                )
            doctor_name = doctor_cache[prescription.doctor_id]

        out.append({
            "id": item.id,
            "medicine_name": pm_name,
            "dosage": item.dosage,
            "frequency": item.frequency,
            "duration": item.duration,
            "instructions": item.instructions,
            "prescription_id": prescription.id,
            "prescription_created_at": prescription.created_at,
            "diagnosis": prescription.diagnosis,
            "doctor_name": doctor_name,
            "matched_id": medicine.id if medicine else None,
            "matched_name": medicine.name if medicine else None,
            "price": catalog.money(medicine.price) if medicine else None,
            "stock": int(medicine.stock or 0) if medicine else 0,
            "available": bool(medicine and medicine.is_active and (medicine.stock or 0) > 0),
            "image": catalog.medicine_image(medicine),
        })

    return out


def patient_has_valid_prescription(
    db: Session,
    patient_id: int,
    medicine: Medicine
) -> PrescriptionMedicine | None:
    """Does this patient have a doctor's line that covers this medicine?"""

    candidates = (
        db.query(PrescriptionMedicine, Prescription)
        .join(Prescription, Prescription.id == PrescriptionMedicine.prescription_id)
        .filter(Prescription.patient_id == patient_id)
        .order_by(Prescription.created_at.desc())
        .all()
    )

    wanted_name = catalog.normalize_name(medicine.name)
    wanted_generic = catalog.normalize_name(medicine.generic_name)

    for item, _prescription in candidates:
        line = catalog.normalize_name(item.medicine_name)

        if not line:
            continue

        if line == wanted_name or line == wanted_generic:
            return item

        if wanted_generic and wanted_generic.startswith(line):
            return item

        if wanted_name and wanted_name.startswith(line):
            return item

    return None


# =========================================================
# CART READ
# =========================================================

def get_items(db: Session, user_id: int) -> list[PharmacyCartItem]:
    return (
        db.query(PharmacyCartItem)
        .filter(PharmacyCartItem.user_id == user_id)
        .order_by(PharmacyCartItem.created_at.asc(), PharmacyCartItem.id.asc())
        .all()
    )


def summary(db: Session, user: User) -> dict:
    items = get_items(db, user.id)

    lines = []
    subtotal = 0.0
    problems = []
    count = 0

    for item in items:

        medicine = item.medicine

        if medicine is None:
            problems.append(
                f"one cart item is no longer in our catalog (item #{item.id})"
            )
            db.delete(item)
            db.commit()
            continue

        live_price = catalog.money(medicine.price)
        stock = int(medicine.stock or 0)
        quantity = int(item.quantity or 0)

        if not medicine.is_active:
            problems.append(f"{medicine.name} has been discontinued")

        if stock <= 0:
            problems.append(f"{medicine.name} is out of stock")

        line_total = round(live_price * quantity, 2)
        subtotal += line_total
        count += quantity

        lines.append({
            "item_id": item.id,
            "medicine_id": medicine.id,
            "name": medicine.name,
            "generic_name": medicine.generic_name,
            "form": medicine.form,
            "strength": medicine.strength,
            "pack_size": medicine.pack_size,
            "unit_price": live_price,
            "old_unit_price": catalog.money(item.unit_price),
            "price_changed": abs(live_price - catalog.money(item.unit_price)) > 0.009,
            "quantity": quantity,
            "stock": stock,
            "line_total": line_total,
            "image": catalog.medicine_image(medicine),
            "source": item.source,
            "prescription_id": item.prescription_id,
            "dosage": item.dosage,
            "frequency": item.frequency,
            "duration": item.duration,
            "available": bool(medicine.is_active and stock >= quantity),
            "requires_prescription": bool(medicine.requires_prescription),
            "max_qty": max(1, min(stock or 1, MAX_PER_ITEM)),
        })

    subtotal = round(subtotal, 2)

    return {
        "lines": lines,
        "count": count,
        "subtotal": subtotal,
        "problems": problems,
        "ready": bool(lines) and not problems,
    }


# =========================================================
# CART WRITES
# =========================================================

def add_catalog_item(
    db: Session,
    user: User,
    medicine_id: int,
    quantity: int = 1
) -> dict:

    medicine = db.get(Medicine, medicine_id)

    if medicine is None or not medicine.is_active:
        raise CartError("That medicine is not available in our pharmacy.")

    try:
        quantity = int(quantity or 1)
    except (TypeError, ValueError):
        raise CartError("Quantity must be a number.") from None

    if quantity < 1:
        raise CartError("Quantity must be at least 1.")

    if quantity > MAX_PER_ITEM:
        raise CartError(f"You can add up to {MAX_PER_ITEM} packs at a time.")

    stock = int(medicine.stock or 0)

    if stock <= 0:
        raise CartError(
            f"{medicine.name} is out of stock. Use 'Find it nearby' for the "
            "emergency option."
        )

    if quantity > stock:
        raise CartError(
            f"Only {stock} pack(s) of {medicine.name} are left."
        )

    if medicine.requires_prescription:
        allowed = patient_has_valid_prescription(db, user.id, medicine)
        if allowed is None:
            raise CartError(
                f"{medicine.name} needs a valid prescription. Ask your doctor "
                "to add it to your prescription, then buy it from the "
                "'Doctor prescribed' tab."
            )

    item = (
        db.query(PharmacyCartItem)
        .filter(
            PharmacyCartItem.user_id == user.id,
            PharmacyCartItem.medicine_id == medicine.id,
            PharmacyCartItem.source == "CATALOG",
        )
        .first()
    )

    if item is None:
        item = PharmacyCartItem(
            user_id=user.id,
            medicine_id=medicine.id,
            quantity=quantity,
            unit_price=catalog.money(medicine.price),
            source="CATALOG",
        )
        db.add(item)
    else:
        new_qty = int(item.quantity or 0) + quantity
        if new_qty > stock:
            raise CartError(
                f"Your cart would have {new_qty} pack(s) but only {stock} "
                f"are in stock for {medicine.name}."
            )
        item.quantity = new_qty
        item.unit_price = catalog.money(medicine.price)
        item.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(item)

    return {
        "item_id": item.id,
        "medicine_id": medicine.id,
        "name": medicine.name,
        "quantity": item.quantity,
        "line_total": item.line_total,
        "cart": summary(db, user),
    }


def add_prescription_item(
    db: Session,
    user: User,
    prescription_medicine_id: int,
    quantity: int = 1
) -> dict:

    pm = db.get(PrescriptionMedicine, prescription_medicine_id)

    if pm is None:
        raise CartError("That prescription line could not be found.")

    prescription = db.get(Prescription, pm.prescription_id)

    if prescription is None or prescription.patient_id != user.id:
        raise CartError("This prescription does not belong to you.")

    medicine = catalog.match_medicine(db, pm.medicine_name)

    if medicine is None or not medicine.is_active:
        raise CartError(
            f"{pm.medicine_name} is not stocked in our pharmacy yet. Use "
            "'Find it nearby' to see which shop around you has it."
        )

    stock = int(medicine.stock or 0)

    if stock <= 0:
        raise CartError(
            f"{medicine.name} is out of stock right now. 'Find it nearby' "
            "shows partner shops that have it."
        )

    try:
        quantity = max(1, min(int(quantity or 1), MAX_PER_ITEM, stock))
    except (TypeError, ValueError):
        quantity = 1

    item = (
        db.query(PharmacyCartItem)
        .filter(
            PharmacyCartItem.user_id == user.id,
            PharmacyCartItem.medicine_id == medicine.id,
            PharmacyCartItem.source == "PRESCRIPTION",
            PharmacyCartItem.prescription_medicine_id == pm.id,
        )
        .first()
    )

    if item is None:
        item = PharmacyCartItem(
            user_id=user.id,
            medicine_id=medicine.id,
            quantity=quantity,
            unit_price=catalog.money(medicine.price),
            source="PRESCRIPTION",
            prescription_id=prescription.id,
            prescription_medicine_id=pm.id,
            dosage=pm.dosage,
            frequency=pm.frequency,
            duration=pm.duration,
        )
        db.add(item)
    else:
        item.quantity = max(1, min(int(item.quantity or 0) + quantity, stock))
        item.unit_price = catalog.money(medicine.price)
        item.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(item)

    return {
        "item_id": item.id,
        "medicine_id": medicine.id,
        "name": medicine.name,
        "quantity": item.quantity,
        "line_total": item.line_total,
        "cart": summary(db, user),
    }


def set_quantity(
    db: Session,
    user: User,
    item_id: int,
    quantity: int
) -> dict:

    item = db.get(PharmacyCartItem, item_id)

    if item is None or item.user_id != user.id:
        raise CartError("That cart item is not yours.")

    if quantity <= 0:
        remove_item(db, user, item_id)
        return {"removed": True, "cart": summary(db, user)}

    if quantity > MAX_PER_ITEM:
        raise CartError(f"Maximum {MAX_PER_ITEM} packs per item.")

    medicine = item.medicine

    if medicine is None:
        raise CartError("That medicine is no longer in our catalog.")

    if quantity > int(medicine.stock or 0):
        raise CartError(
            f"Only {int(medicine.stock or 0)} pack(s) available."
        )

    item.quantity = quantity
    item.unit_price = catalog.money(medicine.price)
    item.updated_at = datetime.utcnow()

    db.commit()

    return {"removed": False, "cart": summary(db, user)}


def remove_item(db: Session, user: User, item_id: int) -> None:
    item = db.get(PharmacyCartItem, item_id)

    if item is None or item.user_id != user.id:
        raise CartError("That cart item is not yours.")

    db.delete(item)
    db.commit()


def clear(db: Session, user: User) -> None:
    (
        db.query(PharmacyCartItem)
        .filter(PharmacyCartItem.user_id == user.id)
        .delete(synchronize_session=False)
    )
    db.commit()


def delivery_fee_for(subtotal: float) -> float:
    if subtotal <= 0:
        return 0.0
    return 0.0 if subtotal >= FREE_DELIVERY_OVER else DELIVERY_FEE
