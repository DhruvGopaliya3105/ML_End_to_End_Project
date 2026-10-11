"""Doctor desk routes - ``/doctor-desk``.

A doctor signs in with the same login form as a patient and lands here
(``src/routers/auth.py`` sends the DOCTOR role to this page). The roster is
live, every number on it comes from a query, and the patient file has both the
reading side (visits, records, prescriptions, medicines, invoices, reviews)
and the writing side (notes, consultation record, prescription, follow-up,
appointment payment).

Two guards on purpose:

* a page guard   -> ``rbac.guard_page`` so a role without ``doctor.desk.read``
  is bounced to /dashboard instead of seeing a JSON error
* a per-patient check -> ``visible_patient_ids`` so a doctor that lost
  ``doctor.patients.all`` cannot even open a file it is not on

Every write is audited by the service; every file open is logged too.
"""

from __future__ import annotations

import datetime as dt
import logging

from fastapi import (
    APIRouter,
    Depends,
    Form,
    Query,
    Request
)

from fastapi.encoders import jsonable_encoder

from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    RedirectResponse
)

from sqlalchemy.orm import Session

from src.database.connection import get_db
from src.security import rbac
from src.services import doctor_desk_service as desk
from src.routers.pharmacy import (
    _templates,
    base_context,
    error_response,
    ok_response,
    parse_int
)


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/doctor-desk",
    tags=["Doctor Desk"]
)

TABS = [
    ("overview", "Overview"),
    ("visits", "Visits & payments"),
    ("records", "Consultation notes"),
    ("prescriptions", "Prescriptions"),
    ("medicines", "Medicines taken"),
    ("billing", "Full invoice"),
    ("notes", "Doctor notes"),
    ("reviews", "Patient reviews"),
    ("documents", "Reports"),
    ("timeline", "Timeline"),
]

TAB_KEYS = {key for key, _label in TABS}


# ==========================================================================
# helpers
# ==========================================================================

def _flash(request: Request) -> str:
    return (request.query_params.get("msg") or "").strip()[:200]


def _quote(text: str) -> str:
    """Messages go into a redirect URL, so keep them URL friendly."""

    from urllib.parse import quote

    return quote((text or "")[:180])


def _back(request: Request, patient_id: int, tab: str) -> RedirectResponse:
    return RedirectResponse(
        url=f"/doctor-desk/patient/{patient_id}?tab={tab}",
        status_code=303
    )


def _desk_context(
    request: Request,
    db: Session,
    user,
    **extra
) -> dict:

    from src.routers.pharmacy import user_dict

    context = base_context(request, db, user, **extra)

    context["active_nav"] = "doctor_desk"
    context["cart_count"] = 0          # the desk is not a shop
    context["cart_subtotal"] = 0.0
    context["flash"] = _flash(request)
    context["tiles"] = desk.desk_tiles(db, user)
    context["me"] = user_dict(user)
    context["today"] = dt.date.today().strftime("%d %b %Y")
    _hour = dt.datetime.now().hour
    context["greeting"] = (
        "Good Morning" if _hour < 12
        else "Good Afternoon" if _hour < 17
        else "Good Evening"
    )
    context["today_iso"] = dt.date.today().isoformat()
    context["can_write"] = rbac.has_permission(db, user, rbac.DOCTOR_NOTE_WRITE)
    context["can_record"] = rbac.has_permission(db, user, rbac.DOCTOR_RECORD_WRITE)
    context["can_prescribe"] = rbac.has_permission(db, user, rbac.DOCTOR_PRESCRIBE_WRITE)
    context["can_bill"] = rbac.has_permission(db, user, rbac.DOCTOR_BILLING_WRITE)
    context["sees_all"] = desk.may_reach_everyone(db, user)

    return context


