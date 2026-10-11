"""Doctor desk - one place to see and keep everything about a patient.

What this service assembles (all read-only aggregation except the note /
record / prescription / payment writers at the bottom):

* ``list_patients``      the roster: every enrolled patient with live numbers
                         (visits, first/last visit, dues, follow-ups, notes),
                         search + scope chips + sorting
* ``patient_dossier``    one file: profile, visits, records, treatments,
                         follow-ups, prescriptions with dose/days, reviews,
                         screening history, uploaded reports
* ``ledger``             every rupee: appointment fees + pharmacy orders, with
                         method, status, refund and running totals
* ``medicine_journey``   "which tablet, how many days, from where, when, paid?"
                         - prescription lines merged with what was actually
                         bought at the counter
* ``timeline``           all of the above as one reverse-chronological thread
* notes / record / prescription / follow-up / payment writers, each of which
  writes an audit row (``src/services/pharmacy_audit_service.py``)

Nothing here trusts the caller for scope: ``visible_patient_ids`` is what makes
a role that lost ``doctor.patients.all`` see only its own patients.
"""

from __future__ import annotations

import datetime as dt
import logging
import re
from decimal import Decimal

from sqlalchemy import String
from sqlalchemy import case
from sqlalchemy import func
from sqlalchemy import or_
from sqlalchemy.orm import Session

from src.models.appointment import Appointment
from src.models.doctor import Doctor
from src.models.doctor_patient_note import DoctorPatientNote
from src.models.follow_up import FollowUp
from src.models.medical_record import MedicalRecord
from src.models.patient_document import PatientDocument
from src.models.pharmacy_order import PharmacyOrder
from src.models.pharmacy_order import PharmacyOrderItem
from src.models.prescription import Prescription
from src.models.prescription_medicine import PrescriptionMedicine
from src.models.screening import ScreeningHistory
from src.models.treatment import Treatment
from src.models.treatment_review import TreatmentReview
from src.models.user import User
from src.services import pharmacy_audit_service as audit


logger = logging.getLogger(__name__)

NEW_PATIENT_DAYS = 30
OVERDUE_DAYS = 90

NOTE_TYPES = [
    ("NOTE", "Note"),
    ("ADVISORY", "Advice / diet"),
    ("ALLERGY", "Allergy"),
    ("RED_FLAG", "Red flag"),
    ("PAYMENT", "Billing"),
    ("FOLLOW_UP", "Follow-up"),
    ("VISIT", "Visit summary"),
]

NOTE_TYPE_LABELS = dict(NOTE_TYPES)


# ==========================================================================
# small helpers
# ==========================================================================

def _num(value) -> float:
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _date(value) -> dt.date | None:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return None


def _fmt_date(value) -> str:
    day = _date(value)
    return day.strftime("%d %b %Y") if day else "-"


def _fmt_dt(value) -> str:
    if isinstance(value, dt.datetime):
        return value.strftime("%d %b %Y, %H:%M")
    return _fmt_date(value)


def _days_between(a, b=None) -> int | None:
    first = _date(a)
    second = _date(b) if b is not None else dt.date.today()
    if first is None:
        return None
    return (second - first).days


def _duration_days(text: str | None) -> int:
    """Pull the number of days out of '5 days', '10 d', '2 weeks', '1 month'."""

    if not text:
        return 0

    raw = str(text).lower()

    short = re.search(r"(\d+)\s*(?:day|d)\b", raw)
    if short:
        return int(short.group(1))

    weeks = re.search(r"(\d+)\s*(?:week|wk|w)\b", raw)
    if weeks:
        return int(weeks.group(1)) * 7

    months = re.search(r"(\d+)\s*(?:month|mo)\b", raw)
    if months:
        return int(months.group(1)) * 30

    number = re.match(r"^\s*(\d+)\s*$", raw)
    if number:
        return int(number.group(1))

    return 0


def _money_key(*parts) -> str:
    return "|".join(str(part) for part in parts)


def normalize_name(text: str | None) -> str:
    """Same idea as the pharmacy catalog: lower-case, punctuation dropped."""

    if not text:
        return ""

    out = re.sub(r"[^a-z0-9 ]+", " ", str(text).lower())
    return " ".join(out.split())


# ==========================================================================
# who is looking, and which patients may they open
# ==========================================================================

def resolve_doctor_row(db: Session, user: User | None) -> Doctor | None:
    """Link a login (``users`` row) to the clinic's ``doctors`` row.

    Email first, then name - the demo doctor signs in as
    ``doctor@demo.com`` while the doctors table knows him as
    ``vikram.joshi@sanjeevani.com``, and the file should still find his
    appointments.
    """

    if user is None:
        return None

    row = (
        db.query(Doctor)
        .filter(func.lower(Doctor.email) == (user.email or "").lower())
        .first()
    )

    if row is not None:
        return row

    name = (user.name or "").strip()

    if name:
        row = (
            db.query(Doctor)
            .filter(func.lower(Doctor.name) == name.lower())
            .first()
        )

        if row is not None:
            return row

        # "Dr. Vikram Joshi" vs "Vikram Joshi"
        loose = re.sub(r"^(dr\.?|doctor)\s+", "", name, flags=re.I).lower()

        if loose:
            row = (
                db.query(Doctor)
                .filter(
                    func.lower(
                        func.replace(Doctor.name, "Dr. ", "")
                    ) == loose
                )
                .first()
            )

    return row


def may_reach_everyone(db: Session, user: User | None) -> bool:
    from src.security import rbac

    return rbac.has_permission(db, user, rbac.DOCTOR_PATIENTS_ALL)


def visible_patient_ids(
    db: Session,
    user: User | None,
    doctor_row: Doctor | None
) -> set[int] | None:
    """None = every enrolled patient. Otherwise only this doctor's own."""

    if may_reach_everyone(db, user):
        return None

    own: set[int] = set()
    doctor_id = getattr(doctor_row, "id", None)

    if doctor_id is None:
        return own

    for column, model in (
        (Appointment.doctor_id, Appointment),
        (MedicalRecord.doctor_id, MedicalRecord),
        (Treatment.doctor_id, Treatment),
        (FollowUp.doctor_id, FollowUp),
        (Prescription.doctor_id, Prescription),
        (TreatmentReview.doctor_id, TreatmentReview),
    ):
        own.update(
            value for (value,) in db.query(model.patient_id).filter(
                column == doctor_id,
                model.patient_id.is_not(None)
            ).distinct()
        )

    return own


def _candidate_patients(db: Session):
    """Anyone who is a patient by role, or who has a clinical row."""

    return (
        db.query(User)
        .filter(
            or_(
                func.upper(func.coalesce(User.role, "PATIENT")) == "PATIENT",
                User.id.in_(db.query(MedicalRecord.patient_id)),
                User.id.in_(db.query(Appointment.patient_id)),
                User.id.in_(db.query(PharmacyOrder.user_id)),
            )
        )
    )


# ==========================================================================
# the roster
# ==========================================================================

