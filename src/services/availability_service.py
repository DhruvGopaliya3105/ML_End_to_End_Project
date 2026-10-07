
from datetime import datetime, date, time, timedelta

from sqlalchemy.orm import Session

from src.models.doctor_schedule import DoctorSchedule
from src.models.appointment import Appointment


# ============================================================
# TIME -> DATETIME
# ============================================================

def time_to_datetime(
    selected_date: date,
    selected_time: time
):
    return datetime.combine(
        selected_date,
        selected_time
    )


# ============================================================
# GET DOCTOR SCHEDULE
# ============================================================

def get_doctor_schedule(
    db: Session,
    doctor_id: int,
    selected_date: date
):

    day_of_week = selected_date.weekday()

    schedules = (
        db.query(DoctorSchedule)
        .filter(
            DoctorSchedule.doctor_id == doctor_id,

            DoctorSchedule.day_of_week == day_of_week,

            DoctorSchedule.is_available == True
        )
        .order_by(
            DoctorSchedule.start_time
        )
        .all()
    )

    return schedules


# ============================================================
# GET AVAILABLE TIMES
# ============================================================

def get_available_times(
    db: Session,
    doctor_id: int,
    selected_date: date,
    duration_minutes: int
):

    # ========================================================
    # DOCTOR WORKING SCHEDULE
    # ========================================================

    schedules = get_doctor_schedule(
        db=db,
        doctor_id=doctor_id,
        selected_date=selected_date
    )

    if not schedules:
        return []


    # ========================================================
    # EXISTING APPOINTMENTS
    # ========================================================

    existing_appointments = (
        db.query(Appointment)
        .filter(
            Appointment.doctor_id == doctor_id,

            Appointment.appointment_date
            == selected_date,

            Appointment.status.in_([
                "BOOKED",
                "CONFIRMED",
                "DOCTOR_DELAYED"
            ])
        )
        .order_by(
            Appointment.start_time
        )
        .all()
    )


    available_times = []


    # ========================================================
    # PROCESS EACH WORKING SCHEDULE
    # ========================================================

    for schedule in schedules:

        current_datetime = time_to_datetime(
            selected_date,
            schedule.start_time
        )

        schedule_end = time_to_datetime(
            selected_date,
            schedule.end_time
        )


        # ====================================================
        # APPOINTMENT DURATION
        # ====================================================

        duration = timedelta(
            minutes=duration_minutes
        )


        # ====================================================
        # IMPORTANT
        #
        # We use appointment duration as the next interval.
        #
        # Example:
        #
        # 10:00 - 10:30
        # 10:30 - 11:00
        # 11:00 - 11:30
        #
        # NOT:
        #
        # 10:00 - 10:30
        # 10:05 - 10:35
        # 10:10 - 10:40
        # ====================================================

        interval = duration


        # ====================================================
        # GENERATE SLOTS
        # ====================================================

        while current_datetime + duration <= schedule_end:

            proposed_start = current_datetime

            proposed_end = (
                current_datetime + duration
            )


            overlap = False


            # =================================================
            # CHECK EXISTING APPOINTMENTS
            # =================================================

            for appointment in existing_appointments:

                appointment_start = time_to_datetime(
                    selected_date,
                    appointment.start_time
                )

                appointment_end = time_to_datetime(
                    selected_date,
                    appointment.end_time
                )


                # ---------------------------------------------
                # OVERLAP CONDITION
                # ---------------------------------------------

                if (
                    proposed_start < appointment_end
                    and
                    proposed_end > appointment_start
                ):

                    overlap = True

                    break


            # =================================================
            # ADD SLOT IF AVAILABLE
            # =================================================

            if not overlap:

                available_times.append({

                    "start_time":
                        proposed_start.time(),

                    "end_time":
                        proposed_end.time(),

                    "duration_minutes":
                        duration_minutes

                })


            # =================================================
            # MOVE TO NEXT NON-OVERLAPPING SLOT
            # =================================================

            current_datetime += interval


    return available_times

