from datetime import datetime, date

from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from sqlalchemy.orm import Session

from src.database.connection import get_db
from src.config import TEMPLATES_DIR

from src.models.doctor import Doctor
from src.models.appointment import Appointment
from src.models.treatment_review import TreatmentReview


# ============================================================
# ROUTER
# ============================================================

router = APIRouter(
    prefix="/treatment-review",
    tags=["Treatment Review"]
)

templates = Jinja2Templates(
    directory=str(TEMPLATES_DIR)
)


# ============================================================
# USER
# ============================================================

def get_user_id(request: Request):
    return request.session.get("user_id")


# ============================================================
# PATIENT APPOINTMENTS
# ============================================================

def get_patient_appointments(
    db: Session,
    patient_id: int
):

    return (
        db.query(Appointment)
        .filter(
            Appointment.patient_id == patient_id,
            Appointment.status.notin_(
                [
                    "CANCELLED",
                    "CANCELED"
                ]
            )
        )
        .order_by(
            Appointment.appointment_date.desc(),
            Appointment.start_time.desc()
        )
        .all()
    )


# ============================================================
# DOCTORS WITH RECENT APPOINTMENT
# DIRECT APPOINTMENT + DOCTOR JOIN
# ============================================================

def get_patient_doctor_appointments(
    db: Session,
    patient_id: int
):

    print("========================================")
    print("FEEDBACK DEBUG")
    print("PATIENT ID:", patient_id)

    results = (
        db.query(
            Appointment,
            Doctor
        )
        .join(
            Doctor,
            Appointment.doctor_id == Doctor.id
        )
        .filter(
            Appointment.patient_id == patient_id,
            Appointment.status.notin_(
                [
                    "CANCELLED",
                    "CANCELED"
                ]
            )
        )
        .order_by(
            Appointment.appointment_date.desc(),
            Appointment.start_time.desc()
        )
        .all()
    )

    print(
        "APPOINTMENT + DOCTOR COUNT:",
        len(results)
    )

    doctor_appointments = []

    seen_doctors = set()

    for appointment, doctor in results:

        print(
            "FOUND APPOINTMENT:",
            appointment.id
        )

        print(
            "DOCTOR:",
            doctor.id,
            doctor.name
        )

        print(
            "STATUS:",
            appointment.status
        )

        print(
            "DOCTOR ACTIVE:",
            doctor.is_active
        )

        # Avoid duplicate doctor cards
        if doctor.id in seen_doctors:
            continue

        seen_doctors.add(doctor.id)

        doctor_appointments.append(
            {
                "doctor": doctor,
                "appointment": appointment
            }
        )

    print(
        "FINAL DOCTOR CARDS:",
        len(doctor_appointments)
    )

    print("========================================")

    return doctor_appointments


# ============================================================
# GET PATIENT DOCTORS
# ============================================================

def get_patient_doctors(
    db: Session,
    patient_id: int
):

    doctor_appointments = (
        get_patient_doctor_appointments(
            db,
            patient_id
        )
    )

    print(
        "TEMPLATE DOCTOR APPOINTMENTS:",
        doctor_appointments
    )

    print(
        "TEMPLATE DOCTOR APPOINTMENTS COUNT:",
        len(doctor_appointments)
    )

    return [
        item["doctor"]
        for item in doctor_appointments
    ]


# ============================================================
# LATEST APPOINTMENT
# ============================================================

def get_latest_appointment(
    db: Session,
    patient_id: int,
    doctor_id: int
):

    return (
        db.query(Appointment)
        .filter(
            Appointment.patient_id == patient_id,
            Appointment.doctor_id == doctor_id,
            Appointment.status.notin_(
                [
                    "CANCELLED",
                    "CANCELED"
                ]
            )
        )
        .order_by(
            Appointment.appointment_date.desc(),
            Appointment.start_time.desc()
        )
        .first()
    )


# ============================================================
# ALTERNATIVE DOCTORS
# ============================================================

def get_alternative_doctors(
    db: Session,
    current_doctor: Doctor
):

    if current_doctor is None:
        return []

    return (
        db.query(Doctor)
        .filter(
            Doctor.is_active == True,
            Doctor.id != current_doctor.id,
            Doctor.specialization ==
            current_doctor.specialization
        )
        .order_by(
            Doctor.experience_years.desc(),
            Doctor.name.asc()
        )
        .all()
    )


# ============================================================
# MAIN FEEDBACK PAGE
# ============================================================

@router.get("")
def treatment_review_page(
    request: Request,
    db: Session = Depends(get_db)
):

    user_id = get_user_id(request)

    if user_id is None:

        return RedirectResponse(
            url="/login",
            status_code=303
        )

    print(
        "DEBUG TREATMENT REVIEW USER ID:",
        user_id
    )

    doctor_appointments = (
        get_patient_doctor_appointments(
            db,
            user_id
        )
    )

    reviews = (
        db.query(TreatmentReview)
        .filter(
            TreatmentReview.patient_id == user_id
        )
        .order_by(
            TreatmentReview.created_at.desc()
        )
        .all()
    )

    return templates.TemplateResponse(
        request,
        "treatment_review.html",
        {
            "user": request.session,

            "doctor_appointments":
                doctor_appointments,

            "doctors": [
                item["doctor"]
                for item in doctor_appointments
            ],

            "reviews": reviews,

            "selected_doctor": None,

            "recommended_doctors": [],

            "change_doctor_mode": False,

            "appointment": None,

            "today": date.today()
        }
    )


