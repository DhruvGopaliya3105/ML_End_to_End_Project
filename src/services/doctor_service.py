from sqlalchemy.orm import Session

from src.models.doctor import Doctor
from src.models.doctor_slot import DoctorSlot


def get_all_doctors(db: Session):
    doctors = (
        db.query(Doctor)
        .filter(Doctor.is_active == True)
        .order_by(Doctor.name)
        .all()
    )

    return doctors


def get_doctors_by_specialization(
    db: Session,
    specialization: str
):
    doctors = (
        db.query(Doctor)
        .filter(
            Doctor.specialization == specialization,
            Doctor.is_active == True
        )
        .order_by(Doctor.name)
        .all()
    )

    return doctors


def get_doctor_by_id(
    db: Session,
    doctor_id: int
):
    doctor = (
        db.query(Doctor)
        .filter(
            Doctor.id == doctor_id,
            Doctor.is_active == True
        )
        .first()
    )

    return doctor


def get_doctor_slots(
    db: Session,
    doctor_id: int
):
    slots = (
        db.query(DoctorSlot)
        .filter(
            DoctorSlot.doctor_id == doctor_id,
            DoctorSlot.is_available == True
        )
        .order_by(
            DoctorSlot.slot_date,
            DoctorSlot.start_time
        )
        .all()
    )

    return slots