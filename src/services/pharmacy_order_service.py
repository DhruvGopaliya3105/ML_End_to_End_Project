"""Orders: checkout, payment confirmation, cancel/refund, stock movement.

Checkout is deliberately one transaction:

    read cart -> lock price+stock -> decrement stock -> write order + items
              -> clear cart -> audit row -> COMMIT

so a patient can never pay for stock that was already sold to someone else.
The stock decrement is a guarded UPDATE (``WHERE stock >= qty``); if it touches
0 rows the whole checkout aborts with a clear "only N left" message.

``stock_adjusted`` on the order is what makes cancel/refund idempotent: stock
moves back exactly once, even if a user double-clicks "Cancel" or a super user
restores an old snapshot around it.
"""

import logging
from datetime import datetime
from uuid import uuid4

from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy import update

from src.models.medicine import Medicine
from src.models.pharmacy_cart import PharmacyCartItem
from src.models.pharmacy_order import (
    PharmacyOrder,
    PharmacyOrderItem
)
from src.models.user import User
from src.services import pharmacy_audit_service as audit
from src.services import pharmacy_cart_service as cart
from src.services import pharmacy_catalog_service as catalog


logger = logging.getLogger(__name__)

STATUS_PENDING = "PENDING_PAYMENT"
STATUS_CONFIRMED = "CONFIRMED"
STATUS_CANCELLED = "CANCELLED"
STATUS_REFUNDED = "REFUNDED"

PAY_PENDING = "PENDING"
PAY_PAID = "PAID"
PAY_FAILED = "FAILED"
PAY_REFUNDED = "REFUNDED"

ORDER_STATUSES = [
    STATUS_PENDING,
    STATUS_CONFIRMED,
    STATUS_CANCELLED,
    STATUS_REFUNDED,
]

OPEN_STATUSES = (STATUS_PENDING, STATUS_CONFIRMED)


class CheckoutError(ValueError):
    pass


# =========================================================
# ORDER NUMBER
# =========================================================

def generate_order_no(db: Session) -> str:
    today = datetime.utcnow().strftime("%Y%m%d")

    prefix = f"PH-{today}-"

    used = (
        db.query(func.count(PharmacyOrder.id))
        .filter(PharmacyOrder.order_no.like(f"{prefix}%"))
        .scalar()
        or 0
    )

    candidate = f"{prefix}{int(used) + 1:04d}"

    while (
        db.query(PharmacyOrder.id)
        .filter(PharmacyOrder.order_no == candidate)
        .first()
        is not None
    ):
        used += 1
        candidate = f"{prefix}{int(used) + 1:04d}"

    return candidate


# =========================================================
# STOCK MOVEMENT
# =========================================================

def _take_stock(db: Session, medicine_id: int, quantity: int) -> None:

    result = db.execute(
        update(Medicine)
        .where(
            Medicine.id == medicine_id,
            Medicine.stock >= quantity
        )
        .values(stock=Medicine.stock - quantity)
    )

    if (result.rowcount or 0) == 0:
        raise CheckoutError(
            "Stock finished while you were checking out. Please refresh the "
            "cart and try again."
        )


def _give_stock_back(db: Session, order: PharmacyOrder) -> None:

    for item in order.items:

        if item.medicine_id is None:
            continue

        db.execute(
            update(Medicine)
            .where(Medicine.id == item.medicine_id)
            .values(stock=func.coalesce(Medicine.stock, 0) + int(item.quantity or 0))
        )


# =========================================================
# CHECKOUT
# =========================================================

