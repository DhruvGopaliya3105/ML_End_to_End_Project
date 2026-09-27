from sqlalchemy.orm import Session

from src.models.prescription import Prescription
from src.models.prescription_medicine import PrescriptionMedicine


def create_prescription(
    db: Session,
    patient_id: int,
    doctor_id: int | None = None,
    medical_record_id: int | None = None,
    treatment_id: int | None = None,
    diagnosis: str | None = None,
    doctor_instructions: str | None = None,
    medicines: list | None = None
):
    prescription = Prescription(
        patient_id=patient_id,
        doctor_id=doctor_id,
        medical_record_id=medical_record_id,
        treatment_id=treatment_id,
        diagnosis=diagnosis,
        doctor_instructions=doctor_instructions
    )

    db.add(prescription)
    db.flush()

    if medicines:

        for medicine in medicines:

            prescription_medicine = PrescriptionMedicine(
                prescription_id=prescription.id,
                medicine_name=medicine.get("medicine_name"),
                dosage=medicine.get("dosage"),
                frequency=medicine.get("frequency"),
                duration=medicine.get("duration"),
                instructions=medicine.get("instructions")
            )

            db.add(prescription_medicine)

    db.commit()
    db.refresh(prescription)

    return prescription


def get_patient_prescriptions(
    db: Session,
    patient_id: int
):
    prescriptions = (
        db.query(Prescription)
        .filter(
            Prescription.patient_id == patient_id
        )
        .order_by(
            Prescription.created_at.desc()
        )
        .all()
    )

    result = []

    for prescription in prescriptions:

        medicines = (
            db.query(PrescriptionMedicine)
            .filter(
                PrescriptionMedicine.prescription_id
                == prescription.id
            )
            .all()
        )

        result.append(
            {
                "prescription": prescription,
                "medicines": medicines
            }
        )

    return result


def get_prescription(
    db: Session,
    prescription_id: int,
    patient_id: int
):
    prescription = (
        db.query(Prescription)
        .filter(
            Prescription.id == prescription_id,
            Prescription.patient_id == patient_id
        )
        .first()
    )

    if not prescription:
        return None

    medicines = (
        db.query(PrescriptionMedicine)
        .filter(
            PrescriptionMedicine.prescription_id
            == prescription.id
        )
        .all()
    )

    return {
        "prescription": prescription,
        "medicines": medicines
    }


def get_previous_prescriptions(
    db: Session,
    patient_id: int
):
    return get_patient_prescriptions(
        db=db,
        patient_id=patient_id
    )