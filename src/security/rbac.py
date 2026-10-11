"""Role based access control for the pharmacy module.

The rest of the project stores ``users.role`` but never checks it, so anyone
who knew a URL could reach any page. This module is the single place where
"who may do what" is decided, and every pharmacy / pharmacy-admin route goes
through it.

Three ways to use it
--------------------
1. JSON endpoints (FastAPI dependency)::

       @router.post("/medicines")
       def create(user: User = Depends(require_permission(PHARMACY_CATALOG_WRITE))):
           ...

   Missing login  -> 401 ``{"success": false, "message": "Please login first."}``
   Wrong role     -> 403 with the permission name in the response.

2. HTML pages (must redirect, not return JSON)::

       user, redirect = guard_page(request, db, PHARMACY_VIEW)
       if redirect:
           return redirect

3. Inside a service / template, when you only need to dim a button::

       if has_permission(db, user, PHARMACY_ORDER_REFUND):
           ...

SUPERUSER always has everything (``*``). The permission matrix can be changed
at runtime from the admin screen - that writes ``role_permissions`` rows which
override these defaults, so no redeploy is needed to grant or freeze a role.
"""

from fastapi import (
    Depends,
    HTTPException,
    Request
)

from fastapi.responses import RedirectResponse

from sqlalchemy.orm import Session

from src.database.connection import get_db
from src.models.user import User


# =========================================================
# ROLES
# =========================================================

ROLE_PATIENT = "PATIENT"
ROLE_DOCTOR = "DOCTOR"
ROLE_PHARMACIST = "PHARMACIST"
ROLE_STAFF = "STAFF"
ROLE_ADMIN = "ADMIN"
ROLE_SUPERUSER = "SUPERUSER"

ROLES = [
    ROLE_PATIENT,
    ROLE_DOCTOR,
    ROLE_PHARMACIST,
    ROLE_STAFF,
    ROLE_ADMIN,
    ROLE_SUPERUSER,
]

ROLE_LABELS = {
    ROLE_PATIENT: "Patient",
    ROLE_DOCTOR: "Doctor",
    ROLE_PHARMACIST: "Pharmacist",
    ROLE_STAFF: "Clinic staff",
    ROLE_ADMIN: "Admin",
    ROLE_SUPERUSER: "Super User",
}


# =========================================================
# PERMISSION KEYS
# =========================================================

PHARMACY_VIEW = "pharmacy.view"
PHARMACY_CART_MANAGE = "pharmacy.cart.manage"
PHARMACY_ORDER_OWN = "pharmacy.order.own"
PHARMACY_ORDER_CANCEL_OWN = "pharmacy.order.cancel.own"
PHARMACY_NEARBY_SEARCH = "pharmacy.nearby.search"
PHARMACY_PRESCRIPTION_BUY = "pharmacy.prescription.buy"

PHARMACY_ORDER_READ_ALL = "pharmacy.order.read.all"
PHARMACY_ORDER_FULFIL = "pharmacy.order.fulfil"
PHARMACY_ORDER_REFUND = "pharmacy.order.refund"
PHARMACY_CATALOG_READ = "pharmacy.catalog.read"
PHARMACY_CATALOG_WRITE = "pharmacy.catalog.write"
PHARMACY_STOCK_WRITE = "pharmacy.stock.write"
PHARMACY_NEARBY_WRITE = "pharmacy.nearby.write"
PHARMACY_AUDIT_READ = "pharmacy.audit.read"
PHARMACY_SNAPSHOT_CREATE = "pharmacy.snapshot.create"
PHARMACY_SNAPSHOT_RESTORE = "pharmacy.snapshot.restore"
PHARMACY_ROLE_WRITE = "pharmacy.role.write"

# Doctor desk - a doctor's own patient file. ``doctor.patients.all`` is what
# makes "any enrolled patient, not only the ones with an appointment here"
# possible; take it away from a role and that role only sees its own patients.
DOCTOR_DESK_READ = "doctor.desk.read"
DOCTOR_RECORD_WRITE = "doctor.record.write"
DOCTOR_PRESCRIBE_WRITE = "doctor.prescribe.write"
DOCTOR_NOTE_WRITE = "doctor.note.write"
DOCTOR_BILLING_READ = "doctor.billing.read"
DOCTOR_BILLING_WRITE = "doctor.billing.write"
DOCTOR_PATIENTS_ALL = "doctor.patients.all"