def checkout(
    db: Session,
    user: User,
    *,
    payment_method: str = "CASH",
    delivery_type: str = "PICKUP",
    address: str | None = None,
    phone: str | None = None,
    notes: str | None = None,
    is_emergency: bool = False,
    request=None
) -> PharmacyOrder:

    payment_method = (payment_method or "CASH").upper()
    delivery_type = (delivery_type or "PICKUP").upper()

    if payment_method not in ("CASH", "ONLINE"):
        raise CheckoutError("Choose CASH or ONLINE as the payment method.")

    if delivery_type not in ("PICKUP", "DELIVERY"):
        raise CheckoutError("Choose counter pickup or home delivery.")

    if delivery_type == "DELIVERY":
        if not (address or "").strip():
            raise CheckoutError("A delivery address is required.")
        if not (phone or "").strip():
            raise CheckoutError("A contact number is required for delivery.")

    items = cart.get_items(db, user.id)

    if not items:
        raise CheckoutError("Your cart is empty.")

    lines = []

    for item in items:

        medicine = item.medicine

        if medicine is None or not medicine.is_active:
            raise CheckoutError(
                "One of your cart items is no longer on the shelf. Remove it "
                "and try again."
            )

        quantity = int(item.quantity or 0)

        if quantity < 1:
            raise CheckoutError(f"Bad quantity for {medicine.name}.")

        if int(medicine.stock or 0) < quantity:
            raise CheckoutError(
                f"Only {int(medicine.stock or 0)} pack(s) of {medicine.name} "
                "are left. Reduce the quantity or use 'Find it nearby'."
            )

        lines.append((item, medicine, quantity, catalog.money(medicine.price)))

    subtotal = round(sum(price * qty for _i, _m, qty, price in lines), 2)
    delivery_fee = (
        cart.delivery_fee_for(subtotal)
        if delivery_type == "DELIVERY" else 0.0
    )
    total = round(subtotal + delivery_fee, 2)

    prescription_ids = {
        item.prescription_id for item, *_rest in lines if item.prescription_id
    }

    order_type = (
        "PRESCRIPTION" if any(item.source == "PRESCRIPTION" for item, *_r in lines)
        else "CATALOG"
    )

    order = PharmacyOrder(
        order_no=generate_order_no(db),
        user_id=user.id,
        order_type=order_type,
        prescription_id=(prescription_ids.pop() if len(prescription_ids) == 1 else None),
        status=(
            STATUS_CONFIRMED if payment_method == "CASH" else STATUS_PENDING
        ),
        payment_method=payment_method,
        payment_status=PAY_PENDING,
        payment_provider=(
            "CASH_COUNTER" if payment_method == "CASH" else "SIMULATED"
        ),
        subtotal=subtotal,
        delivery_fee=delivery_fee,
        total=total,
        delivery_type=delivery_type,
        address=(address or None),
        phone=(phone or None),
        notes=(notes or None),
        is_emergency=bool(is_emergency),
        stock_adjusted=True,
        confirmed_at=(datetime.utcnow() if payment_method == "CASH" else None),
    )

    db.add(order)
    db.flush()

    for item, medicine, quantity, price in lines:

        _take_stock(db, medicine.id, quantity)

        db.add(PharmacyOrderItem(
            order_id=order.id,
            medicine_id=medicine.id,
            medicine_name=medicine.name,
            generic_name=medicine.generic_name,
            form=medicine.form,
            strength=medicine.strength,
            pack_size=medicine.pack_size,
            image_path=medicine.image_path or catalog.medicine_image(medicine),
            quantity=quantity,
            unit_price=price,
            line_total=round(price * quantity, 2),
            source=item.source,
            prescription_medicine_id=item.prescription_medicine_id,
            dosage=item.dosage,
            frequency=item.frequency,
            duration=item.duration,
        ))

    (
        db.query(PharmacyCartItem)
        .filter(PharmacyCartItem.user_id == user.id)
        .delete(synchronize_session=False)
    )

    audit.log_activity(
        db,
        action="pharmacy.order.create",
        entity_type="order",
        entity_id=order.id,
        description=(
            f"{user.name} placed order {order.order_no} ({len(lines)} item(s), "
            f"Rs {total:.2f}, {payment_method}, {delivery_type})"
        ),
        severity="WARN" if is_emergency else "INFO",
        after=catalog_snapshot_of_order(order),
        actor=audit_actor(user),
        request=request,
        rollback_available=True,
    )

    db.commit()
    db.refresh(order)

    notify_order_placed(order, user)

    return order


def audit_actor(user: User | None) -> dict:
    if user is None:
        return {"user_id": None, "name": "Anonymous", "role": "GUEST"}
    return {
        "user_id": user.id,
        "name": user.name,
        "role": (user.role or "PATIENT").upper(),
    }


def catalog_snapshot_of_order(order: PharmacyOrder) -> dict:
    return {
        "order_no": order.order_no,
        "status": order.status,
        "payment_method": order.payment_method,
        "payment_status": order.payment_status,
        "subtotal": catalog.money(order.subtotal),
        "delivery_fee": catalog.money(order.delivery_fee),
        "total": catalog.money(order.total),
        "items": [
            {
                "medicine_name": item.medicine_name,
                "quantity": item.quantity,
                "unit_price": catalog.money(item.unit_price),
            }
            for item in order.items
        ],
    }


