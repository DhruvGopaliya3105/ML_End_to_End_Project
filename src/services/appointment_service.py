from datetime import datetime

from sqlalchemy.orm import Session

from src.models.appointment import Appointment


# =========================================================
# GET SINGLE PATIENT APPOINTMENT
# =========================================================

def get_patient_appointment(
    db: Session,
    appointment_id: int,
    patient_id: int
):

    appointment = (
        db.query(Appointment)
        .filter(
            Appointment.id == appointment_id,
            Appointment.patient_id == patient_id
        )
        .first()
    )

    return appointment


# =========================================================
# GET ALL PATIENT APPOINTMENTS
# =========================================================

def get_patient_appointments(
    db: Session,
    patient_id: int
):

    appointments = (
        db.query(Appointment)
        .filter(
            Appointment.patient_id == patient_id
        )
        .order_by(
            Appointment.appointment_date,
            Appointment.start_time
        )
        .all()
    )

    return appointments


# =========================================================
# BOOK DYNAMIC APPOINTMENT
# =========================================================

def book_dynamic_appointment(
    db: Session,
    patient_id: int,
    doctor_id: int,
    appointment_date,
    start_time,
    end_time,
    visit_type_id: int,
    reason: str = "",
    payment_method: str = "CASH",
    payment_amount: float = 0
):

    if end_time <= start_time:

        return None, "End time must be after start time."


    existing = (
        db.query(Appointment)
        .filter(
            Appointment.doctor_id == doctor_id,

            Appointment.appointment_date
            == appointment_date,

            Appointment.start_time
            < end_time,

            Appointment.end_time
            > start_time,

            Appointment.status.in_([
                "BOOKED",
                "CONFIRMED",
                "DOCTOR_DELAYED"
            ])
        )
        .first()
    )


    if existing:

        return None, (
            "Doctor is already booked at this time."
        )


    start_datetime = datetime.combine(
        appointment_date,
        start_time
    )

    end_datetime = datetime.combine(
        appointment_date,
        end_time
    )

    duration = int(
        (
            end_datetime - start_datetime
        ).total_seconds() / 60
    )


    appointment = Appointment(

        patient_id=patient_id,

        doctor_id=doctor_id,

        appointment_date=appointment_date,

        start_time=start_time,

        end_time=end_time,

        visit_type=str(visit_type_id),

        duration_minutes=duration,

        status="BOOKED",

        reason=reason,

        payment_method=payment_method,

        payment_status="PENDING",

        payment_amount=payment_amount

    )


    try:

        db.add(appointment)

        db.commit()

        db.refresh(appointment)

        return appointment, None


    except Exception as e:

        db.rollback()

        return None, str(e)


# =========================================================
# CONFIRM APPOINTMENT
# =========================================================

def confirm_appointment(
    db: Session,
    appointment_id: int,
    patient_id: int = None
):

    query = (
        db.query(Appointment)
        .filter(
            Appointment.id == appointment_id
        )
    )


    # -----------------------------------------------------
    # SECURITY:
    # Appointment must belong to logged-in patient
    # -----------------------------------------------------

    if patient_id is not None:

        query = query.filter(
            Appointment.patient_id == patient_id
        )


    appointment = query.first()


    if appointment is None:

        return None, "Appointment not found."


    # -----------------------------------------------------
    # Already confirmed
    # -----------------------------------------------------

    if appointment.status == "CONFIRMED":

        return (
            appointment,
            "Appointment is already confirmed."
        )


    # -----------------------------------------------------
    # Only BOOKED can be confirmed
    # -----------------------------------------------------

    if appointment.status != "BOOKED":

        return (
            None,
            f"Appointment cannot be confirmed "
            f"because its current status is "
            f"{appointment.status}."
        )


    # -----------------------------------------------------
    # CONFIRM
    # -----------------------------------------------------

    appointment.status = "CONFIRMED"


    try:

        db.commit()

        db.refresh(appointment)

        return appointment, None


    except Exception as e:

        db.rollback()

        return None, str(e)


# =========================================================
# CANCEL APPOINTMENT
# =========================================================

def patient_cancel_appointment(
    db: Session,
    appointment_id: int,
    patient_id: int
):

    appointment = get_patient_appointment(

        db=db,

        appointment_id=appointment_id,

        patient_id=patient_id

    )


    if appointment is None:

        return None, "Appointment not found."


    if appointment.status in [
        "COMPLETED",
        "CANCELLED",
        "DOCTOR_CANCELLED"
    ]:

        return None, (
            "This appointment cannot be cancelled."
        )


    appointment.status = "CANCELLED"

    appointment.cancelled_by = "PATIENT"

    appointment.cancelled_at = datetime.utcnow()


    try:

        db.commit()

        db.refresh(appointment)

        return appointment, None


    except Exception as e:

        db.rollback()

        return None, str(e)


# =========================================================
# RESCHEDULE APPOINTMENT
# =========================================================

def patient_reschedule_appointment(
    db: Session,
    appointment_id: int,
    patient_id: int,
    new_date,
    new_start_time,
    new_end_time
):

    appointment = get_patient_appointment(

        db=db,

        appointment_id=appointment_id,

        patient_id=patient_id

    )


    if appointment is None:

        return None, "Appointment not found."


    if appointment.status in [
        "COMPLETED",
        "CANCELLED",
        "DOCTOR_CANCELLED"
    ]:

        return None, (
            "This appointment cannot be rescheduled."
        )


    if new_end_time <= new_start_time:

        return None, (
            "End time must be after start time."
        )


    existing = (
        db.query(Appointment)
        .filter(

            Appointment.id != appointment.id,

            Appointment.doctor_id
            == appointment.doctor_id,

            Appointment.appointment_date
            == new_date,

            Appointment.start_time
            < new_end_time,

            Appointment.end_time
            > new_start_time,

            Appointment.status.in_([
                "BOOKED",
                "CONFIRMED"
            ])

        )
        .first()
    )


    if existing:

        return None, (
            "Doctor is already booked at this time."
        )


    start_datetime = datetime.combine(
        new_date,
        new_start_time
    )

    end_datetime = datetime.combine(
        new_date,
        new_end_time
    )

    duration = int(
        (
            end_datetime - start_datetime
        ).total_seconds() / 60
    )


    appointment.appointment_date = new_date

    appointment.start_time = new_start_time

    appointment.end_time = new_end_time

    appointment.duration_minutes = duration

    appointment.status = "BOOKED"


    try:

        db.commit()

        db.refresh(appointment)

        return appointment, None


    except Exception as e:

        db.rollback()

        return None, str(e)