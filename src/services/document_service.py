from sqlalchemy.orm import Session

from src.models.patient_document import PatientDocument


def create_document(
    db: Session,
    patient_id: int,
    document_name: str,
    file_path: str,
    document_type: str | None = None,
    file_size: int | None = None,
    medical_record_id: int | None = None
):
    document = PatientDocument(
        patient_id=patient_id,
        medical_record_id=medical_record_id,
        document_name=document_name,
        document_type=document_type,
        file_path=file_path,
        file_size=file_size,
        status="ACTIVE"
    )

    db.add(document)
    db.commit()
    db.refresh(document)

    return document


def get_patient_documents(
    db: Session,
    patient_id: int
):
    documents = (
        db.query(PatientDocument)
        .filter(
            PatientDocument.patient_id == patient_id,
            PatientDocument.status == "ACTIVE"
        )
        .order_by(
            PatientDocument.uploaded_at.desc()
        )
        .all()
    )

    return documents


def get_document(
    db: Session,
    document_id: int,
    patient_id: int
):
    document = (
        db.query(PatientDocument)
        .filter(
            PatientDocument.id == document_id,
            PatientDocument.patient_id == patient_id,
            PatientDocument.status == "ACTIVE"
        )
        .first()
    )

    return document