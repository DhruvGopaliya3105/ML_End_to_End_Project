from datetime import date, time

from fastapi import (
    APIRouter,
    Depends,
    Request,
    Form
)

from fastapi.responses import RedirectResponse

from fastapi.templating import Jinja2Templates

from sqlalchemy.orm import Session

from src.database.connection import get_db

from src.models.doctor import Doctor
from src.models.visit_type import VisitType

from src.services.availability_service import (
    get_available_times
)

from src.services.appointment_service import (
    book_dynamic_appointment,
    get_patient_appointments,
    patient_cancel_appointment
)


router = APIRouter()

templates = Jinja2Templates(
    directory="templates"
)


# ============================================================
# BOOKING PAGE
# ============================================================

@router.get("/book-appointment")
def booking_page(

    request: Request,

    doctor_id: int,

    appointment_date: date,

    db: Session = Depends(get_db)

):

    user_id = request.session.get("user_id")


    if user_id is None:

        return RedirectResponse(
            url="/login",
            status_code=303
        )


    doctor = (

        db.query(Doctor)

        .filter(

            Doctor.id == doctor_id,

            Doctor.is_active == True

        )

        .first()

    )


    if doctor is None:

        return RedirectResponse(
            url="/doctors",
            status_code=303
        )


    visit_types = (

        db.query(VisitType)

        .filter(

            VisitType.is_active == True

        )

        .order_by(

            VisitType.id

        )

        .all()

    )


    return templates.TemplateResponse(

        request,

        "book_appointment.html",

        {

            "user": request.session,

            "doctor": doctor,

            "appointment_date":
                appointment_date,

            "visit_types":
                visit_types

        }

    )


# ============================================================
# AVAILABLE TIMES API
# ============================================================

@router.get("/api/appointment-times")
def appointment_times(

    request: Request,

    doctor_id: int,

    appointment_date: date,

    visit_type_id: int,

    db: Session = Depends(get_db)

):

    user_id = request.session.get("user_id")


    if user_id is None:

        return {

            "success": False,

            "message": "Login required"

        }


    visit_type = (

        db.query(VisitType)

        .filter(

            VisitType.id == visit_type_id,

            VisitType.is_active == True

        )

        .first()

    )


    if visit_type is None:

        return {

            "success": False,

            "message": "Visit type not found"

        }


    available_times = get_available_times(

        db=db,

        doctor_id=doctor_id,

        selected_date=appointment_date,

        duration_minutes=
            visit_type.default_duration_minutes

    )


    return {

        "success": True,

        "duration_minutes":
            visit_type.default_duration_minutes,

        "times": [

            {

                "start_time":
                    item["start_time"].strftime("%H:%M"),

                "end_time":
                    item["end_time"].strftime("%H:%M")

            }

            for item in available_times

        ]

    }


# ============================================================
# CREATE APPOINTMENT
# ============================================================

@router.post("/book-appointment")
def book_appointment(

    request: Request,

    doctor_id: int = Form(...),

    appointment_date: date = Form(...),

    start_time: str = Form(...),

    end_time: str = Form(...),

    visit_type_id: int = Form(...),

    reason: str = Form(""),

    payment_method: str = Form("CASH"),

    payment_amount: float = Form(0),

    db: Session = Depends(get_db)

):

    user_id = request.session.get("user_id")


    if user_id is None:

        return RedirectResponse(
            url="/login",
            status_code=303
        )


    # --------------------------------------------------------
    # Convert string time to Python time object
    # --------------------------------------------------------

    try:

        start_hour, start_minute = map(
            int,
            start_time.split(":")
        )

        end_hour, end_minute = map(
            int,
            end_time.split(":")
        )

        start = time(
            start_hour,
            start_minute
        )

        end = time(
            end_hour,
            end_minute
        )

    except (ValueError, TypeError):

        return RedirectResponse(
            url="/doctors",
            status_code=303
        )


    # --------------------------------------------------------
    # Book appointment
    # --------------------------------------------------------

    appointment, error = book_dynamic_appointment(

        db=db,

        patient_id=user_id,

        doctor_id=doctor_id,

        appointment_date=appointment_date,

        start_time=start,

        end_time=end,

        visit_type_id=visit_type_id,

        reason=reason,

        payment_method=payment_method,

        payment_amount=payment_amount

    )


    if error:

        return RedirectResponse(

            url="/doctors",

            status_code=303

        )


    return RedirectResponse(

        url="/appointments",

        status_code=303

    )


# ============================================================
# MY APPOINTMENTS
# ============================================================

@router.get("/appointments")
def my_appointments(

    request: Request,

    db: Session = Depends(get_db)

):

    user_id = request.session.get("user_id")


    if user_id is None:

        return RedirectResponse(

            url="/login",

            status_code=303

        )


    appointments = get_patient_appointments(

        db,

        user_id

    )


    return templates.TemplateResponse(

        request,

        "appointments.html",

        {

            "user": request.session,

            "appointments": appointments

        }

    )


# ============================================================
# CANCEL APPOINTMENT
# ============================================================

@router.post("/appointments/{appointment_id}/cancel")
def cancel_appointment(

    request: Request,

    appointment_id: int,

    db: Session = Depends(get_db)

):

    user_id = request.session.get("user_id")


    # --------------------------------------------------------
    # Login check
    # --------------------------------------------------------

    if user_id is None:

        return RedirectResponse(

            url="/login",

            status_code=303

        )


    # --------------------------------------------------------
    # Cancel appointment
    # --------------------------------------------------------

    appointment, error = patient_cancel_appointment(

        db=db,

        appointment_id=appointment_id,

        patient_id=user_id

    )


    # --------------------------------------------------------
    # If error
    # --------------------------------------------------------

    if error:

        return RedirectResponse(

            url="/appointments",

            status_code=303

        )


    # --------------------------------------------------------
    # Success
    # --------------------------------------------------------

    return RedirectResponse(

        url="/appointments",

        status_code=303

    )