PERMISSIONS = [
    (PHARMACY_VIEW, "Open the pharmacy pages", "Patient side"),
    (PHARMACY_CART_MANAGE, "Add / remove cart items", "Patient side"),
    (PHARMACY_ORDER_OWN, "Place an order for own account", "Patient side"),
    (PHARMACY_ORDER_CANCEL_OWN, "Cancel own pending order", "Patient side"),
    (PHARMACY_NEARBY_SEARCH, "Emergency 'find it nearby' search", "Patient side"),
    (PHARMACY_PRESCRIPTION_BUY, "Buy tablets a doctor prescribed", "Patient side"),

    (PHARMACY_ORDER_READ_ALL, "See every patient order", "Pharmacy counter"),
    (PHARMACY_ORDER_FULFIL, "Mark order paid / handed over", "Pharmacy counter"),
    (PHARMACY_ORDER_REFUND, "Cancel or refund an order", "Pharmacy counter"),
    (PHARMACY_CATALOG_READ, "See catalog incl. cost/stock", "Catalog"),
    (PHARMACY_CATALOG_WRITE, "Add / edit / delete medicines", "Catalog"),
    (PHARMACY_STOCK_WRITE, "Change stock quantities", "Catalog"),
    (PHARMACY_NEARBY_WRITE, "Maintain partner shops + their stock", "Nearby"),
    (PHARMACY_AUDIT_READ, "Read the audit trail", "Governance"),
    (PHARMACY_SNAPSHOT_CREATE, "Take a snapshot", "Governance"),
    (PHARMACY_SNAPSHOT_RESTORE, "Roll back to a snapshot", "Governance"),
    (PHARMACY_ROLE_WRITE, "Change who is allowed to do what", "Governance"),

    (DOCTOR_DESK_READ, "Open the doctor desk (patient list + files)", "Doctor desk"),
    (DOCTOR_RECORD_WRITE, "Write / update a patient's medical record", "Doctor desk"),
    (DOCTOR_PRESCRIBE_WRITE, "Issue a prescription to a patient", "Doctor desk"),
    (DOCTOR_NOTE_WRITE, "Keep notes on a patient file", "Doctor desk"),
    (DOCTOR_BILLING_READ, "See a patient's payments and invoices", "Doctor desk"),
    (DOCTOR_BILLING_WRITE, "Record / refund an appointment payment", "Doctor desk"),
    (DOCTOR_PATIENTS_ALL, "Reach every enrolled patient, not only own", "Doctor desk"),
]


# =========================================================
# DEFAULT MATRIX
# =========================================================

_ALLOW_ALL = "*"

DEFAULT_ROLE_PERMISSIONS: dict[str, object] = {
    ROLE_PATIENT: [
        PHARMACY_VIEW,
        PHARMACY_CART_MANAGE,
        PHARMACY_ORDER_OWN,
        PHARMACY_ORDER_CANCEL_OWN,
        PHARMACY_NEARBY_SEARCH,
        PHARMACY_PRESCRIPTION_BUY,
    ],
    ROLE_DOCTOR: [
        PHARMACY_VIEW,
        PHARMACY_CATALOG_READ,
        DOCTOR_DESK_READ,
        DOCTOR_RECORD_WRITE,
        DOCTOR_PRESCRIBE_WRITE,
        DOCTOR_NOTE_WRITE,
        DOCTOR_BILLING_READ,
        DOCTOR_BILLING_WRITE,
        DOCTOR_PATIENTS_ALL,
    ],
    ROLE_PHARMACIST: [
        PHARMACY_VIEW,
        PHARMACY_CATALOG_READ,
        PHARMACY_ORDER_READ_ALL,
        PHARMACY_ORDER_FULFIL,
        PHARMACY_STOCK_WRITE,
        PHARMACY_NEARBY_WRITE,
    ],
    ROLE_STAFF: [
        PHARMACY_VIEW,
        PHARMACY_ORDER_READ_ALL,
        PHARMACY_ORDER_FULFIL,
        PHARMACY_NEARBY_WRITE,
    ],
    ROLE_ADMIN: [
        PHARMACY_VIEW,
        PHARMACY_CATALOG_READ,
        PHARMACY_CATALOG_WRITE,
        PHARMACY_STOCK_WRITE,
        PHARMACY_NEARBY_WRITE,
        PHARMACY_ORDER_READ_ALL,
        PHARMACY_ORDER_FULFIL,
        PHARMACY_ORDER_REFUND,
        PHARMACY_AUDIT_READ,
        PHARMACY_SNAPSHOT_CREATE,
        PHARMACY_SNAPSHOT_RESTORE,
        DOCTOR_DESK_READ,
        DOCTOR_RECORD_WRITE,
        DOCTOR_PRESCRIBE_WRITE,
        DOCTOR_NOTE_WRITE,
        DOCTOR_BILLING_READ,
        DOCTOR_BILLING_WRITE,
        DOCTOR_PATIENTS_ALL,
    ],
    # Everything, including editing roles. Never removable.
    ROLE_SUPERUSER: _ALLOW_ALL,
}


# =========================================================
# CURRENT USER
# =========================================================

def session_user_id(request: Request) -> int | None:
    try:
        return request.session.get("user_id")
    except AttributeError:  # pragma: no cover - session middleware missing
        return None


def get_session_user(
    request: Request,
    db: Session
) -> User | None:
    """Load the logged in user from the DB (never trust the session copy)."""

    user_id = session_user_id(request)

    if user_id is None:
        return None

    return (
        db.query(User)
        .filter(User.id == user_id)
        .first()
    )


def user_role(user: User | None) -> str:
    return (getattr(user, "role", None) or ROLE_PATIENT).upper()


