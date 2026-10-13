"""Pharmacy - patient facing pages and JSON API.

Mounted in ``main.py`` as ``app.include_router(pharmacy_router)``.

Pages
-----
/pharmacy                     catalog, filter by disease / search / sort
/pharmacy/cart                cart + payment method (cash / online) + place order
/pharmacy/prescriptions       the tablets a doctor prescribed, with price + buy
/pharmacy/orders              my orders with CONFIRMED / pending / cancelled
/pharmacy/order/{no}          one order: status, items, invoice, pay / cancel
/pharmacy/nearby              emergency "who has it near me" (SQL + Google)

API (used by the buttons on those pages, all JSON)
---------------------------------------------------
/pharmacy/api/medicines       live search
/pharmacy/api/cart/*          add / add-prescription / quantity / remove / clear
/pharmacy/api/buy-now         skip the cart, order one item straight away
/pharmacy/api/checkout        place the order from the cart
/pharmacy/api/order/{id}/pay  confirm online payment (Razorpay signature or
                              simulated, see pharmacy_payment_service)
/pharmacy/api/order/{id}/cancel
/pharmacy/api/nearby          partner shops from SQL + Google Places

Every route checks the RBAC permissions from ``src/security/rbac.py``, so a
role that was switched off in the admin screen gets 403 (API) or is bounced to
the dashboard (pages) instead of silently working.
"""

import logging
import math

from fastapi import (
    APIRouter,
    Depends,
    Form,
    Query,
    Request
)

from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    RedirectResponse
)

from sqlalchemy.orm import Session

from src.database.connection import get_db
from src.models.medicine import Medicine
from src.models.user import User
from src.services import pharmacy_cart_service as cart_service
from src.services import pharmacy_catalog_service as catalog
from src.services import pharmacy_audit_service as audit
from src.services import pharmacy_nearby_service as nearby
from src.services import pharmacy_order_service as orders
from src.services import pharmacy_payment_service as payments
from src.security import rbac


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/pharmacy",
    tags=["Pharmacy"]
)


# =========================================================
# SMALL HELPERS
# =========================================================

def _templates(request: Request):
    return request.app.state.templates


def user_dict(user: User | None) -> dict:
    """Same keys the existing templates expect (user.user_name etc.)."""

    if user is None:
        return {
            "user_name": "Guest",
            "user_email": "",
            "user_role": "PATIENT",
            "id": None,
        }

    return {
        "user_name": user.name,
        "user_email": user.email,
        "user_role": (user.role or "PATIENT").upper(),
        "id": user.id,
        "phone": user.phone,
    }


def base_context(
    request: Request,
    db: Session,
    user: User | None,
    **extra
) -> dict:

    cart_summary = None

    if user is not None:
        try:
            cart_summary = cart_service.summary(db, user)
        except Exception:  # noqa: BLE001 - a bad cart must not break the page
            logger.exception("cart summary failed")
            db.rollback()
            cart_summary = {"count": 0, "lines": [], "subtotal": 0.0}

    context = {
        "user": user_dict(user),
        "db": db,
        "cart_count": (cart_summary or {}).get("count", 0),
        "cart_subtotal": (cart_summary or {}).get("subtotal", 0.0),
        "can": lambda permission: rbac.has_permission(db, user, permission),
        "role_label": rbac.ROLE_LABELS.get(
            rbac.user_role(user), rbac.user_role(user)
        ),
        "is_superuser": rbac.is_superuser(user),
        "active_nav": "pharmacy",
        "inr": payments.format_inr,
        "gateway": payments.gateway_config(),
    }

    context.update(extra)

    return context


def error_response(message: str, status: int = 400, **extra) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"success": False, "message": message, **extra}
    )


def ok_response(**payload) -> JSONResponse:
    return JSONResponse(content={"success": True, **payload})


def parse_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# =========================================================
# PHARMACY HOME / CATALOG
# =========================================================