def aggregate_stats(db: Session, patient_ids: list[int], doctor_id: int | None = None) -> dict[int, dict]:
    """One grouped query per fact instead of N queries per patient."""

    stats = {
        pid: {
            "visits": 0, "upcoming": 0, "first_visit": None, "last_visit": None,
            "records": 0, "rx_lines": 0, "prescriptions": 0, "treatments": 0,
            "active_treatment": 0, "followups_pending": 0, "followup_overdue": 0,
            "next_followup": None, "reviews": 0, "avg_rating": None,
            "notes": 0, "urgent_notes": 0, "documents": 0, "screenings": 0,
            "orders": 0, "order_items": 0, "billed": 0.0, "paid": 0.0,
            "due": 0.0, "refunded": 0.0, "unpaid_orders": 0, "mine": False,
            "days_since_visit": None, "is_new": False,
        }
        for pid in patient_ids
    }

    if not patient_ids:
        return stats

    today = dt.date.today()

    # ---- appointments ----------------------------------------------------
    rows = (
        db.query(
            Appointment.patient_id,
            func.count(Appointment.id),
            func.min(Appointment.appointment_date),
            func.max(Appointment.appointment_date),
            func.sum(
                func.coalesce(Appointment.payment_amount, 0)
            ),
        )
        .filter(Appointment.patient_id.in_(patient_ids))
        .group_by(Appointment.patient_id)
        .all()
    )

    for pid, total, first, last, billed in rows:
        block = stats.get(pid)
        if block is None:
            continue
        block["visits"] = int(total or 0)
        block["first_visit"] = _date(first)
        block["last_visit"] = _date(last)
        block["billed"] += _num(billed)
        block["days_since_visit"] = _days_between(last) if last else None

    upcoming = (
        db.query(Appointment.patient_id, func.count(Appointment.id))
        .filter(
            Appointment.patient_id.in_(patient_ids),
            Appointment.appointment_date >= today,
            Appointment.status.in_(("BOOKED", "CONFIRMED", "PENDING"))
        )
        .group_by(Appointment.patient_id)
        .all()
    )
    for pid, total in upcoming:
        stats[pid]["upcoming"] = int(total or 0)

    if doctor_id is not None:
        for pid, in db.query(Appointment.patient_id).filter(
            Appointment.patient_id.in_(patient_ids),
            Appointment.doctor_id == doctor_id
        ).distinct():
            stats[pid]["mine"] = True

    # ---- money on appointments -----------------------------------------
    money = (
        db.query(
            Appointment.patient_id,
            func.sum(
                case(
                    (
                        func.upper(func.coalesce(Appointment.payment_status, "")) == "PAID",
                        func.coalesce(Appointment.payment_amount, 0)
                    ),
                    else_=0
                )
            ),
            func.sum(
                case(
                    (
                        func.upper(func.coalesce(Appointment.payment_status, "")) != "PAID",
                        func.coalesce(Appointment.payment_amount, 0)
                    ),
                    else_=0
                )
            ),
            func.sum(func.coalesce(Appointment.refund_amount, 0)),
        )
        .filter(Appointment.patient_id.in_(patient_ids))
        .group_by(Appointment.patient_id)
        .all()
    )

    for pid, paid, due, refunded in money:
        block = stats[pid]
        block["paid"] += _num(paid)
        block["due"] += _num(due)
        block["refunded"] += _num(refunded)

    # ---- clinical rows ---------------------------------------------------
    for model, key, extra in (
        (MedicalRecord, "records", None),
        (Prescription, "prescriptions", None),
        (ScreeningHistory, "screenings", None),
        (PatientDocument, "documents", None),
    ):
        found = (
            db.query(model.patient_id, func.count(model.id))
            .filter(model.patient_id.in_(patient_ids))
            .group_by(model.patient_id)
            .all()
        )
        for pid, total in found:
            stats[pid][key] = int(total or 0)

    if doctor_id is not None:
        for pid, in db.query(MedicalRecord.patient_id).filter(
            MedicalRecord.patient_id.in_(patient_ids),
            MedicalRecord.doctor_id == doctor_id
        ).distinct():
            stats[pid]["mine"] = True

    treatments = (
        db.query(
            Treatment.patient_id,
            func.count(Treatment.id),
            func.sum(
                case(
                    (func.upper(func.coalesce(Treatment.status, "")) == "ACTIVE", 1),
                    else_=0
                )
            ),
        )
        .filter(Treatment.patient_id.in_(patient_ids))
        .group_by(Treatment.patient_id)
        .all()
    )
    for pid, total, active in treatments:
        stats[pid]["treatments"] = int(total or 0)
        stats[pid]["active_treatment"] = int(active or 0)

    # ---- follow-ups ------------------------------------------------------
    fu = (
        db.query(
            FollowUp.patient_id,
            func.count(FollowUp.id),
            func.min(FollowUp.follow_up_date),
        )
        .filter(
            FollowUp.patient_id.in_(patient_ids),
            func.upper(func.coalesce(FollowUp.status, "PENDING")) != "COMPLETED"
        )
        .group_by(FollowUp.patient_id)
        .all()
    )
    for pid, total, soonest in fu:
        block = stats[pid]
        block["followups_pending"] = int(total or 0)
        block["next_followup"] = _date(soonest)
        if soonest is not None and _date(soonest) <= today:
            block["followup_overdue"] = int(total or 0)

    # ---- reviews ---------------------------------------------------------
    rev = (
        db.query(
            TreatmentReview.patient_id,
            func.count(TreatmentReview.id),
            func.avg(TreatmentReview.rating),
        )
        .filter(TreatmentReview.patient_id.in_(patient_ids))
        .group_by(TreatmentReview.patient_id)
        .all()
    )
    for pid, total, avg in rev:
        stats[pid]["reviews"] = int(total or 0)
        if avg is not None:
            stats[pid]["avg_rating"] = round(float(avg), 1)

    # ---- notes -----------------------------------------------------------
    notes = (
        db.query(
            DoctorPatientNote.patient_id,
            func.count(DoctorPatientNote.id),
            func.sum(
                case(
                    (DoctorPatientNote.is_urgent.is_(True), 1), else_=0
                )
            ),
        )
        .filter(
            DoctorPatientNote.patient_id.in_(patient_ids),
            DoctorPatientNote.status == "ACTIVE"
        )
        .group_by(DoctorPatientNote.patient_id)
        .all()
    )
    for pid, total, urgent in notes:
        stats[pid]["notes"] = int(total or 0)
        stats[pid]["urgent_notes"] = int(urgent or 0)

    # ---- pharmacy orders -------------------------------------------------
    orders = (
        db.query(
            PharmacyOrder.user_id,
            func.count(PharmacyOrder.id),
            func.sum(PharmacyOrder.total),
            func.sum(
                case(
                    (
                        func.upper(func.coalesce(PharmacyOrder.payment_status, "")) == "PAID",
                        PharmacyOrder.total
                    ),
                    else_=0
                )
            ),
            func.sum(
                case(
                    (
                        func.upper(func.coalesce(PharmacyOrder.payment_status, "")) != "PAID",
                        func.coalesce(PharmacyOrder.total, 0)
                    ),
                    else_=0
                )
            ),
        )
        .filter(
            PharmacyOrder.user_id.in_(patient_ids),
            func.upper(func.coalesce(PharmacyOrder.status, "")) != "CANCELLED"
        )
        .group_by(PharmacyOrder.user_id)
        .all()
    )
    for pid, total, billed, paid, due in orders:
        block = stats[pid]
        block["orders"] = int(total or 0)
        block["billed"] += _num(billed)
        block["paid"] += _num(paid)
        block["due"] += _num(due)

    unpaid = (
        db.query(PharmacyOrder.user_id, func.count(PharmacyOrder.id))
        .filter(
            PharmacyOrder.user_id.in_(patient_ids),
            func.upper(func.coalesce(PharmacyOrder.payment_status, "")) != "PAID",
            func.upper(func.coalesce(PharmacyOrder.status, "")) != "CANCELLED"
        )
        .group_by(PharmacyOrder.user_id)
        .all()
    )
    for pid, total in unpaid:
        stats[pid]["unpaid_orders"] = int(total or 0)

    rx_lines = (
        db.query(Prescription.patient_id, func.count(PrescriptionMedicine.id))
        .join(PrescriptionMedicine, PrescriptionMedicine.prescription_id == Prescription.id)
        .filter(Prescription.patient_id.in_(patient_ids))
        .group_by(Prescription.patient_id)
        .all()
    )
    for pid, total in rx_lines:
        stats[pid]["rx_lines"] = int(total or 0)

    for pid, block in stats.items():
        first = block["first_visit"]
        block["is_new"] = bool(
            first is not None and (today - first).days <= NEW_PATIENT_DAYS
        ) or (block["visits"] == 1 and block["prescriptions"] + block["records"] > 0)

        block["billed"] = round(block["billed"], 2)
        block["paid"] = round(block["paid"], 2)
        block["due"] = round(max(block["due"], 0.0), 2)
        block["refunded"] = round(block["refunded"], 2)

        since_first = (
            (dt.date.today() - first).days if isinstance(first, dt.date) else None
        )

        tags = []
        if block["is_new"]:
            tags.append(
                ("NEW", "new",
                 f"First visit {since_first} day(s) ago"
                 if since_first is not None else "First visit on file")
            )
        if block["urgent_notes"]:
            tags.append((f"{block['urgent_notes']} urgent", "danger", "Urgent note on the file"))
        if block["followup_overdue"]:
            tags.append(("Follow-up overdue", "warn", "Pending follow-up date has passed"))
        if block["due"] > 0:
            tags.append(("Payment due", "danger", "Unpaid amount on file"))
        if block["active_treatment"]:
            tags.append(("Treatment ongoing", "ok", "Active treatment row"))
        if block["visits"] == 0:
            tags.append(("No visit yet", "muted", "Registered, never came"))
        elif block["days_since_visit"] and block["days_since_visit"] > OVERDUE_DAYS:
            tags.append(
                (f"No visit {block['days_since_visit']}d", "muted", "Lapsed - worth a reminder")
            )
        if not block["reviews"] and block["visits"]:
            tags.append(("No review yet", "muted", "Has visited but never reviewed"))
        block["tags"] = tags

    return stats


