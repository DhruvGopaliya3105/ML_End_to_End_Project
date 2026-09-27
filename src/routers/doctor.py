from fastapi import (
    APIRouter,
    Depends,
    Request
)

from fastapi.responses import RedirectResponse

from fastapi.templating import Jinja2Templates

from sqlalchemy.orm import Session

from src.database.connection import get_db

from src.services.doctor_service import (
    get_all_doctors,
    get_doctors_by_specialization,
    get_doctor_by_id,
    get_doctor_slots
)


router = APIRouter()

templates = Jinja2Templates(
    directory="templates"
)


# =====================================================
# DOCTORS LIST
# =====================================================

@router.get("/doctors")
def doctors_page(

    request: Request,

    specialization: str | None = None,

    db: Session = Depends(get_db)

):

    # -------------------------------------------------
    # LOGIN CHECK
    # -------------------------------------------------

    user_id = request.session.get(
        "user_id"
    )

    if user_id is None:

        return RedirectResponse(
            url="/login",
            status_code=303
        )


    # -------------------------------------------------
    # GET DOCTORS
    # -------------------------------------------------

    if specialization:

        doctors = get_doctors_by_specialization(
            db,
            specialization
        )

    else:

        doctors = get_all_doctors(
            db
        )


    # -------------------------------------------------
    # DEPARTMENTS
    # -------------------------------------------------

    departments = [

        "Cardiology",

        "Dermatology",

        "Neurology",

        "Orthopedics",

        "Pediatrics",

        "General Medicine",

        "Ophthalmology",

        "Dentistry",

        "ENT",

        "Gynecology"

    ]


    # -------------------------------------------------
    # RETURN DOCTORS PAGE
    # -------------------------------------------------

    return templates.TemplateResponse(

        request,

        "doctors.html",

        {

            "user": request.session,

            "doctors": doctors,

            "departments": departments,

            "selected_department":
                specialization

        }

    )


# =====================================================
# DOCTOR DETAIL
# =====================================================

@router.get("/doctor/{doctor_id}")
def doctor_detail(

    doctor_id: int,

    request: Request,

    db: Session = Depends(get_db)

):

    # -------------------------------------------------
    # LOGIN CHECK
    # -------------------------------------------------

    user_id = request.session.get(
        "user_id"
    )

    if user_id is None:

        return RedirectResponse(
            url="/login",
            status_code=303
        )


    # -------------------------------------------------
    # GET DOCTOR
    # -------------------------------------------------

    doctor = get_doctor_by_id(

        db,

        doctor_id

    )


    if doctor is None:

        return RedirectResponse(

            url="/doctors",

            status_code=303

        )


    # -------------------------------------------------
    # OLD SLOTS
    #
    # Kept because doctor_detail.html may still
    # expect "slots".
    # -------------------------------------------------

    slots = get_doctor_slots(

        db,

        doctor_id

    )


    # -------------------------------------------------
    # RETURN DOCTOR DETAIL
    # -------------------------------------------------

    return templates.TemplateResponse(

        request,

        "doctor_detail.html",

        {

            "user": request.session,

            "doctor": doctor,

            "slots": slots

        }

    )