@router.get(
    "",
    response_class=HTMLResponse
)
@router.get(
    "/",
    response_class=HTMLResponse,
    include_in_schema=False
)
def pharmacy_page(
    request: Request,
    disease: str | None = Query(default=None),
    q: str | None = Query(default=None),
    form: str | None = Query(default=None),
    sort: str = Query(default="popular"),
    available: bool = Query(default=False),
    rx: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=24, ge=6, le=96),
    db: Session = Depends(get_db)
):

    user, redirect = rbac.guard_page(
        request,
        db,
        rbac.PHARMACY_VIEW,
        login_required=False
    )

    if redirect is not None:
        return redirect

    filters = {
        "disease_slug": disease,
        "search": q,
        "form": form,
        "only_available": available,
        "requires_prescription": rx,
    }

    try:
        limit = min(per_page, 96)
        offset = (max(1, page) - 1) * limit

        medicines, total = catalog.list_medicines(
            db,
            sort=sort,
            limit=limit,
            offset=offset,
            **filters
        )
    except Exception:  # noqa: BLE001 - never show a blank page on a query bug
        logger.exception("pharmacy catalog query failed")
        db.rollback()
        medicines, total = [], 0

    cards = [
        catalog.medicine_to_dict(db, medicine)
        for medicine in medicines
    ]

    # One query per card is fine at demo size, but batching keeps it cheap
    # when the catalog grows to a few thousand rows.
    for card in cards:
        card["stock_label"] = (
            "In stock" if card["stock"] > card["low_stock_alert"]
            else ("Low stock" if card["stock"] > 0 else "Out of stock")
        )

    diseases = catalog.list_diseases(db)

    context = base_context(
        request,
        db,
        user,
        medicines=cards,
        diseases=diseases,
        total=total,
        page=page,
        per_page=limit,
        pages=max(1, math.ceil(total / limit)) if total else 1,
        active_disease=disease or "",
        search=q or "",
        active_form=form or "",
        active_sort=sort,
        only_available=available,
        rx_filter=rx or "",
        forms=["TABLET", "CAPSULE", "SYRUP", "DROPS", "OINTMENT", "INJECTION", "POWDER"],
        stats=catalog.catalog_stats(db),
    )

    return _templates(request).TemplateResponse(
        request,
        "pharmacy.html",
        context
    )


@router.get("/api/medicines")
def api_medicines(
    request: Request,
    q: str | None = Query(default=None),
    disease: str | None = Query(default=None),
    limit: int = Query(default=12, ge=1, le=60),
    db: Session = Depends(get_db)
):

    # Browsing the shelf is public (same rule as the /pharmacy page); a
    # logged in user whose role lost pharmacy.view is still refused.
    user = rbac.get_session_user(request, db)

    if user is not None and not rbac.has_permission(db, user, rbac.PHARMACY_VIEW):
        return error_response("Not allowed.", 403)

    medicines, _total = catalog.list_medicines(
        db,
        search=q,
        disease_slug=disease,
        limit=limit,
        sort="popular"
    )

    return ok_response(
        results=[
            catalog.medicine_to_dict(db, medicine, with_diseases=False)
            for medicine in medicines
        ]
    )


# =========================================================
# CART
# =========================================================

@router.get("/cart")
def cart_page(
    request: Request,
    db: Session = Depends(get_db)
):

    user, redirect = rbac.guard_page(request, db, rbac.PHARMACY_VIEW)

    if redirect is not None:
        return redirect

    summary = cart_service.summary(db, user)

    context = base_context(
        request,
        db,
        user,
        cart=summary,
        subtotal=summary["subtotal"],
        delivery_fee=cart_service.delivery_fee_for(summary["subtotal"]),
        total=round(
            summary["subtotal"] + cart_service.delivery_fee_for(summary["subtotal"]),
            2
        ),
        max_per_item=cart_service.MAX_PER_ITEM,
    )

    return _templates(request).TemplateResponse(
        request,
        "pharmacy_cart.html",
        context
    )