SORTS = {
    "last_visit": "last_visit",
    "name": "name",
    "visits": "visits",
    "due": "due",
    "new": "first_visit",
    "rating": "avg_rating",
}

SCOPES = [
    ("all", "All patients"),
    ("mine", "My patients"),
    ("new", "New patients"),
    ("followup", "Follow-up due"),
    ("unpaid", "Payment due"),
    ("urgent", "Urgent notes"),
    ("lapsed", "No visit 90+ days"),
    ("norev", "Review pending"),
    ("never", "Never visited"),
]

SCOPE_KEYS = {key for key, _label in SCOPES}


def list_patients(
    db: Session,
    user: User | None,
    *,
    search: str | None = None,
    scope: str = "all",
    sort: str = "last_visit",
    direction: str = "desc",
    page: int = 1,
    per_page: int = 15
) -> tuple[list[dict], dict]:

    doctor_row = resolve_doctor_row(db, user)
    allowed = visible_patient_ids(db, user, doctor_row)

    query = _candidate_patients(db)

    if allowed is not None:
        if not allowed:
            return [], _empty_meta(doctor_row)
        query = query.filter(User.id.in_(allowed))

    term = (search or "").strip()

    if term:
        like = f"%{term.lower()}%"
        query = query.filter(
            or_(
                func.lower(User.name).like(like),
                func.lower(User.email).like(like),
                func.lower(func.coalesce(User.phone, "")).like(like),
                func.cast(User.id, String) == term.lstrip("#"),
            )
        )

    patients = query.all()
    stats = aggregate_stats(db, [row.id for row in patients],
                            doctor_row.id if doctor_row else None)

    everyone: list[dict] = []
    rows: list[dict] = []

    for person in patients:
        block = stats.get(person.id, {})


        entry = {
            "id": person.id,
            "patient_no": f"SJV-{person.id:05d}",
            "name": person.name,
            "email": person.email,
            "phone": person.phone,
            "age": person.age,
            "gender": person.gender,
            "initials": _initials(person.name),
            "enrolled": _fmt_date(person.created_at),
            "stats": block,
            "tags": block.get("tags", []),
        }

        everyone.append(entry)

        if scope != "all" and scope in SCOPE_KEYS:
            if not _matches_scope(entry, scope):
                continue

        rows.append(entry)

    key = SORTS.get(sort, "last_visit")

    def sort_value(row: dict):
        value = row["stats"].get(key)
        if key in ("name",):
            return (row["name"] or "").lower()
        if isinstance(value, dt.date):
            return value.toordinal()
        if value is None:
            return -10**9 if direction != "oldest" else 10**9
        return value

    rows.sort(key=sort_value, reverse=(direction == "desc"))

    total = len(rows)
    pages = max(1, (total + per_page - 1) // per_page)
    page = min(max(1, page), pages)

    meta = {
        "total": total,
        "page": page,
        "pages": pages,
        "per_page": per_page,
        "scopes": [
            {
                "key": key_name,
                "label": label,
                "count": (
                    len(everyone) if key_name == "all"
                    else _count_for_scope(everyone, key_name)
                ),
            }
            for key_name, label in SCOPES
        ],
        "doctor_row": _doctor_brief(doctor_row),
        "linked": doctor_row is not None,
    }

    return rows[(page - 1) * per_page: page * per_page], meta


def _empty_meta(doctor_row) -> dict:
    return {
        "total": 0, "page": 1, "pages": 1, "per_page": 15,
        "scopes": [{"key": key, "label": label, "count": 0} for key, label in SCOPES],
        "doctor_row": _doctor_brief(doctor_row),
        "linked": doctor_row is not None,
    }


def _matches_scope(row: dict, scope: str) -> bool:
    """One definition of every chip, used for filtering and for the counts."""

    block = row["stats"]

    if scope == "all":
        return True
    if scope == "mine":
        return bool(block.get("mine"))
    if scope == "new":
        return bool(block.get("is_new"))
    if scope == "followup":
        return bool(block.get("followups_pending"))
    if scope == "unpaid":
        return _num(block.get("due")) > 0
    if scope == "urgent":
        return bool(block.get("urgent_notes"))
    if scope == "lapsed":
        gap = block.get("days_since_visit")
        return bool(block.get("visits")) and gap is not None and gap > OVERDUE_DAYS
    if scope == "norev":
        return bool(block.get("visits")) and not block.get("reviews")
    if scope == "never":
        return not block.get("visits")

    return True


def _count_for_scope(rows: list[dict], scope: str) -> int:
    """The chips show how many patients each filter would return."""

    return sum(1 for row in rows if _matches_scope(row, scope))


def _initials(name: str | None) -> str:
    words = [part for part in re.split(r"[\s.]+", (name or "").strip()) if part]
    if not words:
        return "?"
    if len(words) == 1:
        return words[0][:2].upper()
    skip = {"dr", "doctor", "mr", "mrs", "ms"}
    words = [word for word in words if word.lower() not in skip] or words
    return (words[0][0] + words[-1][0]).upper()


def _doctor_brief(doctor_row: Doctor | None) -> dict | None:
    if doctor_row is None:
        return None
    return {
        "id": doctor_row.id,
        "name": doctor_row.name,
        "specialization": doctor_row.specialization,
        "consultation_fee": _num(doctor_row.consultation_fee),
    }


def desk_tiles(db: Session, user: User | None) -> dict:
    """The four numbers on top of the desk, recomputed on every load."""

    doctor_row = resolve_doctor_row(db, user)
    allowed = visible_patient_ids(db, user, doctor_row)

    query = _candidate_patients(db)

    if allowed is not None:
        query = query.filter(User.id.in_(allowed if allowed else {-1}))

    ids = [row.id for row in query.all()]
    stats = aggregate_stats(db, ids, doctor_row.id if doctor_row else None)

    today = dt.date.today()

    new_count = sum(1 for block in stats.values() if block.get("is_new"))
    due_total = round(sum(_num(block.get("due")) for block in stats.values()), 2)
    overdue = sum(1 for block in stats.values() if block.get("followup_overdue"))

    appointments_today = (
        db.query(func.count(Appointment.id))
        .filter(Appointment.appointment_date == today)
    )
    if doctor_row is not None and not may_reach_everyone(db, user):
        appointments_today = appointments_today.filter(
            Appointment.doctor_id == doctor_row.id
        )

    return {
        "patients": len(ids),
        "new_30d": new_count,
        "followup_overdue": overdue,
        "due_total": due_total,
        "today_visits": int(appointments_today.scalar() or 0),
        "urgent_notes": int(
            db.query(func.count(DoctorPatientNote.id))
            .filter(
                DoctorPatientNote.status == "ACTIVE",
                DoctorPatientNote.is_urgent.is_(True),
                (
                    DoctorPatientNote.patient_id.in_(ids)
                    if ids else DoctorPatientNote.id.is_(None)
                )
            ).scalar() or 0
        ),
        "doctor": _doctor_brief(doctor_row),
    }


# ==========================================================================
# one patient: the file
# ==========================================================================

def patient_profile(db: Session, patient_id: int) -> dict | None:

    person = db.get(User, patient_id)

    if person is None:
        return None

    return {
        "id": person.id,
        "patient_no": f"SJV-{person.id:05d}",
        "name": person.name,
        "email": person.email,
        "phone": person.phone,
        "age": person.age,
        "gender": person.gender,
        "initials": _initials(person.name),
        "role": (person.role or "PATIENT").upper(),
        "is_active": bool(person.is_active),
        "enrolled": _fmt_date(person.created_at),
        "enrolled_raw": _date(person.created_at),
    }


def visits(db: Session, patient_id: int) -> list[dict]:

    rows = (
        db.query(Appointment, Doctor)
        .outerjoin(Doctor, Doctor.id == Appointment.doctor_id)
        .filter(Appointment.patient_id == patient_id)
        .order_by(Appointment.appointment_date.desc(), Appointment.start_time.desc())
        .all()
    )

    out = []

    for row, doctor in rows:
        out.append({
            "id": row.id,
            "date": _fmt_date(row.appointment_date),
            "time": row.start_time.strftime("%H:%M") if row.start_time else "-",
            "end": row.end_time.strftime("%H:%M") if row.end_time else "-",
            "status": row.status,
            "visit_type": row.visit_type,
            "duration": row.duration_minutes,
            "reason": row.reason,
            "doctor": doctor.name if doctor else "Not assigned",
            "specialization": doctor.specialization if doctor else None,
            "method": row.payment_method,
            "payment_status": row.payment_status,
            "amount": _num(row.payment_amount),
            "refund_status": row.refund_status,
            "refund_amount": _num(row.refund_amount),
            "paid_at": _fmt_dt(row.refund_at) if row.refund_at else None,
            "cancelled_by": row.cancelled_by,
            "doctor_cancel_reason": row.doctor_cancel_reason,
            "is_past": (_date(row.appointment_date) or dt.date.today()) < dt.date.today(),
        })

    return out


def clinical_records(db: Session, patient_id: int) -> list[dict]:

    rows = (
        db.query(MedicalRecord, Doctor)
        .outerjoin(Doctor, Doctor.id == MedicalRecord.doctor_id)
        .filter(MedicalRecord.patient_id == patient_id)
        .order_by(MedicalRecord.visit_date.desc())
        .all()
    )

    out = []

    for row, doctor in rows:
        out.append({
            "id": row.id,
            "visit_date": _fmt_date(row.visit_date),
            "doctor": doctor.name if doctor else "-",
            "appointment_id": row.appointment_id,
            "chief_complaint": row.chief_complaint,
            "symptoms": row.symptoms,
            "clinical_notes": row.clinical_notes,
            "diagnosis": row.diagnosis_notes,
            "treatment": row.treatment_summary,
            "medicines": row.medicines,
            "instructions": row.doctor_instructions,
            "status": row.status,
            "created": _fmt_dt(row.created_at),
        })

    return out


def treatments(db: Session, patient_id: int) -> list[dict]:

    rows = (
        db.query(Treatment, Doctor)
        .outerjoin(Doctor, Doctor.id == Treatment.doctor_id)
        .filter(Treatment.patient_id == patient_id)
        .order_by(Treatment.start_date.desc(), Treatment.id.desc())
        .all()
    )

    out = []

    for row, doctor in rows:
        out.append({
            "id": row.id,
            "name": row.treatment_name,
            "description": row.description,
            "doctor": doctor.name if doctor else "-",
            "start": _fmt_date(row.start_date),
            "end": _fmt_date(row.end_date),
            "status": row.status,
            "running_days": _days_between(row.start_date) if row.start_date else None,
        })

    return out


def follow_ups(db: Session, patient_id: int) -> list[dict]:

    rows = (
        db.query(FollowUp, Doctor)
        .outerjoin(Doctor, Doctor.id == FollowUp.doctor_id)
        .filter(FollowUp.patient_id == patient_id)
        .order_by(FollowUp.follow_up_date.desc())
        .all()
    )

    out = []

    for row, doctor in rows:
        day = _date(row.follow_up_date)
        delta = _days_between(dt.date.today(), day) if day else None
        out.append({
            "id": row.id,
            "date": _fmt_date(row.follow_up_date),
            "reason": row.reason,
            "instructions": row.instructions,
            "doctor": doctor.name if doctor else "-",
            "status": row.status,
            "completed": _fmt_dt(row.completed_at) if row.completed_at else None,
            "overdue": bool(day and day < dt.date.today() and row.status != "COMPLETED"),
            "days_left": delta,
        })

    return out


def prescriptions(db: Session, patient_id: int) -> list[dict]:

    rows = (
        db.query(Prescription, Doctor)
        .outerjoin(Doctor, Doctor.id == Prescription.doctor_id)
        .filter(Prescription.patient_id == patient_id)
        .order_by(Prescription.created_at.desc())
        .all()
    )

    out = []

    for row, doctor in rows:
        lines = (
            db.query(PrescriptionMedicine)
            .filter(PrescriptionMedicine.prescription_id == row.id)
            .order_by(PrescriptionMedicine.id)
            .all()
        )

        out.append({
            "id": row.id,
            "date": _fmt_dt(row.created_at),
            "doctor": doctor.name if doctor else "-",
            "diagnosis": row.diagnosis,
            "instructions": row.doctor_instructions,
            "medical_record_id": row.medical_record_id,
            "lines": [{
                "id": line.id,
                "name": line.medicine_name,
                "dose": line.dosage,
                "frequency": line.frequency,
                "duration": line.duration,
                "days": _duration_days(line.duration),
                "advice": line.instructions,
            } for line in lines],
        })

    return out


def reviews(db: Session, patient_id: int) -> list[dict]:

    rows = (
        db.query(TreatmentReview, Doctor, Treatment)
        .outerjoin(Doctor, Doctor.id == TreatmentReview.doctor_id)
        .outerjoin(Treatment, Treatment.id == TreatmentReview.treatment_id)
        .filter(TreatmentReview.patient_id == patient_id)
        .order_by(TreatmentReview.created_at.desc())
        .all()
    )

    out = []

    for row, doctor, treatment in rows:
        out.append({
            "id": row.id,
            "date": _fmt_dt(row.created_at),
            "doctor": doctor.name if doctor else "-",
            "treatment": treatment.treatment_name if treatment else None,
            "outcome": row.outcome,
            "condition": row.current_condition,
            "experience": row.experience,
            "follow_up_preference": row.follow_up_preference,
            "reason_for_change": row.change_reason,
            "rating": row.rating,
            "comment": row.comment,
        })

    return out


def reports(db: Session, patient_id: int) -> list[dict]:

    rows = (
        db.query(PatientDocument)
        .filter(PatientDocument.patient_id == patient_id)
        .order_by(PatientDocument.uploaded_at.desc())
        .all()
    )

    out = []

    for row in rows:
        out.append({
            "id": row.id,
            "name": row.document_name,
            "type": row.document_type,
            "path": row.file_path,
            "size_kb": round((row.file_size or 0) / 1024, 1),
            "uploaded": _fmt_dt(row.uploaded_at),
            "status": row.status,
        })

    return out


def screenings(db: Session, patient_id: int) -> list[dict]:

    rows = (
        db.query(ScreeningHistory)
        .filter(ScreeningHistory.patient_id == patient_id)
        .order_by(ScreeningHistory.created_at.desc())
        .all()
    )

    return [{
        "id": row.id,
        "date": _fmt_dt(row.created_at),
        "symptoms": row.symptoms,
        "advice": row.ai_response,
        "category": row.care_category,
        "specialist": row.recommended_specialist,
        "severity": row.severity,
    } for row in rows]


# ==========================================================================
# money: the whole invoice history of a patient
# ==========================================================================

def ledger(db: Session, patient_id: int) -> dict:

    lines: list[dict] = []

    for row in visits(db, patient_id):
        amount = row["amount"]
        lines.append({
            "kind": "APPOINTMENT",
            "id": row["id"],
            "title": f"{row['visit_type'] or 'Consultation'} - {row['doctor']}",
            "date": row["date"],
            "time": row["time"],
            "billed": amount,
            "paid": amount if str(row["payment_status"]).upper() == "PAID" else 0.0,
            "status": row["payment_status"],
            "order_status": row["status"],
            "method": row["method"],
            "reference": None,
            "where": "Clinic reception",
            "refund": row["refund_amount"],
            "note": row["reason"],
        })

    orders = (
        db.query(PharmacyOrder)
        .filter(PharmacyOrder.user_id == patient_id)
        .order_by(PharmacyOrder.created_at.desc())
        .all()
    )

    for order in orders:
        where = "Clinic pharmacy counter"

        if (order.delivery_type or "").upper() == "DELIVERY":
            where = f"Delivered - {order.address or 'address on file'}"

        provider = (order.payment_provider or "").upper()
        if provider == "RAZORPAY":
            where = "Clinic pharmacy (UPI/Razorpay)"
        elif provider == "NEARBY":
            where = "Partner chemist (found nearby)"

        lines.append({
            "kind": "PHARMACY",
            "id": order.id,
            "order_no": order.order_no,
            "title": f"Medicine order {order.order_no}",
            "date": _fmt_date(order.created_at),
            "time": order.created_at.strftime("%H:%M") if order.created_at else "",
            "billed": _num(order.total),
            "paid": _num(order.total) if (order.payment_status or "").upper() == "PAID" else 0.0,
            "status": order.payment_status,
            "order_status": order.status,
            "method": order.payment_method,
            "reference": order.transaction_id,
            "where": where,
            "refund": 0.0 if (order.payment_status or "").upper() != "REFUNDED" else _num(order.total),
            "note": order.notes,
            "item_count": len(order.items or []),
            "emergency": bool(order.is_emergency),
            "link": f"/pharmacy/order/{order.order_no}",
        })

    lines.sort(key=lambda row: (row["date"] or "", row["time"] or ""), reverse=True)

    billed = round(sum(_num(row["billed"]) for row in lines), 2)
    paid = round(sum(_num(row["paid"]) for row in lines), 2)
    refunded = round(sum(_num(row["refund"]) for row in lines), 2)

    return {
        "lines": lines,
        "totals": {
            "billed": billed,
            "paid": paid,
            "due": round(max(billed - paid, 0.0), 2),
            "refunded": refunded,
            "count": len(lines),
            "unpaid_count": sum(
                1 for row in lines
                if str(row["status"]).upper() not in ("PAID", "REFUNDED")
                and _num(row["billed"]) > 0
            ),
        },
    }


def medicine_journey(db: Session, patient_id: int) -> list[dict]:
    """"Konsi tablet, kitne din ki, kahaan se li, kab li, paid ya nahi." """

    per_name: dict[str, dict] = {}

    prescribed = (
        db.query(PrescriptionMedicine, Prescription, Doctor)
        .join(Prescription, Prescription.id == PrescriptionMedicine.prescription_id)
        .outerjoin(Doctor, Doctor.id == Prescription.doctor_id)
        .filter(Prescription.patient_id == patient_id)
        .order_by(Prescription.created_at.desc())
        .all()
    )

    for line, prescription, doctor in prescribed:
        key = normalize_name(line.medicine_name) or line.medicine_name.lower()
        block = per_name.setdefault(key, {
            "medicine": line.medicine_name,
            "prescribed_times": 0,
            "prescribed_dates": [],
            "total_days": 0,
            "courses": [],
            "doctors": [],
            "packs": 0,
            "spent": 0.0,
            "bought_dates": [],
            "sources": [],
            "payment": "not bought",
            "last_price": None,
            "order_refs": [],
            "statuses": [],
        })

        block["prescribed_times"] += 1
        days = _duration_days(line.duration)
        block["total_days"] += days
        block["prescribed_dates"].append(prescription.created_at)

        if doctor is not None and doctor.name not in block["doctors"]:
            block["doctors"].append(doctor.name)

        block["courses"].append({
            "rx_id": prescription.id,
            "date": _fmt_date(prescription.created_at),
            "dose": line.dosage,
            "frequency": line.frequency,
            "duration": line.duration,
            "days": days,
            "advice": line.instructions,
            "doctor": doctor.name if doctor else "-",
        })

    bought = (
        db.query(PharmacyOrderItem, PharmacyOrder)
        .join(PharmacyOrder, PharmacyOrder.id == PharmacyOrderItem.order_id)
        .filter(PharmacyOrder.user_id == patient_id)
        .order_by(PharmacyOrder.created_at.desc())
        .all()
    )

    for item, order in bought:
        key = normalize_name(item.medicine_name) or item.medicine_name.lower()
        block = per_name.setdefault(key, {
            "medicine": item.medicine_name,
            "prescribed_times": 0,
            "prescribed_dates": [],
            "total_days": 0,
            "courses": [],
            "doctors": [],
            "packs": 0,
            "spent": 0.0,
            "bought_dates": [],
            "sources": [],
            "payment": "not bought",
            "last_price": None,
            "order_refs": [],
            "statuses": [],
        })

        block["packs"] += int(item.quantity or 0)
        block["spent"] = round(block["spent"] + _num(item.line_total), 2)
        block["last_price"] = _num(item.unit_price)
        block["bought_dates"].append(order.created_at)
        block["order_refs"].append(order.order_no)
        block["statuses"].append(
            f"{order.status} / {order.payment_status}"
        )

        where = "Clinic pharmacy counter"
        if (order.delivery_type or "").upper() == "DELIVERY":
            where = "Delivered to home"
        if (order.payment_provider or "").upper() == "NEARBY":
            where = "Partner chemist (nearby)"
        if where not in block["sources"]:
            block["sources"].append(where)

    for block in per_name.values():
        if block["packs"]:
            block["payment"] = (
                "paid" if all(
                    "PAID" in status or "CONFIRMED" in status
                    for status in block["statuses"]
                ) else "partly / not paid"
            )

        dates = block.pop("prescribed_dates") + block.pop("bought_dates")
        dates = [row for row in dates if row is not None]
        dates.sort()
        block["first"] = _fmt_date(dates[0]) if dates else "-"
        block["last"] = _fmt_date(dates[-1]) if dates else "-"
        block["days_since_last"] = _days_between(dates[-1]) if dates else None

    return sorted(
        per_name.values(),
        key=lambda block: (block["last"] or "", block["medicine"]),
        reverse=True
    )


def order_items_for(db: Session, order_id: int) -> list[dict]:

    rows = (
        db.query(PharmacyOrderItem)
        .filter(PharmacyOrderItem.order_id == order_id)
        .order_by(PharmacyOrderItem.id)
        .all()
    )

    return [{
        "name": row.medicine_name,
        "generic": row.generic_name,
        "form": row.form,
        "strength": row.strength,
        "pack": row.pack_size,
        "qty": row.quantity,
        "price": _num(row.unit_price),
        "total": _num(row.line_total),
        "days": _duration_days(row.duration),
        "dose": row.dosage,
        "frequency": row.frequency,
        "duration": row.duration,
        "source": row.source,
    } for row in rows]


def orders_detail(db: Session, patient_id: int) -> list[dict]:

    out = []

    for order in (
        db.query(PharmacyOrder)
        .filter(PharmacyOrder.user_id == patient_id)
        .order_by(PharmacyOrder.created_at.desc())
        .all()
    ):
        out.append({
            "id": order.id,
            "order_no": order.order_no,
            "date": _fmt_dt(order.created_at),
            "status": order.status,
            "payment_status": order.payment_status,
            "payment_method": order.payment_method,
            "provider": order.payment_provider,
            "reference": order.transaction_id,
            "delivery_type": order.delivery_type,
            "address": order.address,
            "subtotal": _num(order.subtotal),
            "delivery_fee": _num(order.delivery_fee),
            "total": _num(order.total),
            "emergency": bool(order.is_emergency),
            "notes": order.notes,
            "cancel_reason": order.cancel_reason,
            "handed_over": _fmt_dt(order.handed_over_at) if order.handed_over_at else None,
            "link": f"/pharmacy/order/{order.order_no}",
            "items": order_items_for(db, order.id),
        })

    return out


# ==========================================================================
# the one merged story
# ==========================================================================

def timeline(db: Session, patient_id: int, limit: int = 60) -> list[dict]:

    events: list[dict] = []

    def add(when, kind: str, title: str, sub: str = "", tone: str = "muted",
            money: float | None = None, link: str | None = None) -> None:
        stamp = when if isinstance(when, dt.datetime) else (
            dt.datetime.combine(when, dt.time()) if isinstance(when, dt.date) else None
        )
        events.append({
            "when": stamp,
            "when_text": _fmt_dt(when) if when else "-",
            "kind": kind,
            "title": title,
            "sub": sub,
            "tone": tone,
            "money": money,
            "link": link,
        })

    for row in (
        db.query(Appointment, Doctor)
        .outerjoin(Doctor, Doctor.id == Appointment.doctor_id)
        .filter(Appointment.patient_id == patient_id).all()
    ):
        appt, doctor = row
        add(
            appt.appointment_date, "visit",
            f"{appt.status} visit"
            + (f" - {appt.visit_type}" if appt.visit_type else ""),
            f"{doctor.name if doctor else 'No doctor'} at "
            f"{appt.start_time.strftime('%H:%M') if appt.start_time else '-'}"
            + (f" - {appt.reason}" if appt.reason else ""),
            tone="ok" if appt.status in ("COMPLETED",) else "warn",
            money=_num(appt.payment_amount)
        )

    for row in db.query(MedicalRecord).filter(
        MedicalRecord.patient_id == patient_id
    ).all():
        add(
            row.visit_date, "record", "Consultation note",
            (row.diagnosis_notes or row.chief_complaint or "")[:150],
            tone="info"
        )

    for row in db.query(Prescription).filter(
        Prescription.patient_id == patient_id
    ).all():
        count = (
            db.query(func.count(PrescriptionMedicine.id))
            .filter(PrescriptionMedicine.prescription_id == row.id)
            .scalar()
        )
        add(
            row.created_at, "rx", f"Prescription issued ({count or 0} medicines)",
            (row.diagnosis or "")[:120], tone="primary",
            link="/pharmacy/prescriptions"
        )

    for order in db.query(PharmacyOrder).filter(
        PharmacyOrder.user_id == patient_id
    ).all():
        add(
            order.created_at, "order",
            f"Order {order.order_no} - {order.status}",
            f"{len(order.items or [])} item(s), paid via {order.payment_method}",
            tone="danger" if order.status == "CANCELLED" else "ok",
            money=_num(order.total),
            link=f"/pharmacy/order/{order.order_no}"
        )

    for row in db.query(FollowUp).filter(FollowUp.patient_id == patient_id).all():
        done = (row.status or "").upper() == "COMPLETED"
        add(
            row.follow_up_date, "followup",
            "Follow-up completed" if done else "Follow-up due",
            (row.reason or "")[:120],
            tone="muted" if done else "warn"
        )

    for row in db.query(TreatmentReview).filter(
        TreatmentReview.patient_id == patient_id
    ).all():
        add(
            row.created_at, "review",
            f"Patient review{f' - {row.rating}/5' if row.rating else ''}",
            (row.comment or row.outcome or "")[:140], tone="primary"
        )

    for row in db.query(PatientDocument).filter(
        PatientDocument.patient_id == patient_id
    ).all():
        add(row.uploaded_at, "report", f"Uploaded {row.document_name}",
            row.document_type or "document", tone="muted")

    for row in db.query(ScreeningHistory).filter(
        ScreeningHistory.patient_id == patient_id
    ).all():
        add(row.created_at, "screening", "AI health screening",
            f"{row.care_category or 'triage'}"
            + (f" - {row.recommended_specialist}" if row.recommended_specialist else ""),
            tone="info")

    for row in db.query(DoctorPatientNote).filter(
        DoctorPatientNote.patient_id == patient_id,
        DoctorPatientNote.status == "ACTIVE"
    ).all():
        add(row.created_at, "note", f"Note - {row.title}",
            (row.body or "")[:140],
            tone="danger" if row.is_urgent else "primary")

    events.sort(key=lambda item: item["when"] or dt.datetime.min, reverse=True)

    return events[:limit]


# ==========================================================================
# notes
# ==========================================================================

def notes_for(db: Session, patient_id: int, include_hidden: bool = False) -> list[dict]:

    query = (
        db.query(DoctorPatientNote)
        .filter(DoctorPatientNote.patient_id == patient_id)
    )

    if not include_hidden:
        query = query.filter(DoctorPatientNote.status == "ACTIVE")

    rows = query.order_by(
        DoctorPatientNote.is_pinned.desc(),
        DoctorPatientNote.created_at.desc()
    ).all()

    return [{
        "id": row.id,
        "type": row.note_type,
        "type_label": NOTE_TYPE_LABELS.get(row.note_type, row.note_type),
        "title": row.title,
        "body": row.body,
        "author": row.doctor_name or "-",
        "author_specialization": row.doctor_specialization,
        "author_id": row.doctor_id,
        "visibility": row.visibility,
        "is_pinned": bool(row.is_pinned),
        "is_urgent": bool(row.is_urgent),
        "follow_up_date": _fmt_date(row.follow_up_date) if row.follow_up_date else None,
        "created": _fmt_dt(row.created_at),
        "created_raw": row.created_at,
        "ago": _days_between(row.created_at),
        "status": row.status,
    } for row in rows]


def add_note(
    db: Session,
    *,
    patient_id: int,
    author: User | None,
    doctor_row: Doctor | None,
    title: str,
    body: str | None = None,
    note_type: str = "NOTE",
    visibility: str = "DOCTOR_ONLY",
    is_pinned: bool = False,
    is_urgent: bool = False,
    follow_up_date: dt.date | None = None,
    request=None
) -> DoctorPatientNote:

    title = (title or "").strip()

    if not title:
        raise ValueError("Give the note a title (one line is enough).")

    if len(title) > 160:
        raise ValueError("Keep the note title under 160 characters.")

    note_type = (note_type or "NOTE").upper()

    if note_type not in NOTE_TYPE_LABELS:
        raise ValueError(f"Unknown note type '{note_type}'.")

    visibility = (visibility or "DOCTOR_ONLY").upper()

    if visibility not in ("DOCTOR_ONLY", "PATIENT_VISIBLE"):
        visibility = "DOCTOR_ONLY"

    note = DoctorPatientNote(
        doctor_id=author.id if author is not None else None,
        doctor_name=author.name if author is not None else None,
        doctor_specialization=doctor_row.specialization if doctor_row else None,
        patient_id=patient_id,
        note_type=note_type,
        title=title,
        body=(body or "").strip() or None,
        visibility=visibility,
        is_pinned=bool(is_pinned),
        is_urgent=bool(is_urgent),
        follow_up_date=follow_up_date,
        status="ACTIVE",
        created_at=dt.datetime.utcnow(),
        updated_at=dt.datetime.utcnow(),
    )

    db.add(note)
    db.flush()

    audit.log_activity(
        db,
        action="doctor.note.add",
        entity_type="patient_note",
        entity_id=note.id,
        description=f"Note '{title[:60]}' on patient #{patient_id}",
        actor=audit_actor(author),
        after={
            "type": note.note_type,
            "title": note.title,
            "visibility": note.visibility,
            "urgent": note.is_urgent,
        },
        severity="CRITICAL" if note_type == "RED_FLAG" else "INFO",
        request=request,
        commit=False
    )

    db.commit()
    db.refresh(note)

    return note


def set_note_flag(
    db: Session,
    note_id: int,
    *,
    field: str,
    actor: User | None,
    request=None
) -> dict:

    if field not in ("is_pinned", "is_urgent", "status"):
        raise ValueError("Only pin, urgent and archive can be toggled.")

    note = db.get(DoctorPatientNote, note_id)

    if note is None:
        raise ValueError("That note is gone.")

    before = {field: getattr(note, field)}

    if field == "status":
        note.status = "ARCHIVED" if note.status == "ACTIVE" else "ACTIVE"
    else:
        setattr(note, field, not bool(getattr(note, field)))

    note.updated_at = dt.datetime.utcnow()

    audit.log_activity(
        db,
        action=f"doctor.note.{field}",
        entity_type="patient_note",
        entity_id=note.id,
        description=f"{field} -> {getattr(note, field)} on note '{note.title[:40]}'",
        actor=audit_actor(actor),
        before=before,
        after={field: getattr(note, field)},
        request=request,
        commit=False
    )

    db.commit()

    return {"id": note.id, field: bool(getattr(note, field))}


def delete_note(
    db: Session,
    note_id: int,
    *,
    actor: User | None,
    request=None
) -> dict:
    """Archive, never destroy - the file must keep its history."""

    note = db.get(DoctorPatientNote, note_id)

    if note is None:
        raise ValueError("That note is gone.")

    note.status = "ARCHIVED"
    note.updated_at = dt.datetime.utcnow()

    audit.log_activity(
        db,
        action="doctor.note.archive",
        entity_type="patient_note",
        entity_id=note.id,
        description=f"Archived note '{note.title[:60]}'",
        actor=audit_actor(actor),
        after={"status": "ARCHIVED"},
        request=request,
        commit=False
    )

    db.commit()

    return {"id": note.id, "status": "ARCHIVED"}


def audit_actor(user: User | None) -> dict:
    from src.security import rbac

    return rbac.actor_of(user)


# ==========================================================================
# writing into the file: record, prescription, follow-up, payment
# ==========================================================================

def write_record(
    db: Session,
    *,
    patient_id: int,
    author: User | None,
    doctor_row: Doctor | None,
    visit_date: dt.date | None,
    chief_complaint: str | None,
    symptoms: str | None,
    clinical_notes: str | None,
    diagnosis: str | None,
    treatment_summary: str | None,
    medicines: str | None,
    instructions: str | None,
    status: str = "ACTIVE",
    appointment_id: int | None = None,
    request=None
) -> MedicalRecord:

    record = MedicalRecord(
        patient_id=patient_id,
        doctor_id=doctor_row.id if doctor_row else None,
        appointment_id=appointment_id,
        visit_date=visit_date or dt.date.today(),
        chief_complaint=(chief_complaint or "").strip() or None,
        symptoms=(symptoms or "").strip() or None,
        clinical_notes=(clinical_notes or "").strip() or None,
        diagnosis_notes=(diagnosis or "").strip() or None,
        treatment_summary=(treatment_summary or "").strip() or None,
        medicines=(medicines or "").strip() or None,
        doctor_instructions=(instructions or "").strip() or None,
        status=(status or "ACTIVE").upper(),
        created_at=dt.datetime.utcnow(),
        updated_at=dt.datetime.utcnow(),
    )

    db.add(record)
    db.flush()

    audit.log_activity(
        db,
        action="doctor.record.write",
        entity_type="medical_record",
        entity_id=record.id,
        description=f"Consultation note for patient #{patient_id}",
        actor=audit_actor(author),
        after={
            "visit_date": str(record.visit_date),
            "diagnosis": (record.diagnosis_notes or "")[:120],
            "status": record.status,
        },
        request=request,
        commit=False
    )

    db.commit()
    db.refresh(record)

    return record


def update_record_status(
    db: Session,
    record_id: int,
    *,
    status: str,
    actor: User | None,
    request=None
) -> dict:

    record = db.get(MedicalRecord, record_id)

    if record is None:
        raise ValueError("That record is gone.")

    before = {"status": record.status}
    record.status = (status or "ACTIVE").upper()
    record.updated_at = dt.datetime.utcnow()

    audit.log_activity(
        db,
        action="doctor.record.status",
        entity_type="medical_record",
        entity_id=record.id,
        description=f"Record #{record.id} -> {record.status}",
        actor=audit_actor(actor),
        before=before,
        after={"status": record.status},
        request=request,
        commit=False
    )

    db.commit()

    return {"id": record.id, "status": record.status}


PRESCRIPTION_LINE_COLUMNS = 5


def parse_prescription_lines(raw: str) -> list[dict]:
    """One medicine per line:

        Dolo 650 | 650 mg | twice a day | 5 days | after food

    Only the name is required - the rest may be blank.
    """

    lines: list[dict] = []

    for text in (raw or "").splitlines():
        text = text.strip()

        if not text:
            continue

        parts = [part.strip() for part in text.split("|")]
        parts += [""] * (PRESCRIPTION_LINE_COLUMNS - len(parts))

        name = parts[0]

        if not name:
            continue

        lines.append({
            "name": name[:200],
            "dosage": parts[1][:100] or None,
            "frequency": parts[2][:100] or None,
            "duration": parts[3][:100] or None,
            "instructions": parts[4][:500] or None,
        })

    return lines


def write_prescription(
    db: Session,
    *,
    patient_id: int,
    author: User | None,
    doctor_row: Doctor | None,
    diagnosis: str | None,
    instructions: str | None,
    lines_raw: str,
    medical_record_id: int | None = None,
    treatment_id: int | None = None,
    request=None
) -> Prescription:

    lines = parse_prescription_lines(lines_raw)

    if not lines:
        raise ValueError(
            "Add at least one medicine line, e.g. "
            "\"Dolo 650 | 650 mg | twice a day | 5 days | after food\"."
        )

    prescription = Prescription(
        patient_id=patient_id,
        doctor_id=doctor_row.id if doctor_row else None,
        medical_record_id=medical_record_id,
        treatment_id=treatment_id,
        diagnosis=(diagnosis or "").strip() or None,
        doctor_instructions=(instructions or "").strip() or None,
        created_at=dt.datetime.utcnow(),
        updated_at=dt.datetime.utcnow(),
    )

    db.add(prescription)
    db.flush()

    for line in lines:
        db.add(PrescriptionMedicine(
            prescription_id=prescription.id,
            medicine_name=line["name"],
            dosage=line["dosage"],
            frequency=line["frequency"],
            duration=line["duration"],
            instructions=line["instructions"],
            created_at=dt.datetime.utcnow(),
        ))

    audit.log_activity(
        db,
        action="doctor.prescription.write",
        entity_type="prescription",
        entity_id=prescription.id,
        description=(
            f"Prescription for patient #{patient_id} "
            f"({len(lines)} medicine line(s))"
        ),
        actor=audit_actor(author),
        after={
            "lines": [line["name"] for line in lines],
            "diagnosis": (prescription.diagnosis or "")[:120],
        },
        severity="CRITICAL",
        request=request,
        commit=False
    )

    db.commit()
    db.refresh(prescription)

    return prescription


def send_prescription_to_cart(
    db: Session,
    *,
    prescription_id: int,
    actor: User | None,
    request=None
) -> dict:
    """Put the tablets the doctor just wrote into the patient's pharmacy cart.

    The patient still checks out themselves - this only saves them searching
    for each strip at the counter.
    """

    from src.services import pharmacy_cart_service as cart

    prescription = db.get(Prescription, prescription_id)

    if prescription is None:
        raise ValueError("That prescription is gone.")

    patient = db.get(User, prescription.patient_id)

    if patient is None:
        raise ValueError("The patient on that prescription no longer exists.")

    lines = (
        db.query(PrescriptionMedicine)
        .filter(PrescriptionMedicine.prescription_id == prescription_id)
        .all()
    )

    added: list[str] = []
    skipped: list[dict] = []

    for line in lines:
        from src.services import pharmacy_catalog_service as catalog

        medicine = catalog.match_medicine(db, line.medicine_name)

        if medicine is None:
            skipped.append({
                "name": line.medicine_name,
                "reason": "not stocked here - use the nearby search",
            })
            continue

        days = _duration_days(line.duration)
        packs = 1

        if days > 10:
            packs = 2
        if days > 25:
            packs = 3

        packs = min(packs, int(medicine.stock or 1) or 1)

        try:
            cart.add_catalog_item(db, patient, medicine.id, packs)
            added.append(f"{medicine.name} x{packs}")
        except cart.CartError as exc:
            skipped.append({"name": line.medicine_name, "reason": str(exc)})

    audit.log_activity(
        db,
        action="doctor.prescription.send_to_cart",
        entity_type="prescription",
        entity_id=prescription_id,
        description=(
            f"Pushed Rx #{prescription_id} to patient #{patient.id}'s cart "
            f"({len(added)} added, {len(skipped)} skipped)"
        ),
        actor=audit_actor(actor),
        after={"added": added, "skipped": [row["name"] for row in skipped]},
        request=request,
        commit=False
    )

    db.commit()

    return {
        "patient": patient.name,
        "added": added,
        "skipped": skipped,
        "cart_url": "/pharmacy/cart",
    }


def schedule_follow_up(
    db: Session,
    *,
    patient_id: int,
    actor: User | None,
    doctor_row: Doctor | None,
    on_date: dt.date,
    reason: str | None,
    instructions: str | None,
    medical_record_id: int | None = None,
    appointment_id: int | None = None,
    request=None
) -> FollowUp:

    if on_date is None:
        raise ValueError("Pick a date for the follow-up.")

    row = FollowUp(
        patient_id=patient_id,
        medical_record_id=medical_record_id,
        doctor_id=doctor_row.id if doctor_row else None,
        appointment_id=appointment_id,
        follow_up_date=on_date,
        reason=(reason or "").strip() or None,
        instructions=(instructions or "").strip() or None,
        status="PENDING",
        created_at=dt.datetime.utcnow(),
        updated_at=dt.datetime.utcnow(),
    )

    db.add(row)
    db.flush()

    audit.log_activity(
        db,
        action="doctor.followup.schedule",
        entity_type="follow_up",
        entity_id=row.id,
        description=f"Follow-up booked for {_fmt_date(on_date)} (patient #{patient_id})",
        actor=audit_actor(actor),
        after={"date": str(on_date), "reason": (reason or "")[:120]},
        request=request,
        commit=False
    )

    db.commit()
    db.refresh(row)

    return row


def complete_follow_up(
    db: Session,
    follow_up_id: int,
    *,
    actor: User | None,
    request=None
) -> dict:

    row = db.get(FollowUp, follow_up_id)

    if row is None:
        raise ValueError("That follow-up is gone.")

    before = {"status": row.status}
    row.status = "COMPLETED"
    row.completed_at = dt.datetime.utcnow()
    row.updated_at = dt.datetime.utcnow()

    audit.log_activity(
        db,
        action="doctor.followup.complete",
        entity_type="follow_up",
        entity_id=row.id,
        description=f"Follow-up #{row.id} marked done (patient #{row.patient_id})",
        actor=audit_actor(actor),
        before=before,
        after={"status": "COMPLETED"},
        request=request,
        commit=False
    )

    db.commit()

    return {"id": row.id, "status": row.status}


def set_appointment_payment(
    db: Session,
    appointment_id: int,
    *,
    status: str,
    actor: User | None,
    amount: float | None = None,
    method: str | None = None,
    note: str | None = None,
    request=None
) -> dict:
    """Record the consultation fee at the desk (the appointment table already
    has the money columns; nothing in the app wrote them until now)."""

    row = db.get(Appointment, appointment_id)

    if row is None:
        raise ValueError("That appointment is gone.")

    status = (status or "").upper()

    if status not in ("PENDING", "PAID", "FAILED", "REFUNDED", "NOT_REQUIRED"):
        raise ValueError("Use PENDING, PAID, FAILED, REFUNDED or NOT_REQUIRED.")

    from src.models.doctor import Doctor as DoctorModel

    if amount is None:
        doctor = (
            db.query(DoctorModel)
            .filter(DoctorModel.id == row.doctor_id)
            .first()
            if row.doctor_id else None
        )
        amount = _num(row.payment_amount) or _num(
            getattr(doctor, "consultation_fee", 0)
        ) or 500.0

    before = {
        "payment_status": row.payment_status,
        "payment_amount": _num(row.payment_amount),
        "payment_method": row.payment_method,
    }

    row.payment_status = status
    row.payment_amount = round(_num(amount), 2)
    row.payment_method = (method or row.payment_method or "CASH").upper()

    if status == "REFUNDED":
        row.refund_status = "REFUNDED"
        row.refund_amount = row.payment_amount
        row.refund_method = row.payment_method
        row.refund_reason = (note or "Refunded from the doctor desk")[:500]
        row.refund_at = dt.datetime.utcnow()
    elif status == "PAID":
        row.refund_status = "NOT_REQUIRED"

    row.updated_at = dt.datetime.utcnow()

    audit.log_activity(
        db,
        action="doctor.payment.write",
        entity_type="appointment",
        entity_id=row.id,
        description=(
            f"Appointment #{row.id} payment {before['payment_status']} -> {status} "
            f"(Rs {row.payment_amount:.2f})"
        ),
        actor=audit_actor(actor),
        before=before,
        after={
            "payment_status": row.payment_status,
            "payment_amount": float(row.payment_amount),
            "payment_method": row.payment_method,
        },
        severity="CRITICAL",
        request=request,
        commit=False
    )

    db.commit()

    return {
        "id": row.id,
        "payment_status": row.payment_status,
        "payment_amount": float(row.payment_amount),
        "payment_method": row.payment_method,
    }


def log_desk_view(
    db: Session,
    *,
    actor: User | None,
    patient_id: int,
    view: str,
    request=None
) -> None:
    """Reading a patient file is written down too - it is the part of the
    module that makes "who saw whom" answerable later."""

    audit.log_activity(
        db,
        action="doctor.patient.view",
        entity_type="patient",
        entity_id=patient_id,
        description=f"Opened patient #{patient_id} ({view})",
        actor=audit_actor(actor),
        severity="DEBUG",
        request=request,
        commit=False
    )

    try:
        db.commit()
    except Exception:  # noqa: BLE001 - a failed log must never break a page
        db.rollback()
        logger.warning("could not log the desk view", exc_info=True)


def dossier(
    db: Session,
    patient_id: int,
    *,
    actor: User | None,
    show_billing: bool = True,
    request=None
) -> dict | None:
    """Everything for one patient, one call."""

    profile = patient_profile(db, patient_id)

    if profile is None:
        return None

    doctor_row = resolve_doctor_row(db, actor)
    stats = aggregate_stats(
        db,
        [patient_id],
        doctor_row.id if doctor_row else None
    ).get(patient_id, {})

    data = {
        "profile": profile,
        "stats": stats,
        "visits": visits(db, patient_id),
        "records": clinical_records(db, patient_id),
        "treatments": treatments(db, patient_id),
        "follow_ups": follow_ups(db, patient_id),
        "prescriptions": prescriptions(db, patient_id),
        "reviews": reviews(db, patient_id),
        "reports": reports(db, patient_id),
        "screenings": screenings(db, patient_id),
        "notes": notes_for(db, patient_id),
        "medicines": medicine_journey(db, patient_id),
        "timeline": timeline(db, patient_id, limit=40),
        "note_types": [{"key": key, "label": label} for key, label in NOTE_TYPES],
        "doctor_row": _doctor_brief(doctor_row),
    }

    if show_billing:
        data["ledger"] = ledger(db, patient_id)
        data["orders"] = orders_detail(db, patient_id)
    else:
        data["ledger"] = {"lines": [], "totals": {}}
        data["orders"] = []

    return data
