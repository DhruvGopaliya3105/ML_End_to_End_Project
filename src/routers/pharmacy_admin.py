"""Pharmacy admin / super user console at ``/pharmacy/admin``.

Tabs (server rendered, the buttons call the JSON API under
``/pharmacy/admin/api/*``):

* Orders      - fulfilment queue: cash received, hand over, cancel / refund
* Catalog     - add / edit / delete medicines: price, MRP, stock, photo, tags
* Nearby      - the partner chemists the emergency search reads from SQL
* Audit       - who did what, with the before / after JSON of each change
* Access      - the role -> permission matrix (role based access control)
* Snapshots   - take / pin / preview / restore / prune (controlled rollback)

Access rules
------------
Every route asks ``rbac.has_permission`` for one specific permission, and the
page itself passes the same checks, so a tab simply does not appear for a role
that is not allowed instead of erroring after a click. ``SUPERUSER`` holds
everything (including ``pharmacy.role.write``, which is what allows changing
another user's role); ``ADMIN`` has the same minus role editing; a PHARMACIST
sees only Orders / stock / Nearby.

Every destructive write takes an automatic snapshot first (``AUTO_PRE_BULK``),
so it can be undone from the Snapshots tab.
"""

import logging
from datetime import datetime

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Query,
    Request,
    UploadFile
)

from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response
)

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.config import STATIC_DIR
from src.database.connection import get_db
from src.models.appointment import Appointment
from src.models.doctor import Doctor
from src.models.medicine import Medicine
from src.models.nearby_pharmacy import NearbyPharmacy
from src.models.pharmacy_order import PharmacyOrder
from src.models.pharmacy_snapshot import PharmacySnapshot
from src.models.user import User
from src.routers.pharmacy import base_context
from src.routers.pharmacy import error_response
from src.routers.pharmacy import ok_response
from src.security import rbac
from src.services import pharmacy_audit_service as audit
from src.services import pharmacy_catalog_service as catalog
from src.services import pharmacy_nearby_service as nearby
from src.services import pharmacy_order_service as orders
from src.services import pharmacy_snapshot_service as snapshot_service


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/pharmacy/admin",
    tags=["Pharmacy Admin"]
)

ALLOWED_IMAGE_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}

MAX_IMAGE_BYTES = 5 * 1024 * 1024

TABS = [
    ("orders", "Orders", rbac.PHARMACY_ORDER_READ_ALL),
    ("catalog", "Catalog", rbac.PHARMACY_CATALOG_READ),
    # NOTE: this tab is gated on the *write* permission on purpose. If it
    # used pharmacy.view, a patient would technically satisfy "may open the
    # admin console" and get a 200 on /pharmacy/admin?tab=nearby.
    ("nearby", "Nearby shops", rbac.PHARMACY_NEARBY_WRITE),
    ("audit", "Audit log", rbac.PHARMACY_AUDIT_READ),
    ("access", "Access control", rbac.PHARMACY_ROLE_WRITE),
    ("snapshots", "Snapshots / rollback", rbac.PHARMACY_SNAPSHOT_CREATE),
]


# =========================================================
# GUARDS
# =========================================================

def admin_page(
    request: Request,
    db: Session,
    permission: str | None
):
    """Returns (user, redirect). Staff permissions are required, so a patient
    is bounced to the dashboard rather than getting a 403 page."""

    user, redirect = rbac.guard_page(request, db, permission)

    if redirect is not None:
        return None, redirect

    return user, None


def api_guard(
    request: Request,
    db: Session,
    permission: str
) -> tuple[User | None, JSONResponse | None]:

    user = rbac.get_session_user(request, db)

    if user is None:
        return None, error_response("Please login first.", 401, login_url="/login")

    if not rbac.has_permission(db, user, permission):
        return None, error_response(
            f"Your role ({rbac.user_role(user)}) needs the "
            f"'{permission}' permission for this.",
            403
        )

    return user, None