@router.post("/api/cart/add")
def api_cart_add(
    request: Request,
    medicine_id: int = Form(...),
    quantity: int = Form(default=1),
    db: Session = Depends(get_db)
):

    user, response = _cart_actor(request, db)

    if response is not None:
        return response

    try:
        result = cart_service.add_catalog_item(db, user, medicine_id, quantity)
    except cart_service.CartError as error:
        return error_response(str(error), 409)
    except Exception:  # noqa: BLE001
        logger.exception("cart add failed")
        db.rollback()
        return error_response("Could not update the cart. Try again.")

    audit.log_activity(
        db,
        action="pharmacy.cart.add",
        entity_type="cart",
        entity_id=result["item_id"],
        description=f"Added {result['name']} x{result['quantity']} to cart",
        actor=orders.audit_actor(user),
        request=request,
        commit=True
    )

    return ok_response(**result)


@router.post("/api/cart/add-prescription")
def api_cart_add_prescription(
    request: Request,
    prescription_medicine_id: int = Form(...),
    quantity: int = Form(default=1),
    db: Session = Depends(get_db)
):

    user, response = _cart_actor(request, db)

    if response is not None:
        return response

    try:
        result = cart_service.add_prescription_item(
            db,
            user,
            prescription_medicine_id,
            quantity
        )
    except cart_service.CartError as error:
        return error_response(str(error), 409)
    except Exception:  # noqa: BLE001
        logger.exception("prescription cart add failed")
        db.rollback()
        return error_response("Could not add that prescription item.")

    audit.log_activity(
        db,
        action="pharmacy.cart.add_prescription",
        entity_type="cart",
        entity_id=result["item_id"],
        description=f"Added prescribed {result['name']} x{result['quantity']}",
        actor=orders.audit_actor(user),
        request=request,
        commit=True
    )

    return ok_response(**result)


def _cart_actor(request: Request, db: Session):
    """Cart writes need a login *and* the cart permission."""

    user = rbac.get_session_user(request, db)

    if user is None:
        return None, error_response("Please login first.", 401, login_url="/login")

    if not rbac.has_permission(db, user, rbac.PHARMACY_CART_MANAGE):
        return None, error_response(
            "Your role is not allowed to change a cart.", 403
        )

    return user, None


@router.post("/api/cart/quantity")
def api_cart_quantity(
    request: Request,
    item_id: int = Form(...),
    quantity: int = Form(...),
    db: Session = Depends(get_db)
):

    user, response = _cart_actor(request, db)

    if response is not None:
        return response

    try:
        result = cart_service.set_quantity(db, user, item_id, quantity)
    except cart_service.CartError as error:
        return error_response(str(error), 409)

    return ok_response(**result)


@router.post("/api/cart/remove")
def api_cart_remove(
    request: Request,
    item_id: int = Form(...),
    db: Session = Depends(get_db)
):

    user, response = _cart_actor(request, db)

    if response is not None:
        return response

    try:
        cart_service.remove_item(db, user, item_id)
    except cart_service.CartError as error:
        return error_response(str(error), 404)

    audit.log_activity(
        db,
        action="pharmacy.cart.remove",
        entity_type="cart",
        entity_id=item_id,
        description="Removed a cart item",
        actor=orders.audit_actor(user),
        request=request,
        commit=True
    )

    return ok_response(cart=cart_service.summary(db, user))


@router.post("/api/cart/clear")
def api_cart_clear(
    request: Request,
    db: Session = Depends(get_db)
):

    user, response = _cart_actor(request, db)

    if response is not None:
        return response

    cart_service.clear(db, user)

    audit.log_activity(
        db,
        action="pharmacy.cart.clear",
        entity_type="cart",
        entity_id=user.id,
        description="Cart emptied",
        actor=orders.audit_actor(user),
        request=request,
        commit=True
    )

    return ok_response(cart=cart_service.summary(db, user))


