from sqlalchemy.orm import Session

from src.models.screening import ScreeningHistory


def create_screening(
    db: Session,
    patient_id: int,
    symptoms: str,
    ai_response: str,
    care_category: str,
    recommended_specialist: str,
    severity: str
):

    screening = ScreeningHistory(
        patient_id=patient_id,
        symptoms=symptoms,
        ai_response=ai_response,
        care_category=care_category,
        recommended_specialist=recommended_specialist,
        severity=severity
    )

    db.add(screening)

    db.commit()

    db.refresh(screening)

    return screening


def get_patient_screenings(
    db: Session,
    patient_id: int
):

    screenings = (
        db.query(ScreeningHistory)
        .filter(
            ScreeningHistory.patient_id == patient_id
        )
        .order_by(
            ScreeningHistory.created_at.desc()
        )
        .all()
    )

    return screenings


def get_screening_by_id(
    db: Session,
    screening_id: int,
    patient_id: int
):

    screening = (
        db.query(ScreeningHistory)
        .filter(
            ScreeningHistory.id == screening_id,
            ScreeningHistory.patient_id == patient_id
        )
        .first()
    )

    return screening