# =========================================================
# THE CONSOLE
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
def admin_home(
    request: Request,
    tab: str = Query(default="orders"),
    db: Session = Depends(get_db)
):

    first_allowed = None

    for _slug, _label, permission in TABS:
        if rbac.has_permission(
            db,
            rbac.get_session_user(request, db),
            permission
        ):
            first_allowed = permission
            break

    if first_allowed is None:
        # This role may not see any admin tab. Bounce instead of rendering an
        # empty console, so "no permissions" is obvious to the user.
        session_user = rbac.get_session_user(request, db)

        if session_user is None:
            return RedirectResponse(url="/login", status_code=303)

        return RedirectResponse(url="/dashboard", status_code=303)

    user, redirect = admin_page(request, db, first_allowed)

    if redirect is not None:
        return redirect

    if tab not in {slug for slug, _label, _perm in TABS}:
        tab = "orders"

    # A tab the role may not see is swapped for the first allowed one.
    wanted = next((row for row in TABS if row[0] == tab), None)

    if wanted and not rbac.has_permission(db, user, wanted[2]):
        tab = next(
            (row[0] for row in TABS if rbac.has_permission(db, user, row[2])),
            "orders"
        )

    context = base_context(request, db, user)

    context["tabs"] = [
        {
            "slug": slug,
            "label": label,
            "allowed": rbac.has_permission(db, user, permission),
        }
        for slug, label, permission in TABS
    ]
    context["tab"] = tab

    if tab == "orders":
        rows, total = orders.list_orders(db, limit=60)
        context["order_rows"] = [
            {
                **orders.order_to_dict(db, order, detailed=True),
                "badge": orders.status_badge(order),
            }
            for order in rows
        ]
        context["order_total"] = total
        context["order_stats"] = orders.order_totals(db)

    elif tab == "catalog":
        rows, total = catalog.list_medicines(
            db,
            include_inactive=True,
            limit=200,
            sort="name_asc"
        )
        context["catalog_rows"] = [
            catalog.medicine_to_dict(db, medicine) for medicine in rows
        ]
        context["catalog_total"] = total
        context["diseases"] = catalog.list_diseases(db)
        context["stats"] = catalog.catalog_stats(db)
        context["low_stock"] = [
            catalog.medicine_to_dict(db, medicine, with_diseases=False)
            for medicine in catalog.low_stock_rows(db, limit=10)
        ]

    elif tab == "nearby":
        context["shops"] = [
            nearby.shop_to_dict(shop) for shop in nearby.all_shops(db)
        ]
        context["catalog_rows"] = [
            catalog.medicine_to_dict(db, medicine, with_diseases=False)
            for medicine in catalog.list_medicines(db, limit=500)[0]
        ]
        context["google_enabled"] = nearby.google_enabled()

    elif tab == "audit":
        log_rows = audit.list_logs(db, limit=150)
        context["logs"] = [audit.to_log_dict(row) for row in log_rows]
        context["log_total"] = audit.count_logs(db)
        context["actions"] = audit.action_options(db)

    elif tab == "access":
        context["roles"] = [
            {
                "role": role,
                "label": rbac.ROLE_LABELS.get(role, role),
                "permissions": rbac.effective_permissions(db, role),
                "is_default_all": rbac.DEFAULT_ROLE_PERMISSIONS.get(role) == "*",
            }
            for role in rbac.ROLES
        ]
        context["permission_list"] = [
            {"key": key, "label": label, "group": group}
            for key, label, group in rbac.PERMISSIONS
        ]
        context["users"] = [
            {
                "id": row.id,
                "name": row.name,
                "email": row.email,
                "role": (row.role or "PATIENT").upper(),
                "is_active": bool(row.is_active),
            }
            for row in db.query(User).order_by(User.id).limit(200).all()
        ]
        context["is_superuser_actor"] = rbac.is_superuser(user)

    elif tab == "snapshots":
        context["snapshots"] = [
            snapshot_service.snapshot_to_dict(row)
            for row in snapshot_service.list_snapshots(db, limit=30)
        ]
        context["scopes"] = list(snapshot_service.SCOPES.keys())

    # System overview tiles for the admin landing view
    context["overview"] = {
        "patients": db.query(User).filter(
            User.role == "PATIENT",
            User.is_active == True
        ).count(),
        "doctors": db.query(Doctor).filter(
            Doctor.is_active == True
        ).count(),
        "appointments": db.query(Appointment).count(),
        "revenue": float(
            db.query(func.sum(PharmacyOrder.total)).filter(
                PharmacyOrder.payment_status == "PAID"
            ).scalar() or 0
        ),
    }

    return request.app.state.templates.TemplateResponse(
        request,
        "pharmacy_admin.html",
        context
    )


# =========================================================
# ORDERS (fulfilment queue)
# =========================================================

@router.get("/api/orders")
def list_orders_api(
    request: Request,
    status: str | None = Query(default=None),
    payment: str | None = Query(default=None),
    search: str | None = Query(default=None),
    urgent: bool = Query(default=False),
    db: Session = Depends(get_db)
):

    user, denied = api_guard(request, db, rbac.PHARMACY_ORDER_READ_ALL)

    if denied is not None:
        return denied

    rows, total = orders.list_orders(
        db,
        status=status,
        payment=payment,
        search=search,
        urgent_only=urgent,
        limit=100
    )

    return ok_response(
        total=total,
        orders=[
            {
                **orders.order_to_dict(db, order, detailed=True),
                "badge": orders.status_badge(order),
            }
            for order in rows
        ]
    )


@router.post("/api/orders/{order_id}/fulfil")
def fulfil_order(
    request: Request,
    order_id: int,
    action: str = Form(...),
    reason: str | None = Form(default=None),
    db: Session = Depends(get_db)
):
    """One endpoint for the three counter actions.

    mark_paid     - cash physically received
    handed_over   - medicines physically given to the patient
    cancel        - free the stock, no money moved
    refund        - money back + stock back (needs pharmacy.order.refund)
    """

    action = (action or "").strip().lower()

    permission = (
        rbac.PHARMACY_ORDER_REFUND
        if action in ("refund", "cancel") else rbac.PHARMACY_ORDER_FULFIL
    )

    user, denied = api_guard(request, db, permission)

    if denied is not None:
        return denied

    order = orders.get_order(db, order_id)

    if order is None:
        return error_response("Order not found.", 404)

    actor = orders.audit_actor(user)

    try:
        if action == "mark_paid":
            order = orders.mark_cash_paid(
                db, order, request=request, actor=actor
            )
        elif action == "handed_over":
            order = orders.mark_handed_over(
                db, order, request=request, actor=actor
            )
        elif action == "cancel":
            order = orders.cancel_order(
                db, order,
                reason=reason or "Cancelled at the counter",
                request=request,
                actor=actor,
                allow_paid=rbac.has_permission(db, user, rbac.PHARMACY_ORDER_REFUND)
            )
        elif action == "refund":
            order = orders.refund_order(
                db, order,
                reason=reason or "Refunded by pharmacy",
                request=request,
                actor=actor
            )
        else:
            return error_response(f"Unknown action '{action}'.", 400)
    except orders.CheckoutError as error:
        return error_response(str(error), 409)
    except Exception:  # noqa: BLE001
        logger.exception("order fulfilment action failed")
        db.rollback()
        return error_response("Could not update that order.")

    return ok_response(
        status=order.status,
        payment_status=order.payment_status,
        order=orders.order_to_dict(db, order, detailed=True)
    )


@router.get("/api/orders/export.csv")
def export_orders(
    request: Request,
    status: str | None = Query(default=None),
    db: Session = Depends(get_db)
):

    user, denied = api_guard(request, db, rbac.PHARMACY_ORDER_READ_ALL)

    if denied is not None:
        return denied

    rows, _total = orders.list_orders(db, status=status, limit=500)

    lines = [
        "order_no,placed_on,patient,items,payment_method,payment_status,"
        "status,subtotal,delivery_fee,total"
    ]

    for order in rows:
        data = orders.order_to_dict(db, order, detailed=True)
        lines.append(",".join(str(cell) for cell in (
            data["order_no"],
            (order.created_at or datetime.utcnow()).strftime("%Y-%m-%d %H:%M"),
            (data.get("patient") or {}).get("name", ""),
            data["item_count"],
            data["payment_method"],
            data["payment_status"],
            data["status"],
            f'{data["subtotal"]:.2f}',
            f'{data["delivery_fee"]:.2f}',
            f'{data["total"]:.2f}',
        )))

    return Response(
        content="\n".join(lines),
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="pharmacy_orders.csv"'
        }
    )