@router.get("/api/cart")
def api_cart_read(
    request: Request,
    db: Session = Depends(get_db)
):

    user = rbac.get_session_user(request, db)

    if user is None:
        return ok_response(cart={"lines": [], "count": 0, "subtotal": 0.0})

    return ok_response(cart=cart_service.summary(db, user))


# =========================================================
# CHECKOUT
# =========================================================

@router.post("/checkout")
def checkout_form(
    request: Request,
    payment_method: str = Form(default="CASH"),
    delivery_type: str = Form(default="PICKUP"),
    address: str | None = Form(default=None),
    phone: str | None = Form(default=None),
    notes: str | None = Form(default=None),
    emergency: str | None = Form(default=None),
    db: Session = Depends(get_db)
):
    """Progressive-enhancement path: plain form submit, no JavaScript."""

    user, redirect = rbac.guard_page(request, db, rbac.PHARMACY_ORDER_OWN)

    if redirect is not None:
        return redirect

    try:
        order = orders.checkout(
            db,
            user,
            payment_method=payment_method,
            delivery_type=delivery_type,
            address=address,
            phone=phone or user.phone,
            notes=notes,
            is_emergency=bool(emergency),
            request=request
        )
    except orders.CheckoutError as error:
        return _templates(request).TemplateResponse(
            request,
            "pharmacy_cart.html",
            base_context(
                request, db, user,
                cart=cart_service.summary(db, user),
                error=str(error),
                subtotal=0.0,
                delivery_fee=0.0,
                total=0.0,
                max_per_item=cart_service.MAX_PER_ITEM,
            ),
            status_code=409
        )

    return RedirectResponse(
        url=f"/pharmacy/order/{order.order_no}?placed=1",
        status_code=303
    )


@router.post("/api/checkout")
def checkout_api(
    request: Request,
    payment_method: str = Form(default="CASH"),
    delivery_type: str = Form(default="PICKUP"),
    address: str | None = Form(default=None),
    phone: str | None = Form(default=None),
    notes: str | None = Form(default=None),
    emergency: str | None = Form(default=None),
    db: Session = Depends(get_db)
):
    """Same checkout as the plain form above, but JSON for the cart buttons.

    Both paths call ``orders.checkout`` - one implementation, one set of
    rules, so the two can never drift apart.
    """

    user = rbac.get_session_user(request, db)

    if user is None:
        return error_response("Please login first.", 401, login_url="/login")

    if not rbac.has_permission(db, user, rbac.PHARMACY_ORDER_OWN):
        return error_response("Your role cannot place orders.", 403)

    form = {
        "payment_method": payment_method,
        "delivery_type": delivery_type,
        "address": address,
        "phone": phone,
        "notes": notes,
        "emergency": emergency,
    }

    try:
        order = orders.checkout(
            db,
            user,
            payment_method=form.get("payment_method") or "CASH",
            delivery_type=form.get("delivery_type") or "PICKUP",
            address=form.get("address"),
            phone=form.get("phone") or user.phone,
            notes=form.get("notes"),
            is_emergency=bool(form.get("emergency")),
            request=request
        )
    except orders.CheckoutError as error:
        return error_response(str(error), 409)
    except Exception:  # noqa: BLE001
        logger.exception("checkout failed")
        db.rollback()
        return error_response("Checkout failed. Nothing was charged.")

    return ok_response(
        order_no=order.order_no,
        order_id=order.id,
        status=order.status,
        payment_status=order.payment_status,
        total=catalog.money(order.total),
        redirect=f"/pharmacy/order/{order.order_no}?placed=1"
    )