def _open_patient(
    request: Request,
    db: Session,
    patient_id: int,
    permission: str | None = None
) -> tuple[object | None, dict | None, object | None]:
    """Returns ``(user, context, redirect)``; follow ``redirect`` if set."""

    user, redirect = rbac.guard_page(request, db, rbac.DOCTOR_DESK_READ)

    if redirect is not None:
        return None, None, redirect

    target = desk.patient_profile(db, patient_id)

    if target is None:
        return user, None, RedirectResponse(
            url="/doctor-desk?msg=No+such+patient", status_code=303
        )

    doctor_row = desk.resolve_doctor_row(db, user)
    allowed = desk.visible_patient_ids(db, user, doctor_row)

    if allowed is not None and patient_id not in allowed:
        return user, None, RedirectResponse(
            url="/doctor-desk?msg=That+file+is+not+in+your+scope",
            status_code=303
        )

    if permission is not None and not rbac.has_permission(db, user, permission):
        return user, None, RedirectResponse(
            url=f"/doctor-desk/patient/{patient_id}?tab=overview"
                "&msg=Your+role+cannot+do+that+here",
            status_code=303
        )

    context = _desk_context(request, db, user)
    context["patient"] = target
    context["patient_id"] = patient_id

    return user, context, None


def _wants_json(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    return "application/json" in accept and "text/html" not in accept


def _parse_date(raw: str | None) -> dt.date | None:
    raw = (raw or "").strip()

    if not raw:
        return None

    for pattern in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return dt.datetime.strptime(raw, pattern).date()
        except ValueError:
            continue

    return None


# ==========================================================================
# the roster
# ==========================================================================

@router.get(
    "",
    response_class=HTMLResponse
)
@router.get(
    "/",
    response_class=HTMLResponse,
    include_in_schema=False
)
def desk_page(
    request: Request,
    q: str | None = Query(None, max_length=80),
    scope: str = Query("all", max_length=20),
    sort: str = Query("last_visit", max_length=20),
    direction: str = Query("desc", max_length=10),
    page: int = Query(1, ge=1, le=500),
    per_page: int = Query(15, ge=5, le=100),
    db: Session = Depends(get_db)
):

    user, redirect = rbac.guard_page(request, db, rbac.DOCTOR_DESK_READ)

    if redirect is not None:
        return redirect

    if scope not in desk.SCOPE_KEYS:
        scope = "all"

    if sort not in desk.SORTS:
        sort = "last_visit"

    rows, meta = desk.list_patients(
        db,
        user,
        search=q,
        scope=scope,
        sort=sort,
        direction="asc" if direction == "asc" else "desc",
        page=page,
        per_page=per_page
    )

    context = _desk_context(
        request,
        db,
        user,
        rows=rows,
        meta=meta,
        q=q or "",
        scope=scope,
        sort=sort,
        direction="asc" if direction == "asc" else "desc",
        title="Doctor Desk"
    )

    return _templates(request).TemplateResponse(
        request,
        "doctor_desk.html",
        context
    )


@router.get("/api/patients")
def api_patients(
    request: Request,
    q: str | None = Query(None, max_length=80),
    scope: str = Query("all", max_length=20),
    sort: str = Query("last_visit", max_length=20),
    db: Session = Depends(get_db)
):

    user, redirect = rbac.guard_page(
        request, db, rbac.DOCTOR_DESK_READ, login_required=True
    )

    if redirect is not None:
        return error_response("Please login first.", 401)

    rows, meta = desk.list_patients(
        db,
        user,
        search=q,
        scope=scope if scope in desk.SCOPE_KEYS else "all",
        sort=sort if sort in desk.SORTS else "last_visit",
        page=1,
        per_page=25
    )

    return ok_response(
        rows=[
            {
                "id": row["id"],
                "patient_no": row["patient_no"],
                "name": row["name"],
                "email": row["email"],
                "tags": [tag[0] for tag in row["tags"]],
                "visits": row["stats"]["visits"],
                "last_visit": (
                    row["stats"]["last_visit"].strftime("%d %b %Y")
                    if row["stats"]["last_visit"] else None
                ),
                "due": row["stats"]["due"],
            }
            for row in rows
        ],
        total=meta["total"]
    )


@router.get("/api/summary")
def api_summary(
    request: Request,
    db: Session = Depends(get_db)
):

    user, redirect = rbac.guard_page(request, db, rbac.DOCTOR_DESK_READ)

    if redirect is not None:
        return error_response("Please login first.", 401)

    return ok_response(**desk.desk_tiles(db, user))


# ==========================================================================
# one patient file
# ==========================================================================

@router.get(
    "/patient/{patient_id}",
    response_class=HTMLResponse
)
def patient_page(
    patient_id: int,
    request: Request,
    tab: str = Query("overview", max_length=20),
    db: Session = Depends(get_db)
):

    user, context, redirect = _open_patient(request, db, patient_id)

    if redirect is not None:
        return redirect

    # context is never None here: _open_patient redirects on a missing id

    if tab not in TAB_KEYS:
        tab = "overview"

    show_billing = rbac.has_permission(db, user, rbac.DOCTOR_BILLING_READ)

    data = desk.dossier(
        db,
        patient_id,
        actor=user,
        show_billing=show_billing
    ) or {}

    desk.log_desk_view(
        db,
        actor=user,
        patient_id=patient_id,
        view=tab,
        request=request
    )

    context.update(data)
    context["rows"] = []
    context["meta"] = desk.desk_tiles(db, user)
    context["tab"] = tab
    context["tabs"] = [
        {"key": key, "label": label}
        for key, label in TABS
        if show_billing or key not in ("billing", "visits")
    ]
    context["show_billing"] = show_billing
    context["title"] = f"Patient file - {context['patient']['name']}"

    return _templates(request).TemplateResponse(
        request,
        "doctor_patient.html",
        context
    )


@router.get("/patient/{patient_id}/api/file")
def api_patient_file(
    patient_id: int,
    request: Request,
    db: Session = Depends(get_db)
):

    user, _context, redirect = _open_patient(request, db, patient_id)

    if redirect is not None:
        return error_response("Not allowed.", 403)

    data = desk.dossier(db, patient_id, actor=user) or {}

    data.pop("timeline", None)

    # dates / Decimals in the stats blocks need the same encoder FastAPI uses
    return ok_response(**jsonable_encoder(data))


# ==========================================================================
# notes
# ==========================================================================

@router.post("/patient/{patient_id}/notes")
def add_note(
    patient_id: int,
    request: Request,
    title: str = Form(..., max_length=200),
    body: str | None = Form(None, max_length=4000),
    note_type: str = Form("NOTE", max_length=20),
    visibility: str = Form("DOCTOR_ONLY", max_length=20),
    pinned: str | None = Form(None),
    urgent: str | None = Form(None),
    follow_up_date: str | None = Form(None, max_length=20),
    db: Session = Depends(get_db)
):

    user, context, redirect = _open_patient(
        request, db, patient_id, rbac.DOCTOR_NOTE_WRITE
    )

    if redirect is not None:
        return redirect

    doctor_row = desk.resolve_doctor_row(db, user)

    try:
        note = desk.add_note(
            db,
            patient_id=patient_id,
            author=user,
            doctor_row=doctor_row,
            title=title,
            body=body,
            note_type=note_type,
            visibility=visibility,
            is_pinned=bool(pinned),
            is_urgent=bool(urgent),
            follow_up_date=_parse_date(follow_up_date),
            request=request
        )
    except ValueError as exc:
        if _wants_json(request):
            return error_response(str(exc))
        return RedirectResponse(
            url=f"/doctor-desk/patient/{patient_id}?tab=notes&msg={_quote(str(exc))}",
            status_code=303
        )

    if _wants_json(request):
        return ok_response(id=note.id, title=note.title)

    return _back(request, patient_id, "notes")


@router.post("/notes/{note_id}/flag")
def flag_note(
    note_id: int,
    request: Request,
    field: str = Form(..., max_length=20),
    db: Session = Depends(get_db)
):

    user, redirect = rbac.guard_page(request, db, rbac.DOCTOR_NOTE_WRITE)

    if redirect is not None:
        return redirect

    allowed = desk.visible_patient_ids(
        db, user, desk.resolve_doctor_row(db, user)
    )

    note_row = db.get(desk.DoctorPatientNote, note_id)

    if note_row is None:
        return error_response("That note is gone.", 404)

    if allowed is not None and note_row.patient_id not in allowed:
        return error_response("That file is not in your scope.", 403)

    mapping = {
        "pinned": "is_pinned",
        "urgent": "is_urgent",
        "archive": "status",
    }

    target = mapping.get(field)

    if target is None:
        return error_response("Use pinned, urgent or archive.")

    try:
        result = desk.set_note_flag(
            db,
            note_id,
            field=target,
            actor=user,
            request=request
        )
    except ValueError as exc:
        return error_response(str(exc))

    if _wants_json(request):
        return ok_response(**result)

    return RedirectResponse(
        url=f"/doctor-desk/patient/{note_row.patient_id}?tab=notes",
        status_code=303
    )


@router.post("/notes/{note_id}/restore")
def restore_note(
    note_id: int,
    request: Request,
    db: Session = Depends(get_db)
):

    user, redirect = rbac.guard_page(request, db, rbac.DOCTOR_NOTE_WRITE)

    if redirect is not None:
        return redirect

    note_row = db.get(desk.DoctorPatientNote, note_id)

    if note_row is None:
        return error_response("That note is gone.", 404)

    try:
        desk.set_note_flag(
            db,
            note_id,
            field="status",
            actor=user,
            request=request
        )
    except ValueError as exc:
        return error_response(str(exc))

    return RedirectResponse(
        url=f"/doctor-desk/patient/{note_row.patient_id}?tab=notes",
        status_code=303
    )


# ==========================================================================
# consultation record + follow-up
# ==========================================================================

@router.post("/patient/{patient_id}/record")
def write_record(
    patient_id: int,
    request: Request,
    visit_date: str | None = Form(None, max_length=20),
    chief_complaint: str | None = Form(None, max_length=300),
    symptoms: str | None = Form(None, max_length=4000),
    clinical_notes: str | None = Form(None, max_length=4000),
    diagnosis: str | None = Form(None, max_length=2000),
    treatment_summary: str | None = Form(None, max_length=2000),
    medicines: str | None = Form(None, max_length=2000),
    instructions: str | None = Form(None, max_length=2000),
    status: str = Form("ACTIVE", max_length=20),
    appointment_id: str | None = Form(None, max_length=12),
    db: Session = Depends(get_db)
):

    user, context, redirect = _open_patient(
        request, db, patient_id, rbac.DOCTOR_RECORD_WRITE
    )

    if redirect is not None:
        return redirect

    if not (chief_complaint or symptoms or diagnosis or clinical_notes):
        return RedirectResponse(
            url=f"/doctor-desk/patient/{patient_id}?tab=records&msg="
                + _quote("Write something first"),
            status_code=303
        )

    record = desk.write_record(
        db,
        patient_id=patient_id,
        author=user,
        doctor_row=desk.resolve_doctor_row(db, user),
        visit_date=_parse_date(visit_date),
        chief_complaint=chief_complaint,
        symptoms=symptoms,
        clinical_notes=clinical_notes,
        diagnosis=diagnosis,
        treatment_summary=treatment_summary,
        medicines=medicines,
        instructions=instructions,
        status=status,
        appointment_id=parse_int(appointment_id, 0) or None,
        request=request
    )

    return RedirectResponse(
        url=f"/doctor-desk/patient/{patient_id}?tab=records&msg="
            + _quote(f"Consultation note #{record.id} saved"),
        status_code=303
    )


@router.post("/record/{record_id}/status")
def record_status(
    record_id: int,
    request: Request,
    status: str = Form("COMPLETED", max_length=20),
    db: Session = Depends(get_db)
):

    user, redirect = rbac.guard_page(request, db, rbac.DOCTOR_RECORD_WRITE)

    if redirect is not None:
        return redirect

    try:
        result = desk.update_record_status(
            db,
            record_id,
            status=status,
            actor=user,
            request=request
        )
    except ValueError as exc:
        return error_response(str(exc))

    return ok_response(**result)


@router.post("/patient/{patient_id}/follow-up")
def schedule_follow_up(
    patient_id: int,
    request: Request,
    follow_up_date: str = Form(..., max_length=20),
    reason: str | None = Form(None, max_length=300),
    instructions: str | None = Form(None, max_length=2000),
    medical_record_id: str | None = Form(None, max_length=12),
    db: Session = Depends(get_db)
):

    user, context, redirect = _open_patient(
        request, db, patient_id, rbac.DOCTOR_RECORD_WRITE
    )

    if redirect is not None:
        return redirect

    on_date = _parse_date(follow_up_date)

    if on_date is None:
        return RedirectResponse(
            url=f"/doctor-desk/patient/{patient_id}?tab=records&msg="
                + _quote("Use YYYY-MM-DD for the date"),
            status_code=303
        )

    row = desk.schedule_follow_up(
        db,
        patient_id=patient_id,
        actor=user,
        doctor_row=desk.resolve_doctor_row(db, user),
        on_date=on_date,
        reason=reason,
        instructions=instructions,
        medical_record_id=parse_int(medical_record_id, 0) or None,
        request=request
    )

    return RedirectResponse(
        url=f"/doctor-desk/patient/{patient_id}?tab=records"
            f"&msg=Follow-up+#{row.id}+booked+for+{desk._fmt_date(on_date)}",
        status_code=303
    )


@router.post("/follow-up/{follow_up_id}/complete")
def complete_follow_up(
    follow_up_id: int,
    request: Request,
    db: Session = Depends(get_db)
):

    user, redirect = rbac.guard_page(request, db, rbac.DOCTOR_RECORD_WRITE)

    if redirect is not None:
        return redirect

    try:
        result = desk.complete_follow_up(
            db,
            follow_up_id,
            actor=user,
            request=request
        )
    except ValueError as exc:
        return error_response(str(exc))

    if _wants_json(request):
        return ok_response(**result)

    row = db.get(desk.FollowUp, follow_up_id)

    return RedirectResponse(
        url=f"/doctor-desk/patient/{row.patient_id}?tab=records",
        status_code=303
    )


# ==========================================================================
# prescriptions the doctor writes here
# ==========================================================================

@router.post("/patient/{patient_id}/prescription")
def write_prescription(
    patient_id: int,
    request: Request,
    lines: str = Form(..., max_length=8000),
    diagnosis: str | None = Form(None, max_length=2000),
    instructions: str | None = Form(None, max_length=2000),
    medical_record_id: str | None = Form(None, max_length=12),
    db: Session = Depends(get_db)
):

    user, context, redirect = _open_patient(
        request, db, patient_id, rbac.DOCTOR_PRESCRIBE_WRITE
    )

    if redirect is not None:
        return redirect

    try:
        prescription = desk.write_prescription(
            db,
            patient_id=patient_id,
            author=user,
            doctor_row=desk.resolve_doctor_row(db, user),
            diagnosis=diagnosis,
            instructions=instructions,
            lines_raw=lines,
            medical_record_id=parse_int(medical_record_id, 0) or None,
            request=request
        )
    except ValueError as exc:
        return RedirectResponse(
            url=f"/doctor-desk/patient/{patient_id}?tab=prescriptions&msg="
                + _quote(str(exc)),
            status_code=303
        )

    return RedirectResponse(
        url=f"/doctor-desk/patient/{patient_id}?tab=prescriptions&msg="
        + _quote(f"Prescription #{prescription.id} saved - the patient can buy it now"),
        status_code=303
    )


@router.post("/prescription/{prescription_id}/send-to-cart")
def send_to_cart(
    prescription_id: int,
    request: Request,
    db: Session = Depends(get_db)
):

    user, redirect = rbac.guard_page(request, db, rbac.DOCTOR_PRESCRIBE_WRITE)

    if redirect is not None:
        return redirect

    from src.models.prescription import Prescription

    prescription = db.get(Prescription, prescription_id)

    if prescription is None:
        return error_response("That prescription is gone.", 404)

    allowed = desk.visible_patient_ids(
        db, user, desk.resolve_doctor_row(db, user)
    )

    if allowed is not None and prescription.patient_id not in allowed:
        return error_response("That file is not in your scope.", 403)

    try:
        result = desk.send_prescription_to_cart(
            db,
            prescription_id=prescription_id,
            actor=user,
            request=request
        )
    except ValueError as exc:
        return error_response(str(exc))

    if _wants_json(request):
        return ok_response(**result)

    if result["added"]:
        message = f"{len(result['added'])} item(s) added to {result['patient']}'s cart"
    else:
        message = "Nothing was in stock at the clinic pharmacy to push"

    if result["skipped"]:
        message += f" ({len(result['skipped'])} skipped)"

    return RedirectResponse(
        url=f"/doctor-desk/patient/{prescription.patient_id}"
            f"?tab=prescriptions&msg={_quote(message)}",
        status_code=303
    )


# ==========================================================================
# money
# ==========================================================================

@router.get(
    "/patient/{patient_id}/statement",
    response_class=HTMLResponse
)
def statement_page(
    patient_id: int,
    request: Request,
    db: Session = Depends(get_db)
):

    user, context, redirect = _open_patient(
        request, db, patient_id, rbac.DOCTOR_BILLING_READ
    )

    if redirect is not None:
        return redirect

    profile = desk.patient_profile(db, patient_id) or {}
    billing = desk.ledger(db, patient_id)
    orders = desk.orders_detail(db, patient_id)
    visits_rows = desk.visits(db, patient_id)

    context.update({
        "patient": profile,
        "ledger": billing,
        "orders": {row["order_no"]: row for row in orders},
        "visits_rows": visits_rows,
        "printed_on": dt.datetime.now().strftime("%d %b %Y, %H:%M"),
        "by": rbac.actor_of(user),
        "doctor_row": desk.resolve_doctor_row(db, user),
        "title": f"Statement - {profile.get('name', '')}",
    })

    return _templates(request).TemplateResponse(
        request,
        "doctor_invoice.html",
        context
    )


@router.get(
    "/patient/{patient_id}/invoice/{order_no}",
    response_class=HTMLResponse
)
def order_invoice(
    patient_id: int,
    request: Request,
    order_no: str,
    db: Session = Depends(get_db)
):

    user, context, redirect = _open_patient(
        request, db, patient_id, rbac.DOCTOR_BILLING_READ
    )

    if redirect is not None:
        return redirect

    order = next(
        (
            row for row in desk.orders_detail(db, patient_id)
            if row["order_no"] == order_no or str(row["id"]) == order_no
        ),
        None
    )

    if order is None:
        return _templates(request).TemplateResponse(
            request,
            "doctor_invoice.html",
            {**context, "patient": desk.patient_profile(db, patient_id) or {},
             "ledger": {"lines": [], "totals": {}}, "orders": {},
             "visits_rows": [], "missing": True,
             "printed_on": dt.datetime.now().strftime("%d %b %Y, %H:%M"),
             "by": rbac.actor_of(user), "title": "Order not found"}
        )

    profile = desk.patient_profile(db, patient_id) or {}

    context.update({
        "patient": profile,
        "ledger": {"lines": [], "totals": {}},
        "orders": {order["order_no"]: order},
        "only_order": order,
        "visits_rows": [],
        "printed_on": dt.datetime.now().strftime("%d %b %Y, %H:%M"),
        "by": rbac.actor_of(user),
        "doctor_row": desk.resolve_doctor_row(db, user),
        "title": f"Invoice {order['order_no']}",
    })

    return _templates(request).TemplateResponse(
        request,
        "doctor_invoice.html",
        context
    )


@router.post("/appointment/{appointment_id}/payment")
def appointment_payment(
    appointment_id: int,
    request: Request,
    payment_status: str = Form("PAID", max_length=20),
    amount: str | None = Form(None, max_length=12),
    payment_method: str | None = Form(None, max_length=20),
    note: str | None = Form(None, max_length=500),
    db: Session = Depends(get_db)
):

    user, redirect = rbac.guard_page(request, db, rbac.DOCTOR_BILLING_WRITE)

    if redirect is not None:
        return redirect

    from src.models.appointment import Appointment

    row = db.get(Appointment, appointment_id)

    if row is None:
        return error_response("That appointment is gone.", 404)

    allowed = desk.visible_patient_ids(
        db, user, desk.resolve_doctor_row(db, user)
    )

    if allowed is not None and row.patient_id not in allowed:
        return error_response("That patient is not in your scope.", 403)

    value = None

    if amount not in (None, ""):
        try:
            value = round(float(str(amount).replace(",", "").strip()), 2)
        except ValueError:
            return error_response("Amount must be a number, e.g. 500 or 450.50")

        if value < 0:
            return error_response("Amount cannot be negative.")

    try:
        result = desk.set_appointment_payment(
            db,
            appointment_id,
            status=payment_status,
            actor=user,
            amount=value,
            method=payment_method,
            note=note,
            request=request
        )
    except ValueError as exc:
        return error_response(str(exc))

    if _wants_json(request):
        return ok_response(**result)

    return RedirectResponse(
        url=f"/doctor-desk/patient/{row.patient_id}?tab=visits&msg="
            + _quote(
                f"Payment {result['payment_status']} - "
                f"Rs {result['payment_amount']:.2f}"
            ),
        status_code=303
    )