# =========================================================
# CATALOG
# =========================================================

@router.get("/api/medicines")
def medicines_api(
    request: Request,
    q: str | None = Query(default=None),
    disease: str | None = Query(default=None),
    low_stock: bool = Query(default=False),
    db: Session = Depends(get_db)
):

    user, denied = api_guard(request, db, rbac.PHARMACY_CATALOG_READ)

    if denied is not None:
        return denied

    rows, total = catalog.list_medicines(
        db,
        search=q,
        disease_slug=disease,
        low_stock_only=low_stock,
        include_inactive=True,
        limit=200,
        sort="name_asc"
    )

    return ok_response(
        total=total,
        medicines=[catalog.medicine_to_dict(db, row) for row in rows]
    )


@router.post("/api/medicines")
def create_medicine_api(
    request: Request,
    name: str = Form(...),
    price: float = Form(...),
    stock: int = Form(default=0),
    generic_name: str | None = Form(default=None),
    brand: str | None = Form(default=None),
    form: str = Form(default="TABLET"),
    strength: str | None = Form(default=None),
    pack_size: str | None = Form(default=None),
    mrp: float | None = Form(default=None),
    low_stock_alert: int = Form(default=10),
    requires_prescription: str | None = Form(default=None),
    diseases: str | None = Form(default=None),
    sku: str | None = Form(default=None),
    description: str | None = Form(default=None),
    dosage_info: str | None = Form(default=None),
    warning: str | None = Form(default=None),
    image_url: str | None = Form(default=None),
    db: Session = Depends(get_db)
):

    user, denied = api_guard(request, db, rbac.PHARMACY_CATALOG_WRITE)

    if denied is not None:
        return denied

    if float(price) < 0:
        return error_response("Price cannot be negative.", 400)

    try:
        medicine = catalog.create_medicine(
            db,
            {
                "name": name,
                "price": price,
                "stock": stock,
                "generic_name": generic_name,
                "brand": brand,
                "form": form,
                "strength": strength,
                "pack_size": pack_size,
                "mrp": mrp,
                "low_stock_alert": low_stock_alert,
                "requires_prescription": bool(requires_prescription),
                "description": description,
                "dosage_info": dosage_info,
                "warning": warning,
                "image_url": image_url,
                "sku": sku,
            },
            diseases=_split_tags(diseases) or [form or "General"]
        )
    except ValueError as error:
        return error_response(str(error), 400)
    except Exception:  # noqa: BLE001
        logger.exception("medicine create failed")
        db.rollback()
        return error_response("Could not save that medicine.")

    audit.log_activity(
        db,
        action="pharmacy.medicine.create",
        entity_type="medicine",
        entity_id=medicine.id,
        description=f"Added {medicine.name} (Rs {catalog.money(medicine.price):.2f})",
        after=catalog_row(medicine),
        actor=orders.audit_actor(user),
        request=request,
        rollback_available=True,
        commit=True
    )

    return ok_response(
        medicine=catalog.medicine_to_dict(db, medicine),
        message=f"{medicine.name} is in the catalog."
    )


def _split_tags(value: str | None) -> list[str]:
    if not value:
        return []
    parts = [part.strip() for part in value.replace(";", ",").split(",")]
    return [part for part in parts if part]


def catalog_row(medicine: Medicine) -> dict:
    return audit.row_to_dict(medicine)


@router.post("/api/medicines/{medicine_id}")
@router.put("/api/medicines/{medicine_id}")
def update_medicine_api(
    request: Request,
    medicine_id: int,
    name: str | None = Form(default=None),
    price: float | None = Form(default=None),
    stock: int | None = Form(default=None),
    generic_name: str | None = Form(default=None),
    brand: str | None = Form(default=None),
    form: str | None = Form(default=None),
    strength: str | None = Form(default=None),
    pack_size: str | None = Form(default=None),
    mrp: float | None = Form(default=None),
    low_stock_alert: int | None = Form(default=None),
    requires_prescription: str | None = Form(default=None),
    is_active: str | None = Form(default=None),
    diseases: str | None = Form(default=None),
    description: str | None = Form(default=None),
    dosage_info: str | None = Form(default=None),
    side_effects: str | None = Form(default=None),
    warning: str | None = Form(default=None),
    image_url: str | None = Form(default=None),
    image_path: str | None = Form(default=None),
    db: Session = Depends(get_db)
):
    """Edit one medicine. Empty fields are left untouched, and `stock` is an
    absolute number (use the /stock endpoint for +/- adjustments)."""

    user, denied = api_guard(request, db, rbac.PHARMACY_CATALOG_WRITE)

    if denied is not None:
        return denied

    medicine = catalog.get_medicine(db, medicine_id)

    if medicine is None:
        return error_response("Medicine not found.", 404)

    before = catalog_row(medicine)

    incoming = {}

    for key, value in (
        ("name", name), ("price", price), ("stock", stock),
        ("generic_name", generic_name), ("brand", brand), ("form", form),
        ("strength", strength), ("pack_size", pack_size), ("mrp", mrp),
        ("low_stock_alert", low_stock_alert), ("description", description),
        ("dosage_info", dosage_info), ("side_effects", side_effects),
        ("warning", warning), ("image_url", image_url),
        ("image_path", image_path),
    ):
        if value is not None and value != "":
            incoming[key] = value

    if requires_prescription is not None:
        incoming["requires_prescription"] = bool(requires_prescription)

    if is_active is not None:
        incoming["is_active"] = bool(is_active)

    try:
        medicine = catalog.update_medicine(
            db,
            medicine,
            incoming,
            diseases=_split_tags(diseases) or None
        )
    except Exception:  # noqa: BLE001
        logger.exception("medicine update failed")
        db.rollback()
        return error_response("Could not save those changes.")

    audit.log_activity(
        db,
        action="pharmacy.medicine.update",
        entity_type="medicine",
        entity_id=medicine.id,
        description=f"Updated {medicine.name}",
        before=before,
        after=catalog_row(medicine),
        actor=orders.audit_actor(user),
        request=request,
        rollback_available=True,
        commit=True
    )

    return ok_response(
        medicine=catalog.medicine_to_dict(db, medicine),
        message="Saved."
    )