@router.post("/api/buy-now")
def buy_now(
    request: Request,
    medicine_id: int = Form(...),
    quantity: int = Form(default=1),
    payment_method: str = Form(default="CASH"),
    db: Session = Depends(get_db)
):
    """'Buy now' on a card: puts the single item in the cart, then checks out.

    Using the cart as the intermediate step means the prescription rule, the
    stock guard and the audit trail are exactly the same as a normal checkout
    - there is no second code path to keep in sync.
    """

    user, response = _cart_actor(request, db)

    if response is not None:
        return response

    try:
        cart_service.add_catalog_item(db, user, medicine_id, quantity)
        order = orders.checkout(
            db,
            user,
            payment_method=payment_method,
            delivery_type="PICKUP",
            phone=user.phone,
            request=request
        )
    except (cart_service.CartError, orders.CheckoutError) as error:
        return error_response(str(error), 409)
    except Exception:  # noqa: BLE001
        logger.exception("buy now failed")
        db.rollback()
        return error_response("Could not place that order.")

    return ok_response(
        order_no=order.order_no,
        redirect=f"/pharmacy/order/{order.order_no}?placed=1"
    )


# =========================================================
# DOCTOR PRESCRIBED TAB
# =========================================================

@router.get("/prescriptions")
def prescription_orders_page(
    request: Request,
    db: Session = Depends(get_db)
):

    user, redirect = rbac.guard_page(request, db, rbac.PHARMACY_PRESCRIPTION_BUY)

    if redirect is not None:
        return redirect

    lines = cart_service.patient_prescription_medicines(db, user.id)

    cart_lines = {
        line["item_id"]: line for line in
        cart_service.summary(db, user)["lines"]
    }

    for line in lines:
        line["in_cart"] = line["id"] in {
            value["prescription_medicine_id"]
            for value in cart_lines.values()
            if value.get("prescription_medicine_id")
        }

    grouped: dict[int, dict] = {}

    for line in lines:
        key = line["prescription_id"]
        grouped.setdefault(key, {
            "prescription_id": key,
            "created_at": line["prescription_created_at"],
            "diagnosis": line["diagnosis"],
            "doctor_name": line["doctor_name"],
            "items": [],
        })["items"].append(line)

    context = base_context(
        request,
        db,
        user,
        prescriptions=sorted(
            grouped.values(),
            key=lambda row: row["created_at"] or 0,
            reverse=True
        ),
        line_count=len(lines),
    )

    return _templates(request).TemplateResponse(
        request,
        "pharmacy_prescription.html",
        context
    )


@router.post("/api/prescriptions/add-all")
def add_all_prescription_items(
    request: Request,
    prescription_id: int = Form(...),
    db: Session = Depends(get_db)
):

    user = rbac.get_session_user(request, db)

    if user is None:
        return error_response("Please login first.", 401)

    if not rbac.has_permission(db, user, rbac.PHARMACY_PRESCRIPTION_BUY):
        return error_response("Not allowed.", 403)

    added = []
    skipped = []

    for line in cart_service.patient_prescription_medicines(db, user.id):

        if line["prescription_id"] != prescription_id:
            continue

        if not line["available"]:
            skipped.append({
                "name": line["medicine_name"],
                "reason": (
                    "not stocked here" if line["matched_id"] is None
                    else "out of stock"
                ),
                "matched_id": line["matched_id"],
            })
            continue

        try:
            cart_service.add_prescription_item(db, user, line["id"], 1)
            added.append(line["medicine_name"])
        except cart_service.CartError as error:
            skipped.append({"name": line["medicine_name"], "reason": str(error)})

    return ok_response(
        added=added,
        skipped=skipped,
        cart=cart_service.summary(db, user)
    )


# =========================================================
# ORDERS
# =========================================================

@router.get("/orders")
def my_orders(
    request: Request,
    db: Session = Depends(get_db)
):

    user, redirect = rbac.guard_page(request, db, rbac.PHARMACY_VIEW)

    if redirect is not None:
        return redirect

    rows = orders.user_orders(db, user.id)

    context = base_context(
        request,
        db,
        user,
        orders=[
            {
                **orders.order_to_dict(db, order),
                "badge": orders.status_badge(order),
            }
            for order in rows
        ],
    )

    return _templates(request).TemplateResponse(
        request,
        "pharmacy_orders.html",
        context
    )


