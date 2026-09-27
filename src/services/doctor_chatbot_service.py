from datetime import date

from sqlalchemy.orm import Session

from src.models.doctor import Doctor
from src.services.availability_service import get_available_times


# ============================================================
# FIND DOCTORS
# ============================================================

def find_doctors(
    db: Session,
    search_text: str = ""
):

    query = (
        db.query(Doctor)
        .filter(
            Doctor.is_active == True
        )
    )

    search_text = search_text.lower().strip()

    if search_text:

        query = query.filter(
            Doctor.specialization.ilike(
                f"%{search_text}%"
            )
        )

    return query.all()


# ============================================================
# GET DOCTOR DETAILS
# ============================================================

def get_doctor_details(
    doctor: Doctor
):

    return {

        "id": doctor.id,

        "name": doctor.name,

        "specialization":
            doctor.specialization,

        "qualification":
            doctor.qualification,

        "experience_years":
            doctor.experience_years,

        "languages":
            doctor.languages,

        "consultation_fee":
            float(doctor.consultation_fee)
            if doctor.consultation_fee is not None
            else None,

        "bio":
            doctor.bio

    }


# ============================================================
# GET AVAILABLE SLOTS
# ============================================================

def get_doctor_available_slots(
    db: Session,
    doctor: Doctor,
    selected_date: date,
    duration_minutes: int = 30
):

    slots = get_available_times(

        db=db,

        doctor_id=doctor.id,

        selected_date=selected_date,

        duration_minutes=duration_minutes

    )

    return slots


# ============================================================
# FORMAT DOCTOR FOR CHATBOT
# ============================================================

def format_doctor_for_chatbot(
    doctor: Doctor
):

    fee = (
        f"₹{float(doctor.consultation_fee):.2f}"
        if doctor.consultation_fee is not None
        else "Not specified"
    )

    experience = (
        f"{doctor.experience_years} years"
        if doctor.experience_years is not None
        else "Not specified"
    )

    qualification = (
        doctor.qualification
        if doctor.qualification
        else "Not specified"
    )

    languages = (
        doctor.languages
        if doctor.languages
        else "Not specified"
    )

    return (

        f"👨‍⚕️ Dr. {doctor.name}\n\n"

        f"Specialization: "
        f"{doctor.specialization}\n"

        f"Qualification: "
        f"{qualification}\n"

        f"Experience: "
        f"{experience}\n"

        f"Languages: "
        f"{languages}\n"

        f"Consultation Fee: "
        f"{fee}\n\n"

        f"{doctor.bio or ''}"

    )