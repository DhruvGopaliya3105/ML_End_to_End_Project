from sqlalchemy.orm import Session

from src.models.medical_record import MedicalRecord
from src.models.treatment import Treatment
from src.models.follow_up import FollowUp


def create_medical_record(
    db: Session,
    patient_id: int,
    visit_date,
    doctor_id: int | None = None,
    appointment_id: int | None = None,
    chief_complaint: str | None = None,
    symptoms: str | None = None,
    clinical_notes: str | None = None,
    diagnosis_notes: str | None = None,
    treatment_summary: str | None = None,
    medicines: str | None = None,
    doctor_instructions: str | None = None
):
    record = MedicalRecord(
        patient_id=patient_id,
        doctor_id=doctor_id,
        appointment_id=appointment_id,
        visit_date=visit_date,
        chief_complaint=chief_complaint,
        symptoms=symptoms,
        clinical_notes=clinical_notes,
        diagnosis_notes=diagnosis_notes,
        treatment_summary=treatment_summary,
        medicines=medicines,
        doctor_instructions=doctor_instructions,
        status="ACTIVE"
    )

    db.add(record)
    db.commit()
    db.refresh(record)

    return record


def get_patient_medical_history(
    db: Session,
    patient_id: int
):
    records = (
        db.query(MedicalRecord)
        .filter(
            MedicalRecord.patient_id == patient_id
        )
        .order_by(
            MedicalRecord.visit_date.desc()
        )
        .all()
    )

    history = []

    for record in records:

        treatments = (
            db.query(Treatment)
            .filter(
                Treatment.medical_record_id == record.id,
                Treatment.patient_id == patient_id
            )
            .order_by(
                Treatment.start_date.desc()
            )
            .all()
        )

        follow_ups = (
            db.query(FollowUp)
            .filter(
                FollowUp.medical_record_id == record.id,
                FollowUp.patient_id == patient_id
            )
            .order_by(
                FollowUp.follow_up_date.asc()
            )
            .all()
        )

        history.append(
            {
                "record": record,
                "treatments": treatments,
                "follow_ups": follow_ups
            }
        )

    return history


def get_medical_record(
    db: Session,
    record_id: int,
    patient_id: int
):
    record = (
        db.query(MedicalRecord)
        .filter(
            MedicalRecord.id == record_id,
            MedicalRecord.patient_id == patient_id
        )
        .first()
    )

    return record