# =========================================================
# PAYMENT
# =========================================================

def confirm_online_payment(
    db: Session,
    order: PharmacyOrder,
    *,
    provider: str = "SIMULATED",
    reference: str | None = None,
    request=None,
    actor: dict | None = None
) -> PharmacyOrder:

    if order.payment_status == PAY_PAID:
        return order

    if order.status not in (STATUS_PENDING, STATUS_CONFIRMED):
        raise CheckoutError("This order can no longer be paid for.")

    before = catalog_snapshot_of_order(order)

    order.payment_status = PAY_PAID
    order.status = STATUS_CONFIRMED
    order.payment_provider = (provider or "SIMULATED").upper()[:30]
    order.transaction_id = reference or f"SIM{uuid4().hex[:12].upper()}"
    order.payment_reference = order.transaction_id
    order.confirmed_at = datetime.utcnow()
    order.updated_at = datetime.utcnow()

    audit.log_activity(
        db,
        action="pharmacy.payment.confirm",
        entity_type="order",
        entity_id=order.id,
        description=(
            f"Payment of Rs {catalog.money(order.total):.2f} confirmed for "
            f"{order.order_no} via {order.payment_provider}"
        ),
        before=before,
        after=catalog_snapshot_of_order(order),
        actor=actor,
        request=request,
        rollback_available=True,
    )

    db.commit()
    db.refresh(order)

    return order


def fail_online_payment(
    db: Session,
    order: PharmacyOrder,
    *,
    reason: str = "Payment not completed",
    request=None,
    actor: dict | None = None
) -> PharmacyOrder:

    order.payment_status = PAY_FAILED
    order.notes = (f"{order.notes + ' | ' if order.notes else ''}{reason}")[:500]
    order.updated_at = datetime.utcnow()

    audit.log_activity(
        db,
        action="pharmacy.payment.failed",
        entity_type="order",
        entity_id=order.id,
        description=f"{order.order_no}: {reason}",
        severity="WARN",
        actor=actor,
        request=request,
    )

    db.commit()
    db.refresh(order)

    return order


def mark_cash_paid(
    db: Session,
    order: PharmacyOrder,
    *,
    request=None,
    actor: dict | None = None
) -> PharmacyOrder:

    if order.payment_status == PAY_PAID:
        return order

    order.payment_status = PAY_PAID
    order.payment_provider = "CASH_COUNTER"
    order.transaction_id = f"CASH{uuid4().hex[:8].upper()}"
    order.updated_at = datetime.utcnow()

    audit.log_activity(
        db,
        action="pharmacy.payment.cash_received",
        entity_type="order",
        entity_id=order.id,
        description=f"Cash Rs {catalog.money(order.total):.2f} received for {order.order_no}",
        actor=actor,
        request=request,
        rollback_available=True,
    )

    db.commit()
    db.refresh(order)

    return order


# =========================================================
# CANCEL / REFUND / HANDOVER
# =========================================================

def _restore_stock_once(db: Session, order: PharmacyOrder) -> bool:
    if not order.stock_adjusted:
        return False

    _give_stock_back(db, order)
    order.stock_adjusted = False
    return True


def cancel_order(
    db: Session,
    order: PharmacyOrder,
    *,
    reason: str | None = None,
    request=None,
    actor: dict | None = None,
    allow_paid: bool = False
) -> PharmacyOrder:

    if order.status in (STATUS_CANCELLED, STATUS_REFUNDED):
        raise CheckoutError("This order is already closed.")

    if order.payment_status == PAY_PAID and not allow_paid:
        raise CheckoutError(
            "Payment was already made, so this order has to be refunded "
            "instead of cancelled (super user / admin action)."
        )

    before = catalog_snapshot_of_order(order)

    restocked = _restore_stock_once(db, order)

    if order.payment_status == PAY_PAID and allow_paid:
        order.status = STATUS_REFUNDED
        order.payment_status = PAY_REFUNDED
    else:
        order.status = STATUS_CANCELLED

    order.cancelled_at = datetime.utcnow()
    order.cancel_reason = (reason or "Cancelled by user")[:500]
    order.updated_at = datetime.utcnow()

    audit.log_activity(
        db,
        action="pharmacy.order.refund" if order.status == STATUS_REFUNDED else "pharmacy.order.cancel",
        entity_type="order",
        entity_id=order.id,
        description=(
            f"{order.order_no} {order.status}"
            + (f" - {reason}" if reason else "")
            + (" (stock given back)" if restocked else "")
        ),
        severity="WARN",
        before=before,
        after=catalog_snapshot_of_order(order),
        actor=actor,
        request=request,
        rollback_available=True,
    )

    db.commit()
    db.refresh(order)

    return order


