from datetime import datetime

from sqlalchemy.orm import Session

from src.models.appointment import Appointment
from src.models.doctor import Doctor


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

    # -----------------------------------------------------
    # VALIDATE TIME
    # -----------------------------------------------------

    if end_time <= start_time:

        return None, "End time must be after start time."


    # -----------------------------------------------------
    # CHECK DOCTOR SLOT AVAILABILITY
    # -----------------------------------------------------

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


    # -----------------------------------------------------
    # CALCULATE DURATION
    # -----------------------------------------------------

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


    # -----------------------------------------------------
    # GET VISIT TYPE NAME
    # -----------------------------------------------------

    visit_type_name = None

    try:

        from src.models.visit_type import VisitType

        visit_type_row = (
            db.query(VisitType)
            .filter(
                VisitType.id == visit_type_id
            )
            .first()
        )

        if visit_type_row is not None:

            visit_type_name = visit_type_row.name

    except Exception:

        visit_type_name = None


    # -----------------------------------------------------
    # FALLBACK TO VISIT TYPE ID
    # -----------------------------------------------------

    visit_type_value = (
        visit_type_name
        if visit_type_name
        else str(visit_type_id)
    )


    # -----------------------------------------------------
    # GET SELECTED DOCTOR
    # -----------------------------------------------------

    doctor = (
        db.query(Doctor)
        .filter(
            Doctor.id == doctor_id,
            Doctor.is_active == True
        )
        .first()
    )


    if doctor is None:

        return None, "Doctor not found."


    # -----------------------------------------------------
    # ALWAYS USE DOCTOR CONSULTATION FEE
    # -----------------------------------------------------

    try:

        fee = float(
            doctor.consultation_fee or 0
        )

    except (TypeError, ValueError):

        fee = 0.0


    # -----------------------------------------------------
    # VALIDATE PAYMENT METHOD
    # -----------------------------------------------------

    payment_method = (
        payment_method or "CASH"
    ).upper().strip()


    if payment_method not in {
        "CASH",
        "ONLINE"
    }:

        payment_method = "CASH"


    # -----------------------------------------------------
    # PAYMENT STATUS
    # -----------------------------------------------------

    if payment_method == "ONLINE":

        payment_status = "PAID"

    else:

        payment_status = "PENDING"


    # -----------------------------------------------------
    # CREATE APPOINTMENT
    # -----------------------------------------------------

    appointment = Appointment(

        patient_id=patient_id,

        doctor_id=doctor_id,

        appointment_date=appointment_date,

        start_time=start_time,

        end_time=end_time,

        visit_type=visit_type_value,

        duration_minutes=duration,

        # Final booking from normal appointment page
        # is confirmed immediately.
        status="CONFIRMED",

        reason=reason,

        payment_method=payment_method,

        payment_status=payment_status,

        # Never trust the amount coming from HTML.
        # Store the doctor's actual consultation fee.
        payment_amount=fee

    )


    # -----------------------------------------------------
    # SAVE APPOINTMENT
    # -----------------------------------------------------

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
    # SECURITY
    # -----------------------------------------------------

    if patient_id is not None:

        query = query.filter(
            Appointment.patient_id == patient_id
        )


    appointment = query.first()


    if appointment is None:

        return None, "Appointment not found."


    # -----------------------------------------------------
    # ALREADY CONFIRMED
    # -----------------------------------------------------

    if appointment.status == "CONFIRMED":

        return (
            appointment,
            "Appointment is already confirmed."
        )


    # -----------------------------------------------------
    # ONLY BOOKED CAN BE CONFIRMED
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
# COMPLETE DEMO PAYMENT + CONFIRM
# =========================================================