@router.post("/api/medicines/{medicine_id}/stock")
def stock_api(
    request: Request,
    medicine_id: int,
    change: int = Form(...),
    mode: str = Form(default="delta"),
    reason: str | None = Form(default=None),
    db: Session = Depends(get_db)
):
    """mode=delta -> +50 / -3 (a correction). mode=set -> absolute number."""

    user, denied = api_guard(request, db, rbac.PHARMACY_STOCK_WRITE)

    if denied is not None:
        return denied

    medicine = catalog.get_medicine(db, medicine_id)

    if medicine is None:
        return error_response("Medicine not found.", 404)

    before = int(medicine.stock or 0)

    catalog.adjust_stock(
        db,
        medicine,
        change,
        absolute=(mode or "delta").lower() == "set"
    )

    db.commit()
    db.refresh(medicine)

    audit.log_activity(
        db,
        action="pharmacy.medicine.stock",
        entity_type="medicine",
        entity_id=medicine.id,
        description=(
            f"Stock for {medicine.name}: {before} -> {int(medicine.stock or 0)}"
            + (f" ({reason})" if reason else "")
        ),
        before={"stock": before},
        after={"stock": int(medicine.stock or 0)},
        actor=orders.audit_actor(user),
        request=request,
        rollback_available=True,
        commit=True
    )

    return ok_response(
        stock=int(medicine.stock or 0),
        medicine=catalog.medicine_to_dict(db, medicine, with_diseases=False)
    )


@router.post("/api/medicines/{medicine_id}/toggle")
def toggle_medicine_api(
    request: Request,
    medicine_id: int,
    db: Session = Depends(get_db)
):

    user, denied = api_guard(request, db, rbac.PHARMACY_CATALOG_WRITE)

    if denied is not None:
        return denied

    medicine = catalog.get_medicine(db, medicine_id)

    if medicine is None:
        return error_response("Medicine not found.", 404)

    medicine = catalog.set_active(db, medicine, not medicine.is_active)

    audit.log_activity(
        db,
        action="pharmacy.medicine.visibility",
        entity_type="medicine",
        entity_id=medicine.id,
        description=f"{medicine.name} is now {'visible' if medicine.is_active else 'hidden'}",
        severity="WARN",
        actor=orders.audit_actor(user),
        request=request,
        rollback_available=True,
        commit=True
    )

    return ok_response(is_active=bool(medicine.is_active))


@router.delete("/api/medicines/{medicine_id}")
def delete_medicine_api(
    request: Request,
    medicine_id: int,
    confirm: str = Form(default=""),
    db: Session = Depends(get_db)
):
    """Deleting is allowed, but only with confirm=DELETE, and a snapshot that
    can undo it is taken first (pinned so prune() cannot remove it)."""

    user, denied = api_guard(request, db, rbac.PHARMACY_CATALOG_WRITE)

    if denied is not None:
        return denied

    medicine = catalog.get_medicine(db, medicine_id)

    if medicine is None:
        return error_response("Medicine not found.", 404)

    if (confirm or "").upper() != "DELETE":
        return error_response(
            "Type DELETE to confirm. A snapshot was not needed and nothing "
            "was changed.",
            400
        )

    safety = snapshot_service.create_snapshot(
        db,
        label=f"Before deleting {medicine.name}",
        description=(
            f"Automatic: {user.name} deleted medicine #{medicine.id} "
            f"({medicine.sku})"
        ),
        scope="CATALOG",
        actor=orders.audit_actor(user),
        trigger="PRE_DELETE",
        is_pinned=True,
        request=request
    )

    before = catalog_row(medicine)
    name = medicine.name

    try:
        catalog.delete_medicine(db, medicine)
    except Exception:  # noqa: BLE001 - rows already sold cannot be erased
        db.rollback()
        catalog.set_active(db, medicine, False)
        audit.log_activity(
            db,
            action="pharmacy.medicine.hide_instead_of_delete",
            entity_type="medicine",
            entity_id=medicine.id,
            description=(
                f"{name} is referenced by existing orders, so it was hidden "
                "from the catalog instead of deleted"
            ),
            severity="WARN",
            actor=orders.audit_actor(user),
            request=request,
            rollback_available=True,
            snapshot_id=safety.id,
            commit=True
        )
        return ok_response(
            hidden=True,
            snapshot_id=safety.id,
            message=(
                f"{name} appears in past orders, so it was hidden instead of "
                "deleted. Past invoices stay correct."
            )
        )

    audit.log_activity(
        db,
        action="pharmacy.medicine.delete",
        entity_type="medicine",
        entity_id=medicine_id,
        description=f"Deleted {name}",
        severity="CRITICAL",
        before=before,
        actor=orders.audit_actor(user),
        request=request,
        rollback_available=True,
        snapshot_id=safety.id,
        commit=True
    )

    return ok_response(
        deleted=True,
        snapshot_id=safety.id,
        message=f"{name} deleted. Undo point: snapshot #{safety.id}."
    )