def is_superuser(user: User | None) -> bool:
    return user_role(user) == ROLE_SUPERUSER


# =========================================================
# PERMISSION LOOKUP (DB overrides on top of the defaults)
# =========================================================

def role_permission_rows(db: Session) -> dict[tuple[str, str], bool]:
    from src.models.role_permission import RolePermission

    overrides: dict[tuple[str, str], bool] = {}

    try:
        rows = db.query(RolePermission).all()
    except Exception:  # table not created yet (brand new database)
        db.rollback()
        return overrides

    for row in rows:
        overrides[(row.role.upper(), row.permission)] = bool(row.is_allowed)

    return overrides


def role_has_default(role: str, permission: str) -> bool:
    allowed = DEFAULT_ROLE_PERMISSIONS.get(role, [])

    if allowed == _ALLOW_ALL:
        return True

    return permission in allowed


def has_permission(
    db: Session,
    user: User | None,
    permission: str
) -> bool:
    """True if `user` may do `permission`."""

    if user is None:
        return False

    if not getattr(user, "is_active", True):
        return False

    role = user_role(user)

    # A super user can never be locked out of the pharmacy module.
    if role == ROLE_SUPERUSER:
        return True

    overrides = role_permission_rows(db)

    override = overrides.get((role, permission))

    if override is not None:
        return override

    if role_has_default(role, permission):
        return True

    # Wildcard row, e.g. role allowed "pharmacy.*"
    prefix = permission.rsplit(".", 1)[0] + ".*"

    wildcard = overrides.get((role, prefix))

    if wildcard is not None:
        return wildcard

    return False


def effective_permissions(
    db: Session,
    role: str
) -> dict[str, bool]:
    """{permission: True/False} for one role, defaults + overrides applied."""

    role = (role or "").upper()
    overrides = role_permission_rows(db)
    result: dict[str, bool] = {}

    for key, _label, _group in PERMISSIONS:
        if role == ROLE_SUPERUSER:
            result[key] = True
            continue

        override = overrides.get((role, key))

        if override is not None:
            result[key] = override
            continue

        wildcard = overrides.get((role, key.rsplit(".", 1)[0] + ".*"))

        if wildcard is not None:
            result[key] = wildcard
            continue

        result[key] = role_has_default(role, key)

    return result


# =========================================================
# FASTAPI DEPENDENCIES (JSON endpoints)
# =========================================================

def require_login():
    def dependency(
        request: Request,
        db: Session = Depends(get_db)
    ) -> User:

        user = get_session_user(request, db)

        if user is None:
            raise HTTPException(
                status_code=401,
                detail={
                    "success": False,
                    "message": "Please login first.",
                    "login_url": "/login"
                }
            )

        return user

    return dependency


def require_permission(permission: str):
    """Dependency that resolves to the logged in User, or 401/403."""

    def dependency(
        request: Request,
        db: Session = Depends(get_db)
    ) -> User:

        user = get_session_user(request, db)

        if user is None:
            raise HTTPException(
                status_code=401,
                detail={
                    "success": False,
                    "message": "Please login first.",
                    "login_url": "/login"
                }
            )

        if not has_permission(db, user, permission):
            raise HTTPException(
                status_code=403,
                detail={
                    "success": False,
                    "message": (
                        f"Your role ({ROLE_LABELS.get(user_role(user), user_role(user))}) "
                        "is not allowed to do this."
                    ),
                    "required_permission": permission
                }
            )

        return user

    return dependency


def optional_user(
    request: Request,
    db: Session = Depends(get_db)
) -> User | None:
    return get_session_user(request, db)


# =========================================================
# HTML PAGE GUARDS
# =========================================================

def guard_page(
    request: Request,
    db: Session,
    permission: str | None = None,
    login_required: bool = True
) -> tuple[User | None, RedirectResponse | None]:
    """Return ``(user, redirect)``. If ``redirect`` is not None -> return it.

    Kept deliberately simple so it works in any FastAPI HTML route.
    """

    user = get_session_user(request, db)

    if login_required and user is None:
        next_path = request.url.path
        if request.url.query:
            next_path = f"{next_path}?{request.url.query}"
        return None, RedirectResponse(
            url=f"/login?next={next_path}",
            status_code=303
        )

    if user is not None and not user.is_active:
        return None, RedirectResponse(url="/login", status_code=303)

    # A guest is only stopped when the page needs a login (above) or when a
    # user IS logged in but their role lost this permission. Anonymous
    # browsing is intentionally allowed on the shop / nearby pages, so a
    # patient can compare prices before signing in - buying still needs a
    # session, because the cart is stored per user.
    if (
        permission is not None
        and user is not None
        and not has_permission(db, user, permission)
    ):
        return None, RedirectResponse(url="/dashboard", status_code=303)

    return user, None


def actor_of(user: User | None) -> dict:
    """Small dict the audit logger wants."""

    if user is None:
        return {
            "user_id": None,
            "name": "Anonymous",
            "role": "GUEST",
        }

    return {
        "user_id": user.id,
        "name": user.name,
        "role": user_role(user),
    }