def _find_order(db: Session, order_ref: str):
    """Order id or the printed order number, both work in URLs."""

    value = (order_ref or "").strip()

    if value.isdigit():
        order = orders.get_order(db, int(value))
        if order is not None:
            return order

    return orders.get_order_by_no(db, value)


@router.get(
    "/order/{order_ref}",
    response_class=HTMLResponse
)
def order_page(
    request: Request,
    order_ref: str,
    placed: int = Query(default=0),
    db: Session = Depends(get_db)
):

    user, redirect = rbac.guard_page(request, db, rbac.PHARMACY_VIEW)

    if redirect is not None:
        return redirect

    order = _find_order(db, order_ref)

    if order is None:
        return _templates(request).TemplateResponse(
            request,
            "pharmacy_order.html",
            base_context(request, db, user, missing=True, order=None),
            status_code=404
        )

    own_order = order.user_id == user.id
    staff = rbac.has_permission(db, user, rbac.PHARMACY_ORDER_READ_ALL)

    if not own_order and not staff:
        return RedirectResponse(url="/pharmacy/orders", status_code=303)

    payload = orders.order_to_dict(db, order, detailed=staff)

    context = base_context(
        request,
        db,
        user,
        order=payload,
        badge=orders.status_badge(order),
        placed=bool(placed),
        own=own_order,
        staff=staff,
        can_cancel=(
            own_order
            and order.status == orders.STATUS_PENDING
            and rbac.has_permission(db, user, rbac.PHARMACY_ORDER_CANCEL_OWN)
        ),
        can_pay=(
            own_order
            and order.payment_status != orders.PAY_PAID
            and order.status in (orders.STATUS_PENDING, orders.STATUS_CONFIRMED)
        ),
        can_mark_cash=staff and rbac.has_permission(db, user, rbac.PHARMACY_ORDER_FULFIL),
        can_hand_over=(
            staff
            and rbac.has_permission(db, user, rbac.PHARMACY_ORDER_FULFIL)
            and order.status == orders.STATUS_CONFIRMED
        ),
        can_refund=staff and rbac.has_permission(db, user, rbac.PHARMACY_ORDER_REFUND),
        provider_label=payments.payment_provider_label(order),
        payment_note=payments.payment_note(),
    )

    return _templates(request).TemplateResponse(
        request,
        "pharmacy_order.html",
        context
    )


@router.get("/order/{order_ref}/receipt", response_class=HTMLResponse)
def order_receipt(
    request: Request,
    order_ref: str,
    db: Session = Depends(get_db)
):

    user, redirect = rbac.guard_page(request, db, rbac.PHARMACY_VIEW)

    if redirect is not None:
        return redirect

    order = _find_order(db, order_ref)

    if order is None:
        return error_response("Order not found.", 404)

    if order.user_id != user.id and not rbac.has_permission(
        db, user, rbac.PHARMACY_ORDER_READ_ALL
    ):
        return error_response("Not your order.", 403)

    return _templates(request).TemplateResponse(
        request,
        "pharmacy_receipt.html",
        base_context(
            request,
            db,
            user,
            order=orders.order_to_dict(db, order, detailed=True),
            badge=orders.status_badge(order),
            printed_on=datetime_now(),
        )
    )


def datetime_now() -> str:
    from datetime import datetime
    return datetime.utcnow().strftime("%d %b %Y, %H:%M UTC")


@router.get("/api/orders/{order_id}")
def api_order(
    request: Request,
    order_id: int,
    db: Session = Depends(get_db)
):

    user = rbac.get_session_user(request, db)

    order = orders.get_order(db, order_id)

    if order is None:
        return error_response("Order not found.", 404)

    if order.user_id != (user.id if user else None) and not rbac.has_permission(
        db, user, rbac.PHARMACY_ORDER_READ_ALL
    ):
        return error_response("Not your order.", 403)

    return ok_response(order=orders.order_to_dict(db, order, detailed=True))