@router.post("/api/medicines/{medicine_id}/image")
async def upload_image_api(
    request: Request,
    medicine_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Product photo upload -> /static/images/pharmacy/custom/<name>."""

    user, denied = api_guard(request, db, rbac.PHARMACY_CATALOG_WRITE)

    if denied is not None:
        return denied

    medicine = catalog.get_medicine(db, medicine_id)

    if medicine is None:
        return error_response("Medicine not found.", 404)

    content_type = (file.content_type or "").lower()

    if content_type not in ALLOWED_IMAGE_TYPES:
        return error_response(
            "Only PNG, JPG, WEBP or GIF images are accepted.",
            400
        )

    body = await file.read()

    if len(body) > MAX_IMAGE_BYTES:
        return error_response("That image is larger than 5 MB.", 400)

    if not body:
        return error_response("That file is empty.", 400)

    target_dir = STATIC_DIR / "images" / "pharmacy" / "custom"
    target_dir.mkdir(parents=True, exist_ok=True)

    safe_stem = "".join(
        char for char in (file.filename or "image").rsplit(".", 1)[0]
        if char.isalnum() or char in ("-", "_")
    )[:40] or "image"

    filename = (
        f"{safe_stem}-{medicine.id}-{datetime.utcnow():%Y%m%d%H%M%S}"
        f"{ALLOWED_IMAGE_TYPES[content_type]}"
    )

    (target_dir / filename).write_bytes(body)

    medicine.image_path = f"images/pharmacy/custom/{filename}"
    medicine.image_url = None

    db.commit()
    db.refresh(medicine)

    audit.log_activity(
        db,
        action="pharmacy.medicine.image",
        entity_type="medicine",
        entity_id=medicine.id,
        description=f"Photo for {medicine.name} set to {filename}",
        actor=orders.audit_actor(user),
        request=request,
        commit=True
    )

    return ok_response(
        image=catalog.medicine_image(medicine),
        medicine=catalog.medicine_to_dict(db, medicine, with_diseases=False)
    )


@router.post("/api/catalog/bulk-price")
def bulk_price_api(
    request: Request,
    percent: float | None = Form(default=None),
    flat: float | None = Form(default=None),
    disease: str | None = Form(default=None),
    db: Session = Depends(get_db)
):
    """Bulk price change with an automatic undo point."""

    user, denied = api_guard(request, db, rbac.PHARMACY_CATALOG_WRITE)

    if denied is not None:
        return denied

    if percent is None and flat is None:
        return error_response("Give a percentage or a flat amount.", 400)

    try:
        result = snapshot_service.bulk_price_update(
            db,
            percent=percent,
            flat=flat,
            disease_slug=disease
        )
    except ValueError as error:
        return error_response(str(error), 400)
    except Exception:  # noqa: BLE001
        logger.exception("bulk price update failed")
        db.rollback()
        return error_response("Bulk price update failed. Nothing was changed.")

    audit.log_activity(
        db,
        action="pharmacy.medicine.bulk_price",
        entity_type="medicine",
        entity_id=None,
        description=(
            f"Bulk price change ({result['changed']} row(s)); undo snapshot "
            f"#{result['snapshot_id']}"
        ),
        severity="WARN",
        after=result,
        actor=orders.audit_actor(user),
        request=request,
        rollback_available=True,
        snapshot_id=result["snapshot_id"],
        commit=True
    )

    return ok_response(**result)


@router.post("/api/catalog/stock-import")
def stock_import_api(
    request: Request,
    csv_text: str = Form(...),
    mode: str = Form(default="set"),
    db: Session = Depends(get_db)
):
    """Paste CSV: ``sku,stock`` or ``sku,stock,price`` (header optional).

    Handy after a physical stock count. A snapshot is taken first, so a typo
    in the paste can be rolled back from the Snapshots tab.
    """

    user, denied = api_guard(request, db, rbac.PHARMACY_STOCK_WRITE)

    if denied is not None:
        return denied

    rows = [line.strip() for line in csv_text.splitlines() if line.strip()]

    if not rows:
        return error_response("Paste at least one 'sku,stock' line.", 400)

    if rows[0].lower().startswith(("sku", "medicine", "code")):
        rows = rows[1:]

    safety = snapshot_service.create_snapshot(
        db,
        label="Before stock import",
        description=f"Automatic: {len(rows)} CSV line(s), mode {mode}",
        scope="STOCK",
        actor=orders.audit_actor(user),
        trigger="AUTO_PRE_BULK",
        request=request,
        commit=False
    )

    db.commit()
    db.refresh(safety)

    updated = []
    failed = []

    for line in rows:

        parts = [part.strip() for part in line.replace(";", ",").split(",")]

        if len(parts) < 2:
            failed.append({"line": line, "reason": "needs sku,stock"})
            continue

        sku, stock_text = parts[0], parts[1]

        try:
            quantity = int(float(stock_text))
        except ValueError:
            failed.append({"line": line, "reason": "stock is not a number"})
            continue

        medicine = catalog.get_medicine_by_sku(db, sku) if sku else None

        if medicine is None:
            # Allow a plain product name when the shop owner has no SKU.
            from sqlalchemy import func as sa_func

            medicine = (
                db.query(Medicine)
                .filter(
                    sa_func.lower(Medicine.name).like(f"%{sku.lower()}%")
                )
                .first()
            )

        if medicine is None:
            failed.append({"line": line, "reason": f"no medicine matches '{sku}'"})
            continue

        catalog.adjust_stock(
            db,
            medicine,
            quantity,
            absolute=(mode or "set").lower() != "delta"
        )

        if len(parts) >= 3 and parts[2]:
            try:
                medicine.price = catalog.money(float(parts[2]))
            except ValueError:
                failed.append({"line": line, "reason": "price ignored (not a number)"})

        updated.append({
            "sku": medicine.sku,
            "name": medicine.name,
            "stock": int(medicine.stock or 0),
        })

    db.commit()

    audit.log_activity(
        db,
        action="pharmacy.medicine.stock_import",
        entity_type="medicine",
        entity_id=None,
        description=(
            f"Stock import ({len(updated)} updated, {len(failed)} skipped), "
            f"undo snapshot #{safety.id}"
        ),
        severity="WARN",
        after={"updated": updated, "failed": failed},
        actor=orders.audit_actor(user),
        request=request,
        rollback_available=True,
        snapshot_id=safety.id,
        commit=True
    )

    return ok_response(
        updated=updated,
        failed=failed,
        snapshot_id=safety.id,
        message=(
            f"{len(updated)} medicine(s) updated. Snapshot #{safety.id} can "
            "undo this."
        )
    )


# =========================================================
# NEARBY SHOPS
# =========================================================

@router.post("/api/nearby/shops")
def upsert_shop_api(
    request: Request,
    name: str = Form(...),
    shop_id: int | None = Form(default=None),
    address: str | None = Form(default=None),
    area: str | None = Form(default=None),
    city: str | None = Form(default=None),
    pincode: str | None = Form(default=None),
    phone: str | None = Form(default=None),
    whatsapp: str | None = Form(default=None),
    latitude: float | None = Form(default=None),
    longitude: float | None = Form(default=None),
    open_24x7: str | None = Form(default=None),
    opening_hours: str | None = Form(default=None),
    is_partner: str | None = Form(default="on"),
    notes: str | None = Form(default=None),
    db: Session = Depends(get_db)
):

    user, denied = api_guard(request, db, rbac.PHARMACY_NEARBY_WRITE)

    if denied is not None:
        return denied

    shop = db.get(NearbyPharmacy, shop_id) if shop_id else None

    if shop_id and shop is None:
        return error_response("Shop not found.", 404)

    shop = nearby.upsert_shop(db, {
        "name": name,
        "address": address,
        "area": area,
        "city": city or nearby.default_city(),
        "pincode": pincode,
        "phone": phone,
        "whatsapp": whatsapp,
        "latitude": latitude,
        "longitude": longitude,
        "open_24x7": bool(open_24x7),
        "opening_hours": opening_hours,
        "is_partner": bool(is_partner),
        "notes": notes,
        "is_active": True,
    }, shop=shop)

    db.commit()
    db.refresh(shop)

    audit.log_activity(
        db,
        action="pharmacy.nearby.shop_upsert",
        entity_type="nearby_pharmacy",
        entity_id=shop.id,
        description=f"Saved shop '{shop.name}' ({'partner' if shop.is_partner else 'listed'})",
        after=audit.row_to_dict(shop),
        actor=orders.audit_actor(user),
        request=request,
        rollback_available=True,
        commit=True
    )

    return ok_response(shop=nearby.shop_to_dict(shop))


@router.post("/api/nearby/shops/{shop_id}/toggle")
def toggle_shop_api(
    request: Request,
    shop_id: int,
    db: Session = Depends(get_db)
):

    user, denied = api_guard(request, db, rbac.PHARMACY_NEARBY_WRITE)

    if denied is not None:
        return denied

    shop = db.get(NearbyPharmacy, shop_id)

    if shop is None:
        return error_response("Shop not found.", 404)

    shop.is_active = not shop.is_active
    db.commit()

    audit.log_activity(
        db,
        action="pharmacy.nearby.shop_toggle",
        entity_type="nearby_pharmacy",
        entity_id=shop.id,
        description=f"'{shop.name}' marked {'active' if shop.is_active else 'inactive'}",
        actor=orders.audit_actor(user),
        request=request,
        commit=True
    )

    return ok_response(is_active=bool(shop.is_active))


@router.post("/api/nearby/stock")
def shop_stock_api(
    request: Request,
    shop_id: int = Form(...),
    medicine_id: int = Form(...),
    stock: int = Form(default=0),
    price: float | None = Form(default=None),
    db: Session = Depends(get_db)
):

    user, denied = api_guard(request, db, rbac.PHARMACY_NEARBY_WRITE)

    if denied is not None:
        return denied

    shop = db.get(NearbyPharmacy, shop_id)
    medicine = catalog.get_medicine(db, medicine_id)

    if shop is None or medicine is None:
        return error_response("Shop or medicine not found.", 404)

    row = nearby.set_shop_stock(
        db, shop, medicine, stock=stock, price=price
    )

    db.commit()
    db.refresh(row)

    audit.log_activity(
        db,
        action="pharmacy.nearby.stock",
        entity_type="nearby_pharmacy",
        entity_id=shop.id,
        description=(
            f"{shop.name}: {medicine.name} stock = {int(row.stock or 0)}"
        ),
        after={"stock": int(row.stock or 0), "price": row.price},
        actor=orders.audit_actor(user),
        request=request,
        rollback_available=True,
        commit=True
    )

    return ok_response(shop=nearby.shop_to_dict(shop))


@router.post("/api/nearby/sync-google")
def sync_google_api(
    request: Request,
    q: str | None = Form(default=None),
    db: Session = Depends(get_db)
):
    """Pull the Google list into SQL once, so the emergency page is then fast
    and works with no internet / no key."""

    user, denied = api_guard(request, db, rbac.PHARMACY_NEARBY_WRITE)

    if denied is not None:
        return denied

    if not nearby.google_enabled():
        return error_response(
            "GOOGLE_MAPS_API_KEY is not set in .env, so there is nothing to "
            "import. Add shops by hand below - the emergency search uses them "
            "straight from SQL.",
            409
        )

    results, status = nearby.google_search(
        query=(q or f"pharmacy near {nearby.default_city()}"),
        center=nearby.default_center(),
        radius_m=nearby.default_radius_m()
    )

    imported = nearby.import_google_results(db, results) if results else 0

    audit.log_activity(
        db,
        action="pharmacy.nearby.sync_google",
        entity_type="nearby_pharmacy",
        entity_id=None,
        description=f"Google Places import: {len(results)} found, {imported} saved ({status})",
        actor=orders.audit_actor(user),
        request=request,
        commit=True
    )

    return ok_response(
        found=len(results),
        saved=imported,
        google_status=status,
        shops=[nearby.shop_to_dict(row) for row in nearby.all_shops(db)]
    )


# =========================================================
# AUDIT
# =========================================================

@router.get("/api/audit")
def audit_api(
    request: Request,
    action: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    actor: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=150, ge=1, le=500),
    db: Session = Depends(get_db)
):

    user, denied = api_guard(request, db, rbac.PHARMACY_AUDIT_READ)

    if denied is not None:
        return denied

    filters = {
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "actor": actor,
        "severity": severity,
        "date_from": date_from,
        "date_to": date_to,
        "search": search,
    }

    rows = audit.list_logs(db, limit=limit, **filters)

    return ok_response(
        total=audit.count_logs(db, **filters),
        logs=[audit.to_log_dict(row) for row in rows]
    )


@router.get("/api/audit/export.csv")
def audit_export_api(
    request: Request,
    db: Session = Depends(get_db)
):

    user, denied = api_guard(request, db, rbac.PHARMACY_AUDIT_READ)

    if denied is not None:
        return denied

    rows = [
        audit.to_log_dict(row)
        for row in audit.list_logs(db, limit=500)
    ]

    return Response(
        content=audit.as_csv(rows),
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="pharmacy_audit_log.csv"'
        }
    )


# =========================================================
# ACCESS CONTROL
# =========================================================

@router.post("/api/roles/permission")
def set_permission_api(
    request: Request,
    role: str = Form(...),
    permission: str = Form(...),
    allowed: str | None = Form(default=None),
    note: str | None = Form(default=None),
    db: Session = Depends(get_db)
):
    """Write a row into ``role_permissions`` that overrides the code default.

    SUPERUSER is refused on purpose: locking the last super user out of the
    pharmacy is the one mistake this screen must not be able to make.
    """

    user, denied = api_guard(request, db, rbac.PHARMACY_ROLE_WRITE)

    if denied is not None:
        return denied

    role = (role or "").upper()

    if role not in rbac.ROLES:
        return error_response("Unknown role.", 400)

    if role == rbac.ROLE_SUPERUSER:
        return error_response(
            "The Super User always has every permission - it cannot be "
            "changed here.",
            400
        )

    known = {key for key, _label, _group in rbac.PERMISSIONS}

    if permission not in known and not permission.endswith(".*"):
        return error_response("Unknown permission key.", 400)

    from src.models.role_permission import RolePermission

    row = (
        db.query(RolePermission)
        .filter(
            RolePermission.role == role,
            RolePermission.permission == permission
        )
        .first()
    )

    before = audit.row_to_dict(row) if row else None

    if row is None:
        row = RolePermission(
            role=role,
            permission=permission,
        )
        db.add(row)

    row.is_allowed = bool(allowed)
    row.note = (note or "")[:255] or None
    row.updated_by_user_id = user.id
    row.updated_by_name = user.name

    db.commit()

    audit.log_activity(
        db,
        action="pharmacy.role.permission",
        entity_type="role_permission",
        entity_id=row.id,
        description=(
            f"Role {role}: {permission} = "
            f"{'ALLOWED' if row.is_allowed else 'DENIED'}"
        ),
        severity="CRITICAL",
        before=before,
        after=audit.row_to_dict(row),
        actor=orders.audit_actor(user),
        request=request,
        rollback_available=True,
        commit=True
    )

    return ok_response(
        role=role,
        permission=permission,
        allowed=bool(row.is_allowed),
        matrix=rbac.effective_permissions(db, role)
    )


@router.post("/api/roles/reset")
def reset_roles_api(
    request: Request,
    role: str | None = Form(default=None),
    db: Session = Depends(get_db)
):

    user, denied = api_guard(request, db, rbac.PHARMACY_ROLE_WRITE)

    if denied is not None:
        return denied

    from src.models.role_permission import RolePermission

    query = db.query(RolePermission)

    if role:
        query = query.filter(RolePermission.role == role.upper())

    removed = query.delete(synchronize_session=False)

    db.commit()

    audit.log_activity(
        db,
        action="pharmacy.role.reset",
        entity_type="role_permission",
        entity_id=role or "all",
        description=(
            f"Removed {removed} override row(s); roles are back to the "
            "defaults in src/security/rbac.py"
        ),
        severity="CRITICAL",
        actor=orders.audit_actor(user),
        request=request,
        commit=True
    )

    return ok_response(removed=removed)


@router.post("/api/users/{user_id}/role")
def set_user_role_api(
    request: Request,
    user_id: int,
    role: str = Form(...),
    is_active: str | None = Form(default=None),
    db: Session = Depends(get_db)
):

    actor_user, denied = api_guard(request, db, rbac.PHARMACY_ROLE_WRITE)

    if denied is not None:
        return denied

    role = (role or "").upper()

    if role not in rbac.ROLES:
        return error_response("Unknown role.", 400)

    target = db.get(User, user_id)

    if target is None:
        return error_response("User not found.", 404)

    before = {
        "role": (target.role or "").upper(),
        "is_active": bool(target.is_active),
    }

    # Nobody but a super user may create or move a super user; and the person
    # in the session can never demote themselves out of a locked door.
    if before["role"] == rbac.ROLE_SUPERUSER or role == rbac.ROLE_SUPERUSER:
        if not rbac.is_superuser(actor_user):
            return error_response(
                "Only a Super User can add or remove a Super User.", 403
            )

    if target.id == actor_user.id and role != rbac.ROLE_SUPERUSER:
        return error_response(
            "You cannot remove your own Super User role while logged in as it.",
            400
        )

    target.role = role

    if is_active is not None and target.id != actor_user.id:
        target.is_active = bool(is_active)

    db.commit()

    audit.log_activity(
        db,
        action="pharmacy.user.role",
        entity_type="user",
        entity_id=target.id,
        description=f"{target.name}: role {before['role']} -> {role}",
        severity="CRITICAL",
        before=before,
        after={"role": role, "is_active": bool(target.is_active)},
        actor=orders.audit_actor(actor_user),
        request=request,
        rollback_available=True,
        commit=True
    )

    return ok_response(
        user_id=target.id,
        role=role,
        is_active=bool(target.is_active)
    )


# =========================================================
# SNAPSHOTS / ROLLBACK
# =========================================================

@router.get("/api/snapshots")
def snapshots_api(
    request: Request,
    db: Session = Depends(get_db)
):

    user, denied = api_guard(request, db, rbac.PHARMACY_SNAPSHOT_CREATE)

    if denied is not None:
        return denied

    return ok_response(
        snapshots=[
            snapshot_service.snapshot_to_dict(row)
            for row in snapshot_service.list_snapshots(db, limit=50)
        ]
    )


@router.post("/api/snapshots")
def create_snapshot_api(
    request: Request,
    label: str | None = Form(default=None),
    description: str | None = Form(default=None),
    scope: str = Form(default="PHARMACY"),
    pin: str | None = Form(default=None),
    db: Session = Depends(get_db)
):

    user, denied = api_guard(request, db, rbac.PHARMACY_SNAPSHOT_CREATE)

    if denied is not None:
        return denied

    try:
        snapshot = snapshot_service.create_snapshot(
            db,
            label=label,
            description=description,
            scope=scope,
            actor=orders.audit_actor(user),
            trigger="MANUAL",
            is_pinned=bool(pin),
            request=request
        )
    except Exception as error:  # noqa: BLE001
        logger.exception("snapshot create failed")
        db.rollback()
        return error_response(f"Snapshot failed: {error}", 500)

    return ok_response(
        snapshot=snapshot_service.snapshot_to_dict(snapshot),
        message=f"Snapshot #{snapshot.id} saved."
    )


@router.get("/api/snapshots/{snapshot_id}/preview")
def preview_snapshot_api(
    request: Request,
    snapshot_id: int,
    db: Session = Depends(get_db)
):

    user, denied = api_guard(request, db, rbac.PHARMACY_SNAPSHOT_RESTORE)

    if denied is not None:
        return denied

    snapshot = snapshot_service.get_snapshot(db, snapshot_id)

    if snapshot is None:
        return error_response("Snapshot not found.", 404)

    try:
        preview = snapshot_service.preview_restore(db, snapshot)
    except Exception:  # noqa: BLE001
        logger.exception("snapshot preview failed")
        db.rollback()
        return error_response("Could not read that snapshot.", 500)

    return ok_response(preview=preview)


@router.get("/api/snapshots/{snapshot_id}/export.json")
def export_snapshot_api(
    request: Request,
    snapshot_id: int,
    db: Session = Depends(get_db)
):

    user, denied = api_guard(request, db, rbac.PHARMACY_SNAPSHOT_CREATE)

    if denied is not None:
        return denied

    snapshot = snapshot_service.get_snapshot(db, snapshot_id)

    if snapshot is None:
        return error_response("Snapshot not found.", 404)

    return Response(
        content=snapshot_service.export_snapshot_json(snapshot),
        media_type="application/json",
        headers={
            "Content-Disposition": (
                f'attachment; filename="pharmacy_snapshot_{snapshot.id}.json"'
            )
        }
    )


@router.post("/api/snapshots/{snapshot_id}/restore")
def restore_snapshot_api(
    request: Request,
    snapshot_id: int,
    checksum: str = Form(...),
    db: Session = Depends(get_db)
):
    """Roll the pharmacy tables back to a snapshot.

    The checksum must match exactly (the preview hands it to the page), and an
    automatic PRE_RESTORE snapshot of the current state is taken first, so the
    restore can itself be undone.
    """

    user, denied = api_guard(request, db, rbac.PHARMACY_SNAPSHOT_RESTORE)

    if denied is not None:
        return denied

    snapshot = snapshot_service.get_snapshot(db, snapshot_id)

    if snapshot is None:
        return error_response("Snapshot not found.", 404)

    try:
        result = snapshot_service.restore_snapshot(
            db,
            snapshot,
            checksum=checksum,
            actor=orders.audit_actor(user),
            request=request
        )
    except ValueError as error:
        return error_response(str(error), 409)
    except Exception:  # noqa: BLE001
        logger.exception("snapshot restore failed")
        db.rollback()
        return error_response(
            "Restore failed and the transaction was rolled back - the live "
            "data was not changed.",
            500
        )

    return ok_response(
        **result,
        message=(
            f"Restored '{snapshot.label}'. If that was the wrong snapshot, "
            f"restore the undo point #{result['undo_snapshot_id']}."
        )
    )


@router.post("/api/snapshots/{snapshot_id}/pin")
def pin_snapshot_api(
    request: Request,
    snapshot_id: int,
    db: Session = Depends(get_db)
):

    user, denied = api_guard(request, db, rbac.PHARMACY_SNAPSHOT_CREATE)

    if denied is not None:
        return denied

    snapshot = snapshot_service.get_snapshot(db, snapshot_id)

    if snapshot is None:
        return error_response("Snapshot not found.", 404)

    snapshot.is_pinned = not snapshot.is_pinned

    audit.log_activity(
        db,
        action="pharmacy.snapshot.pin",
        entity_type="snapshot",
        entity_id=snapshot.id,
        description=f"Snapshot #{snapshot.id} {'pinned' if snapshot.is_pinned else 'unpinned'}",
        actor=orders.audit_actor(user),
        request=request,
        commit=True
    )

    db.commit()

    return ok_response(is_pinned=bool(snapshot.is_pinned))


@router.delete("/api/snapshots/{snapshot_id}")
def delete_snapshot_api(
    request: Request,
    snapshot_id: int,
    db: Session = Depends(get_db)
):

    user, denied = api_guard(request, db, rbac.PHARMACY_SNAPSHOT_RESTORE)

    if denied is not None:
        return denied

    snapshot = snapshot_service.get_snapshot(db, snapshot_id)

    if snapshot is None:
        return error_response("Snapshot not found.", 404)

    try:
        snapshot_service.delete_snapshot(
            db,
            snapshot,
            actor=orders.audit_actor(user),
            request=request
        )
    except ValueError as error:
        return error_response(str(error), 409)

    return ok_response(deleted=True)


@router.post("/api/snapshots/prune")
def prune_snapshots_api(
    request: Request,
    keep: int = Form(default=20),
    db: Session = Depends(get_db)
):

    user, denied = api_guard(request, db, rbac.PHARMACY_SNAPSHOT_RESTORE)

    if denied is not None:
        return denied

    result = snapshot_service.prune(
        db,
        keep=max(1, keep),
        older_than_days=7,
        actor=orders.audit_actor(user),
        request=request
    )

    return ok_response(**result)