def refund_order(
    db: Session,
    order: PharmacyOrder,
    *,
    reason: str | None = None,
    request=None,
    actor: dict | None = None
) -> PharmacyOrder:

    if order.status == STATUS_REFUNDED:
        raise CheckoutError("This order was already refunded.")

    if order.payment_status != PAY_PAID:
        # Nothing was taken, so this behaves like a cancel.
        return cancel_order(
            db,
            order,
            reason=reason,
            request=request,
            actor=actor,
            allow_paid=True
        )

    before = catalog_snapshot_of_order(order)

    _restore_stock_once(db, order)

    order.status = STATUS_REFUNDED
    order.payment_status = PAY_REFUNDED
    order.cancelled_at = datetime.utcnow()
    order.cancel_reason = (reason or "Refunded by pharmacy")[:500]
    order.updated_at = datetime.utcnow()

    audit.log_activity(
        db,
        action="pharmacy.order.refund",
        entity_type="order",
        entity_id=order.id,
        description=f"Refund issued for {order.order_no} (Rs {catalog.money(order.total):.2f})",
        severity="CRITICAL",
        before=before,
        after=catalog_snapshot_of_order(order),
        actor=actor,
        request=request,
        rollback_available=True,
    )

    db.commit()
    db.refresh(order)

    return order


def mark_handed_over(
    db: Session,
    order: PharmacyOrder,
    *,
    request=None,
    actor: dict | None = None
) -> PharmacyOrder:

    if order.status != STATUS_CONFIRMED:
        raise CheckoutError("Only a confirmed order can be handed over.")

    order.notes = (
        f"{order.notes + ' | ' if order.notes else ''}Handed over "
        f"{datetime.utcnow():%Y-%m-%d %H:%M}"
    )[:500]

    order.handed_over_at = datetime.utcnow()
    order.updated_at = datetime.utcnow()

    audit.log_activity(
        db,
        action="pharmacy.order.handed_over",
        entity_type="order",
        entity_id=order.id,
        description=f"{order.order_no} handed over to {order.user.name if order.user else 'patient'}",
        actor=actor,
        request=request,
    )

    db.commit()
    db.refresh(order)

    return order


# =========================================================
# READS
# =========================================================

def get_order(db: Session, order_id: int) -> PharmacyOrder | None:
    return db.get(PharmacyOrder, order_id)


def get_order_by_no(db: Session, order_no: str) -> PharmacyOrder | None:
    return (
        db.query(PharmacyOrder)
        .filter(func.upper(PharmacyOrder.order_no) == order_no.upper())
        .first()
    )


def user_orders(db: Session, user_id: int, *, limit: int = 50) -> list[PharmacyOrder]:
    return (
        db.query(PharmacyOrder)
        .filter(PharmacyOrder.user_id == user_id)
        .order_by(PharmacyOrder.created_at.desc(), PharmacyOrder.id.desc())
        .limit(limit)
        .all()
    )


def staff_query(
    db: Session,
    *,
    status: str | None = None,
    payment: str | None = None,
    search: str | None = None,
    urgent_only: bool = False
):
    query = db.query(PharmacyOrder)

    if status:
        query = query.filter(PharmacyOrder.status == status.upper())

    if payment:
        query = query.filter(PharmacyOrder.payment_status == payment.upper())

    if urgent_only:
        query = query.filter(PharmacyOrder.is_emergency.is_(True))

    if search:
        like = f"%{search}%"
        query = query.filter(
            func.upper(PharmacyOrder.order_no).like(like.upper())
        )

    return query


def list_orders(
    db: Session,
    *,
    limit: int = 50,
    offset: int = 0,
    **filters
) -> tuple[list[PharmacyOrder], int]:

    query = staff_query(db, **filters)

    total = query.count()

    rows = (
        query
        .order_by(PharmacyOrder.created_at.desc(), PharmacyOrder.id.desc())
        .offset(max(0, offset))
        .limit(min(max(1, limit), 200))
        .all()
    )

    return rows, total