# =========================================================
# PAYMENT / CANCELLATION
# =========================================================

@router.post("/api/order/{order_id}/pay")
def pay_order(
    request: Request,
    order_id: int,
    razorpay_order_id: str | None = Form(default=None),
    razorpay_payment_id: str | None = Form(default=None),
    razorpay_signature: str | None = Form(default=None),
    db: Session = Depends(get_db)
):
    """Confirm an online payment.

    With RAZORPAY_KEY_ID + RAZORPAY_KEY_SECRET in .env the three Razorpay
    fields are mandatory and the HMAC-SHA256 signature is verified on the
    server. Without them this is the simulated UPI flow (same idea the
    appointment page already uses), so the button works on a demo machine.
    """

    user = rbac.get_session_user(request, db)

    if user is None:
        return error_response("Please login first.", 401)

    order = orders.get_order(db, order_id)

    if order is None:
        return error_response("Order not found.", 404)

    # The patient may settle their own bill; counter staff may settle any.
    if order.user_id == user.id:
        allowed = rbac.has_permission(db, user, rbac.PHARMACY_ORDER_OWN)
    else:
        allowed = rbac.has_permission(db, user, rbac.PHARMACY_ORDER_FULFIL)

    if not allowed:
        return error_response("Not your order.", 403)

    body = {
        "razorpay_order_id": razorpay_order_id,
        "razorpay_payment_id": razorpay_payment_id,
        "razorpay_signature": razorpay_signature,
    }

    if payments.razorpay_enabled():

        ok, reason = payments.verify_razorpay_signature(
            razorpay_order_id=body.get("razorpay_order_id"),
            razorpay_payment_id=body.get("razorpay_payment_id"),
            razorpay_signature=body.get("razorpay_signature"),
        )

        if not ok:
            order = orders.fail_online_payment(
                db,
                order,
                reason=f"Gateway verification failed: {reason}",
                request=request,
                actor=orders.audit_actor(user)
            )
            return error_response(
                f"Payment could not be verified ({reason}).",
                402,
                order_no=order.order_no
            )

        provider = "RAZORPAY"
        reference = body.get("razorpay_payment_id")

    else:
        provider = "SIMULATED"
        reference = payments.simulated_transaction_id()

    try:
        order = orders.confirm_online_payment(
            db,
            order,
            provider=provider,
            reference=reference,
            request=request,
            actor=orders.audit_actor(user)
        )
    except orders.CheckoutError as error:
        return error_response(str(error), 409)

    from src.services.workflow_recorder import record_workflow_event

    record_workflow_event(
        db,
        workflow_type="PAYMENT",
        resource_type="pharmacy_order",
        resource_ref=f"pharmacy_orders#{order.id}",
        event_type="STATE_TRANSITION",
        payload={
            "payment_status": order.payment_status,
            "status": order.status,
            "provider": provider,
            "reference": reference
        },
        idempotency_key=f"pay-{order.order_no}-{reference}"
    )

    return ok_response(
        status=order.status,
        payment_status=order.payment_status,
        transaction_id=order.transaction_id,
        order_no=order.order_no,
        redirect=f"/pharmacy/order/{order.order_no}?placed=1",
        provider=provider
    )


