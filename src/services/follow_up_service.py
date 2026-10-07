from datetime import date, datetime

from sqlalchemy.orm import Session

from src.models.follow_up import FollowUp


def create_follow_up(
    db: Session,
    patient_id: int,
    follow_up_date: date,
    medical_record_id: int | None = None,
    doctor_id: int | None = None,
    appointment_id: int | None = None,
    reason: str | None = None,
    instructions: str | None = None
):
    follow_up = FollowUp(
        patient_id=patient_id,
        medical_record_id=medical_record_id,
        doctor_id=doctor_id,
        appointment_id=appointment_id,
        follow_up_date=follow_up_date,
        reason=reason,
        instructions=instructions,
        status="PENDING"
    )

    db.add(follow_up)
    db.commit()
    db.refresh(follow_up)

    return follow_up


def get_patient_follow_ups(
    db: Session,
    patient_id: int
):
    follow_ups = (
        db.query(FollowUp)
        .filter(
            FollowUp.patient_id == patient_id
        )
        .order_by(
            FollowUp.follow_up_date.asc()
        )
        .all()
    )

    return follow_ups


def get_follow_up(
    db: Session,
    follow_up_id: int,
    patient_id: int
):
    follow_up = (
        db.query(FollowUp)
        .filter(
            FollowUp.id == follow_up_id,
            FollowUp.patient_id == patient_id
        )
        .first()
    )

    return follow_up


def complete_follow_up(
    db: Session,
    follow_up_id: int,
    patient_id: int
):
    follow_up = get_follow_up(
        db,
        follow_up_id,
        patient_id
    )

    if follow_up is None:
        return None

    follow_up.status = "COMPLETED"
    follow_up.completed_at = datetime.utcnow()

    db.commit()
    db.refresh(follow_up)

    return follow_up