def complete_demo_payment(
    db: Session,
    appointment_id: int,
    patient_id: int,
    payment_method: str
):

    # -----------------------------------------------------
    # GET PATIENT APPOINTMENT
    # -----------------------------------------------------

    appointment = get_patient_appointment(
        db=db,
        appointment_id=appointment_id,
        patient_id=patient_id
    )


    if appointment is None:

        return None, "Appointment not found."


    # -----------------------------------------------------
    # VALIDATE PAYMENT METHOD
    # -----------------------------------------------------

    payment_method = (
        payment_method or "CASH"
    ).upper().strip()


    if payment_method not in {
        "CASH",
        "ONLINE"
    }:

        return None, "Invalid payment method."


    # -----------------------------------------------------
    # GET DOCTOR FEE
    # -----------------------------------------------------

    doctor = (
        db.query(Doctor)
        .filter(
            Doctor.id == appointment.doctor_id,
            Doctor.is_active == True
        )
        .first()
    )


    if doctor is not None:

        try:

            appointment.payment_amount = float(
                doctor.consultation_fee or 0
            )

        except (TypeError, ValueError):

            pass


    # -----------------------------------------------------
    # UPDATE PAYMENT
    # -----------------------------------------------------

    appointment.payment_method = payment_method


    if payment_method == "ONLINE":

        appointment.payment_status = "PAID"

    else:

        appointment.payment_status = "PENDING"


    # -----------------------------------------------------
    # CONFIRM APPOINTMENT
    # -----------------------------------------------------

    if appointment.status == "BOOKED":

        appointment.status = "CONFIRMED"


    # -----------------------------------------------------
    # SAVE
    # -----------------------------------------------------

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


    # -----------------------------------------------------
    # CANNOT CANCEL COMPLETED/CANCELLED APPOINTMENT
    # -----------------------------------------------------

    if appointment.status in [
        "COMPLETED",
        "CANCELLED",
        "DOCTOR_CANCELLED"
    ]:

        return None, (
            "This appointment cannot be cancelled."
        )


    # -----------------------------------------------------
    # CANCEL
    # -----------------------------------------------------

    appointment.status = "CANCELLED"

    appointment.cancelled_by = "PATIENT"

    appointment.cancelled_at = datetime.utcnow()


    # -----------------------------------------------------
    # REFUND LOGIC
    # -----------------------------------------------------

    if (
        appointment.payment_method == "ONLINE"
        and appointment.payment_status == "PAID"
    ):

        # Demo refund status.
        # No real payment gateway is connected.
        appointment.refund_status = "PENDING"

        appointment.refund_amount = (
            appointment.payment_amount
        )

        appointment.refund_method = (
            "ORIGINAL_METHOD"
        )

        appointment.refund_reason = (
            "Patient cancelled appointment"
        )

    else:

        # Cash payment was never collected.
        appointment.refund_status = "NOT_REQUIRED"

        appointment.refund_amount = None

        appointment.refund_method = None

        appointment.refund_reason = None


    # -----------------------------------------------------
    # SAVE
    # -----------------------------------------------------

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


    # -----------------------------------------------------
    # CANNOT RESCHEDULE CLOSED APPOINTMENTS
    # -----------------------------------------------------

    if appointment.status in [
        "COMPLETED",
        "CANCELLED",
        "DOCTOR_CANCELLED"
    ]:

        return None, (
            "This appointment cannot be rescheduled."
        )


    # -----------------------------------------------------
    # VALIDATE TIME
    # -----------------------------------------------------

    if new_end_time <= new_start_time:

        return None, (
            "End time must be after start time."
        )


    # -----------------------------------------------------
    # CHECK NEW SLOT
    # -----------------------------------------------------

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


    # -----------------------------------------------------
    # CALCULATE NEW DURATION
    # -----------------------------------------------------

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


    # -----------------------------------------------------
    # SAVE EXISTING PAYMENT STATE
    # -----------------------------------------------------

    previous_status = appointment.status

    previous_payment_method = (
        appointment.payment_method
    )

    previous_payment_status = (
        appointment.payment_status
    )

    previous_payment_amount = (
        appointment.payment_amount
    )


    # -----------------------------------------------------
    # UPDATE APPOINTMENT SLOT
    # -----------------------------------------------------

    appointment.appointment_date = new_date

    appointment.start_time = new_start_time

    appointment.end_time = new_end_time

    appointment.duration_minutes = duration


    # -----------------------------------------------------
    # PRESERVE APPOINTMENT STATUS
    # -----------------------------------------------------

    if previous_status == "CONFIRMED":

        appointment.status = "CONFIRMED"

    else:

        appointment.status = "BOOKED"


    # -----------------------------------------------------
    # PRESERVE PAYMENT INFORMATION
    # -----------------------------------------------------

    appointment.payment_method = (
        previous_payment_method
    )

    appointment.payment_status = (
        previous_payment_status
    )

    appointment.payment_amount = (
        previous_payment_amount
    )


    # -----------------------------------------------------
    # SAVE
    # -----------------------------------------------------

    try:

        db.commit()

        db.refresh(appointment)

        return appointment, None


    except Exception as e:

        db.rollback()

        return None, str(e)