def order_to_dict(db: Session, order: PharmacyOrder, *, detailed: bool = False) -> dict:

    data = {
        "id": order.id,
        "order_no": order.order_no,
        "status": order.status,
        "order_type": order.order_type,
        "payment_method": order.payment_method,
        "payment_status": order.payment_status,
        "payment_provider": order.payment_provider,
        "transaction_id": order.transaction_id,
        "subtotal": catalog.money(order.subtotal),
        "delivery_fee": catalog.money(order.delivery_fee),
        "total": catalog.money(order.total),
        "delivery_type": order.delivery_type,
        "address": order.address,
        "phone": order.phone,
        "notes": order.notes,
        "is_emergency": bool(order.is_emergency),
        "item_count": sum(int(item.quantity or 0) for item in order.items),
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "created_at_display": (
            order.created_at.strftime("%d %b %Y, %I:%M %p")
            if order.created_at else ""
        ),
        "confirmed_at": order.confirmed_at.isoformat() if order.confirmed_at else None,
        "cancel_reason": order.cancel_reason,
        "items": [
            {
                "id": item.id,
                "name": item.medicine_name,
                "generic_name": item.generic_name,
                "form": item.form,
                "strength": item.strength,
                "pack_size": item.pack_size,
                "quantity": item.quantity,
                "unit_price": catalog.money(item.unit_price),
                "line_total": catalog.money(item.line_total),
                "image": (
                    item.image_path
                    if item.image_path and item.image_path.startswith("/")
                    else catalog.FALLBACK_IMAGES.get(
                        (item.form or "TABLET").upper(),
                        "/static/images/pharmacy/tablet.svg"
                    )
                ),
                "source": item.source,
                "dosage": item.dosage,
                "frequency": item.frequency,
                "duration": item.duration,
            }
            for item in order.items
        ],
    }

    if detailed:
        data["patient"] = {
            "id": order.user.id if order.user else None,
            "name": order.user.name if order.user else "Deleted user",
            "email": order.user.email if order.user else None,
            "phone": order.user.phone if order.user else None,
        }

    return data


def status_badge(order: PharmacyOrder) -> dict:
    return {
        STATUS_CONFIRMED: {"label": "Confirmed", "tone": "success"},
        STATUS_PENDING: {"label": "Payment pending", "tone": "warn"},
        STATUS_CANCELLED: {"label": "Cancelled", "tone": "muted"},
        STATUS_REFUNDED: {"label": "Refunded", "tone": "danger"},
    }.get(order.status, {"label": order.status, "tone": "muted"})


def order_totals(db: Session) -> dict:
    """Counters for the admin queue header."""

    def count(*conditions):
        query = db.query(func.count(PharmacyOrder.id))
        for condition in conditions:
            query = query.filter(condition)
        return int(query.scalar() or 0)

    revenue = db.query(
        func.coalesce(func.sum(PharmacyOrder.total), 0)
    ).filter(
        PharmacyOrder.payment_status == PAY_PAID
    ).scalar() or 0

    due = db.query(
        func.coalesce(func.sum(PharmacyOrder.total), 0)
    ).filter(
        PharmacyOrder.status == STATUS_CONFIRMED,
        PharmacyOrder.payment_status == PAY_PENDING
    ).scalar() or 0

    return {
        "total_orders": count(),
        "pending_payment": count(PharmacyOrder.status == STATUS_PENDING),
        "confirmed": count(PharmacyOrder.status == STATUS_CONFIRMED),
        "cancelled": count(PharmacyOrder.status.in_([STATUS_CANCELLED, STATUS_REFUNDED])),
        "emergency": count(PharmacyOrder.is_emergency.is_(True)),
        "revenue": catalog.money(revenue),
        "cash_due": catalog.money(due),
    }


def notify_order_placed(order: PharmacyOrder, user: User) -> None:
    """Re-use the project's own notification inbox."""

    try:
        from src.services.notification_service import create_notification

        create_notification(
            db=_db_of(order),
            user_id=user.id,
            title=f"Order {order.order_no} placed",
            message=(
                f"{len(order.items)} item(s) for Rs {catalog.money(order.total):.2f}. "
                + (
                    "Pay at the pharmacy counter."
                    if order.payment_method == "CASH"
                    else "Complete the payment to confirm."
                )
            ),
            notification_type="PHARMACY",
        )
    except Exception:  # noqa: BLE001 - a failed inbox note must not lose an order
        logger.exception("pharmacy notification could not be written")


def _db_of(obj) -> Session:
    from sqlalchemy import inspect as sa_inspect
    return sa_inspect(obj).session