@router.post("/api/order/{order_id}/cancel")
def cancel_order(
    request: Request,
    order_id: int,
    reason: str | None = Form(default=None),
    db: Session = Depends(get_db)
):

    user = rbac.get_session_user(request, db)

    if user is None:
        return error_response("Please login first.", 401)

    order = orders.get_order(db, order_id)

    if order is None:
        return error_response("Order not found.", 404)

    if order.user_id != user.id:
        if not rbac.has_permission(db, user, rbac.PHARMACY_ORDER_REFUND):
            return error_response("Not your order.", 403)

    elif not rbac.has_permission(db, user, rbac.PHARMACY_ORDER_CANCEL_OWN):
        return error_response("Your role cannot cancel orders.", 403)

    try:
        order = orders.cancel_order(
            db,
            order,
            reason=reason or "Cancelled by patient",
            request=request,
            actor=orders.audit_actor(user)
        )
    except orders.CheckoutError as error:
        return error_response(str(error), 409)

    return ok_response(
        status=order.status,
        message="Order cancelled and stock released.",
        redirect=f"/pharmacy/order/{order.order_no}"
    )


@router.post("/order/{order_id}/cancel")
def cancel_order_form(
    request: Request,
    order_id: int,
    reason: str | None = Form(default=None),
    db: Session = Depends(get_db)
):
    """Form version of the cancel button (works with JS switched off)."""

    response = cancel_order(request, order_id, reason, db)

    if getattr(response, "status_code", 200) < 400:
        return RedirectResponse(
            url=f"/pharmacy/order/{order_id}",
            status_code=303
        )

    return response


@router.post("/api/order/{order_id}/mark-paid")
def mark_paid(
    request: Request,
    order_id: int,
    db: Session = Depends(get_db)
):
    """Counter staff: 'the patient handed me cash'."""

    user = rbac.get_session_user(request, db)

    if user is None:
        return error_response("Please login first.", 401)

    if not rbac.has_permission(db, user, rbac.PHARMACY_ORDER_FULFIL):
        return error_response("Not allowed.", 403)

    order = orders.get_order(db, order_id)

    if order is None:
        return error_response("Order not found.", 404)

    order = orders.mark_cash_paid(
        db,
        order,
        request=request,
        actor=orders.audit_actor(user)
    )

    return ok_response(payment_status=order.payment_status, status=order.status)


# =========================================================
# NEARBY / EMERGENCY
# =========================================================

@router.get("/nearby", response_class=HTMLResponse)
def nearby_page(
    request: Request,
    medicine_id: int | None = Query(default=None),
    name: str | None = Query(default=None),
    db: Session = Depends(get_db)
):

    user, redirect = rbac.guard_page(
        request,
        db,
        rbac.PHARMACY_NEARBY_SEARCH,
        login_required=False
    )

    if redirect is not None:
        return redirect

    medicine = db.get(Medicine, medicine_id) if medicine_id else None

    result = nearby.find_for_medicine(
        db,
        medicine,
        medicine_label=name,
        use_google=True,
        persist_google=False
    )

    context = base_context(
        request,
        db,
        user,
        nearby=result,
        medicine=medicine,
        medicine_id=medicine_id,
        name=name or "",
        google_key_hint=(
            "Add GOOGLE_MAPS_API_KEY to .env to include live Google Maps "
            "results as well. Partner shops from the database are always shown."
            if not nearby.google_enabled() else None
        ),
    )

    return _templates(request).TemplateResponse(
        request,
        "pharmacy_nearby.html",
        context
    )


@router.get("/api/nearby")
def api_nearby(
    request: Request,
    medicine_id: int | None = Query(default=None),
    name: str | None = Query(default=None),
    lat: float | None = Query(default=None),
    lng: float | None = Query(default=None),
    radius: int | None = Query(default=None),
    use_google: bool = Query(default=True),
    db: Session = Depends(get_db)
):

    user = rbac.get_session_user(request, db)

    if not rbac.has_permission(db, user, rbac.PHARMACY_NEARBY_SEARCH):
        return error_response("Not allowed to search nearby shops.", 403)

    medicine = db.get(Medicine, medicine_id) if medicine_id else None

    center = (lat, lng) if lat is not None and lng is not None else None

    result = nearby.find_for_medicine(
        db,
        medicine,
        medicine_label=name,
        center=center,
        radius_m=radius,
        use_google=use_google,
        persist_google=True
    )

    return ok_response(**result)
