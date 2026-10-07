from datetime import date

from sqlalchemy.orm import Session

from src.models.treatment import Treatment


def create_treatment(
    db: Session,
    patient_id: int,
    treatment_name: str,
    medical_record_id: int | None = None,
    doctor_id: int | None = None,
    description: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None
):
    treatment = Treatment(
        patient_id=patient_id,
        medical_record_id=medical_record_id,
        doctor_id=doctor_id,
        treatment_name=treatment_name,
        description=description,
        start_date=start_date,
        end_date=end_date,
        status="ACTIVE"
    )

    db.add(treatment)
    db.commit()
    db.refresh(treatment)

    return treatment


def get_patient_treatments(
    db: Session,
    patient_id: int
):
    treatments = (
        db.query(Treatment)
        .filter(
            Treatment.patient_id == patient_id
        )
        .order_by(
            Treatment.start_date.desc()
        )
        .all()
    )

    return treatments


def get_treatment(
    db: Session,
    treatment_id: int,
    patient_id: int
):
    treatment = (
        db.query(Treatment)
        .filter(
            Treatment.id == treatment_id,
            Treatment.patient_id == patient_id
        )
        .first()
    )

    return treatment