# ============================================================
# SUBMIT FEEDBACK
# ============================================================

@router.post("/submit")
def submit_treatment_review(

    request: Request,

    doctor_id: int = Form(...),

    rating: int = Form(...),

    outcome: str = Form(""),

    current_condition: str = Form(""),

    experience: str = Form(""),

    follow_up_preference: str = Form(""),

    change_reason: str = Form(""),

    care_action: str = Form(""),

    follow_up_days: str = Form(""),

    comment: str = Form(""),

    db: Session = Depends(get_db)

):

    user_id = get_user_id(request)

    if user_id is None:

        return RedirectResponse(
            url="/login",
            status_code=303
        )

    # ========================================================
    # RATING
    # ========================================================

    if rating < 1 or rating > 5:

        return RedirectResponse(
            url="/treatment-review",
            status_code=303
        )

    # ========================================================
    # DOCTOR
    # ========================================================

    # IMPORTANT:
    # Feedback is allowed for a previous appointment.
    # Current doctor active status is NOT required.

    doctor = (
        db.query(Doctor)
        .filter(
            Doctor.id == doctor_id
        )
        .first()
    )

    if doctor is None:

        return RedirectResponse(
            url="/treatment-review",
            status_code=303
        )

    # ========================================================
    # VERIFY PATIENT HAD APPOINTMENT WITH DOCTOR
    # ========================================================

    appointment = get_latest_appointment(
        db,
        user_id,
        doctor_id
    )

    if appointment is None:

        return RedirectResponse(
            url="/treatment-review",
            status_code=303
        )

    # ========================================================
    # CLEAN INPUT
    # ========================================================

    outcome = (
        outcome or ""
    ).strip()

    current_condition = (
        current_condition or ""
    ).strip()

    experience = (
        experience or ""
    ).strip()

    follow_up_preference = (
        follow_up_preference or ""
    ).strip()

    change_reason = (
        change_reason or ""
    ).strip()

    care_action = (
        care_action or ""
    ).strip()

    follow_up_days = (
        follow_up_days or ""
    ).strip()

    comment = (
        comment or ""
    ).strip()

    # ========================================================
    # ALLOWED ACTIONS
    # ========================================================

    allowed_actions = {

        5: [
            "NO_FURTHER_TREATMENT",
            "FURTHER_TREATMENT"
        ],

        4: [
            "CONTINUE_TREATMENT",
            "CHANGE_MEDICINES",
            "STOP_TREATMENT"
        ],

        3: [
            "SAME_DOCTOR",
            "CHANGE_DOCTOR",
            "NO_IMPROVEMENT"
        ],

        2: [
            "UNSATISFACTORY",
            "NOT_RECOMMEND",
            "STOP_HOSPITAL"
        ],

        1: [
            "UNSATISFACTORY",
            "NOT_RECOMMEND",
            "STOP_HOSPITAL"
        ]
    }

    if care_action:

        if care_action not in allowed_actions.get(
            rating,
            []
        ):

            return RedirectResponse(
                url="/treatment-review",
                status_code=303
            )

    # ========================================================
    # FOLLOW-UP DAYS
    # ========================================================

    if (
        rating == 5
        and care_action == "FURTHER_TREATMENT"
    ):

        if not follow_up_days:

            return RedirectResponse(
                url="/treatment-review",
                status_code=303
            )

        try:

            days = int(follow_up_days)

        except ValueError:

            return RedirectResponse(
                url="/treatment-review",
                status_code=303
            )

        if days < 1 or days > 365:

            return RedirectResponse(
                url="/treatment-review",
                status_code=303
            )

        change_reason = (
            f"Further treatment required "
            f"for {days} days."
        )

    # ========================================================
    # ACTION LABELS
    # ========================================================

    action_labels = {

        "NO_FURTHER_TREATMENT":
            "No further treatment needed",

        "FURTHER_TREATMENT":
            "I need further treatment",

        "CONTINUE_TREATMENT":
            "Continue treatment for further days",

        "CHANGE_MEDICINES":
            "Change tablets/medicines for better improvement",

        "STOP_TREATMENT":
            "I do not want further treatment",

        "SAME_DOCTOR":
            "I want to continue with the same doctor",

        "CHANGE_DOCTOR":
            "I want to change the doctor",

        "NO_IMPROVEMENT":
            "No improvement is being seen",

        "UNSATISFACTORY":
            "Treatment was not satisfactory",

        "NOT_RECOMMEND":
            "I would not recommend this treatment",

        "STOP_HOSPITAL":
            "I do not want to continue with this hospital anymore"
    }

    selected_action_label = action_labels.get(
        care_action,
        ""
    )

    # ========================================================
    # OLD DB REQUIRED FIELDS
    # ========================================================

    if not outcome:

        outcome = (
            selected_action_label
            if selected_action_label
            else "Feedback Submitted"
        )

    if not current_condition:

        current_condition = (
            "Patient feedback recorded"
        )

    if not experience:

        experience = (
            selected_action_label
            if selected_action_label
            else "Feedback submitted"
        )

    if not follow_up_preference:

        if care_action == "CHANGE_DOCTOR":

            follow_up_preference = (
                "CHANGE_DOCTOR"
            )

        elif care_action:

            follow_up_preference = care_action

        else:

            follow_up_preference = (
                "NOT_SPECIFIED"
            )

    # ========================================================
    # CREATE REVIEW
    # ========================================================

    review = TreatmentReview(

        patient_id=user_id,

        treatment_id=None,

        doctor_id=doctor_id,

        outcome=outcome,

        current_condition=current_condition,

        experience=experience,

        follow_up_preference=
            follow_up_preference,

        change_reason=
            change_reason or None,

        rating=rating,

        comment=comment or None,

        created_at=datetime.utcnow(),

        updated_at=datetime.utcnow()
    )

    # ========================================================
    # SAVE
    # ========================================================

    db.add(review)

    db.commit()

    db.refresh(review)

    # ========================================================
    # SUCCESS PAGE
    # ========================================================

    return templates.TemplateResponse(
        request,
        "treatment_review_success.html",
        {
            "review": review,
            "doctor": doctor,
            "appointment": appointment
        }
    )


