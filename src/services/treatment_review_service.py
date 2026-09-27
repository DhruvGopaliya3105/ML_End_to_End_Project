from sqlalchemy.orm import Session

from src.models.treatment_review import TreatmentReview


# =========================================================
# CREATE REVIEW
# =========================================================

def create_treatment_review(
    db: Session,
    patient_id: int,
    treatment_id: int | None,
    doctor_id: int | None,
    outcome: str,
    current_condition: str,
    experience: str,
    follow_up_preference: str,
    change_reason: str | None = None,
    rating: int | None = None,
    comment: str | None = None
):

    review = TreatmentReview(

        patient_id=patient_id,

        treatment_id=treatment_id,

        doctor_id=doctor_id,

        outcome=outcome,

        current_condition=current_condition,

        experience=experience,

        follow_up_preference=follow_up_preference,

        change_reason=change_reason,

        rating=rating,

        comment=comment

    )

    db.add(review)

    db.commit()

    db.refresh(review)

    return review


# =========================================================
# GET PATIENT REVIEWS
# =========================================================

def get_patient_reviews(
    db: Session,
    patient_id: int
):

    reviews = (

        db.query(TreatmentReview)

        .filter(
            TreatmentReview.patient_id == patient_id
        )

        .order_by(
            TreatmentReview.created_at.desc()
        )

        .all()

    )

    return reviews


# =========================================================
# GET REVIEW
# =========================================================

def get_review(
    db: Session,
    review_id: int,
    patient_id: int
):

    review = (

        db.query(TreatmentReview)

        .filter(

            TreatmentReview.id == review_id,

            TreatmentReview.patient_id == patient_id

        )

        .first()

    )

    return review


# =========================================================
# SHOULD OFFER SECOND OPINION
# =========================================================

def should_offer_second_opinion(
    outcome: str,
    follow_up_preference: str
):

    outcome = outcome.upper()

    preference = follow_up_preference.upper()

    if preference in [
        "NO",
        "NOT_SURE"
    ]:

        return True

    if outcome in [
        "NO_NOTICEABLE_IMPROVEMENT",
        "SYMPTOMS_WORSENED"
    ]:

        return True

    return False