# ============================================================
# CHANGE DOCTOR
# ============================================================

@router.get("/change-doctor/{doctor_id}")
def change_doctor(

    request: Request,

    doctor_id: int,

    db: Session = Depends(get_db)

):

    user_id = get_user_id(request)

    if user_id is None:

        return RedirectResponse(
            url="/login",
            status_code=303
        )

    current_doctor = (
        db.query(Doctor)
        .filter(
            Doctor.id == doctor_id
        )
        .first()
    )

    if current_doctor is None:

        return RedirectResponse(
            url="/treatment-review",
            status_code=303
        )

    appointment = get_latest_appointment(
        db,
        user_id,
        doctor_id
    )

    if appointment is None:

        return RedirectResponse(
            url="/treatment-review",
            status_code=303
        )

    recommended_doctors = (
        get_alternative_doctors(
            db,
            current_doctor
        )
    )

    reviews = (
        db.query(TreatmentReview)
        .filter(
            TreatmentReview.patient_id == user_id
        )
        .order_by(
            TreatmentReview.created_at.desc()
        )
        .all()
    )

    return templates.TemplateResponse(
        request,
        "treatment_review.html",
        {
            "user": request.session,

            "doctor_appointments": [],

            "doctors": [
                current_doctor
            ],

            "reviews": reviews,

            "selected_doctor":
                current_doctor,

            "recommended_doctors":
                recommended_doctors,

            "change_doctor_mode": True,

            "appointment": appointment,

            "today": date.today()
        }
    )


# ============================================================
# BOOK ALTERNATIVE DOCTOR
# ============================================================

@router.get("/book-alternative/{doctor_id}")
def book_alternative_doctor(

    request: Request,

    doctor_id: int,

    db: Session = Depends(get_db)

):

    user_id = get_user_id(request)

    if user_id is None:

        return RedirectResponse(
            url="/login",
            status_code=303
        )

    doctor = (
        db.query(Doctor)
        .filter(
            Doctor.id == doctor_id
        )
        .first()
    )

    if doctor is None:

        return RedirectResponse(
            url="/treatment-review",
            status_code=303
        )

    return RedirectResponse(
        url=(
            f"/book-appointment"
            f"?doctor_id={doctor.id}"
            f"&appointment_date="
            f"{date.today().isoformat()}"
        ),
        status_code=303
    )


# ============================================================
# HISTORY
# ============================================================

@router.get("/history")
def review_history(

    request: Request,

    db: Session = Depends(get_db)

):

    user_id = get_user_id(request)

    if user_id is None:

        return RedirectResponse(
            url="/login",
            status_code=303
        )

    doctor_appointments = (
        get_patient_doctor_appointments(
            db,
            user_id
        )
    )

    reviews = (
        db.query(TreatmentReview)
        .filter(
            TreatmentReview.patient_id == user_id
        )
        .order_by(
            TreatmentReview.created_at.desc()
        )
        .all()
    )

    return templates.TemplateResponse(
        request,
        "treatment_review.html",
        {
            "user": request.session,

            "doctor_appointments":
                doctor_appointments,

            "doctors": [
                item["doctor"]
                for item in doctor_appointments
            ],

            "reviews": reviews,

            "selected_doctor": None,

            "recommended_doctors": [],

            "change_doctor_mode": False,

            "appointment": None,

            "today": date.today()
        }
    )