from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from src.database.connection import get_db

from src.services.treatment_review_service import (
    create_treatment_review,
    get_patient_reviews,
    get_review,
    should_offer_second_opinion
)


router = APIRouter(
    prefix="/treatment-review",
    tags=["Treatment Review"]
)


# =========================================================
# REQUEST BODY
# =========================================================

class TreatmentReviewRequest(BaseModel):

    treatment_id: int | None = None

    doctor_id: int | None = None

    outcome: str

    current_condition: str

    experience: str

    follow_up_preference: str

    change_reason: str | None = None

    rating: int | None = Field(
        default=None,
        ge=1,
        le=5
    )

    comment: str | None = None


# =========================================================
# CREATE REVIEW
# =========================================================

@router.post("/create")
def create_review(
    data: TreatmentReviewRequest,
    request: Request,
    db: Session = Depends(get_db)
):

    user_id = request.session.get("user_id")

    if user_id is None:

        return JSONResponse(
            status_code=401,
            content={
                "success": False,
                "message": "Please login first."
            }
        )

    review = create_treatment_review(

        db=db,

        patient_id=user_id,

        treatment_id=data.treatment_id,

        doctor_id=data.doctor_id,

        outcome=data.outcome,

        current_condition=data.current_condition,

        experience=data.experience,

        follow_up_preference=data.follow_up_preference,

        change_reason=data.change_reason,

        rating=data.rating,

        comment=data.comment
    )

    second_opinion = should_offer_second_opinion(
        data.outcome,
        data.follow_up_preference
    )

    return {

        "success": True,

        "message": "Treatment review created successfully.",

        "review_id": review.id,

        "second_opinion_recommended":
            second_opinion
    }


# =========================================================
# REVIEW HISTORY
# =========================================================

@router.get("/history")
def review_history(
    request: Request,
    db: Session = Depends(get_db)
):

    user_id = request.session.get("user_id")

    if user_id is None:

        return JSONResponse(
            status_code=401,
            content={
                "success": False,
                "message": "Please login first."
            }
        )

    reviews = get_patient_reviews(

        db=db,

        patient_id=user_id
    )

    return {

        "success": True,

        "reviews": [

            {

                "id": review.id,

                "treatment_id":
                    review.treatment_id,

                "doctor_id":
                    review.doctor_id,

                "outcome":
                    review.outcome,

                "current_condition":
                    review.current_condition,

                "experience":
                    review.experience,

                "follow_up_preference":
                    review.follow_up_preference,

                "change_reason":
                    review.change_reason,

                "rating":
                    review.rating,

                "comment":
                    review.comment,

                "created_at":
                    str(review.created_at)

            }

            for review in reviews

        ]

    }


# =========================================================
# SINGLE REVIEW
# =========================================================

@router.get("/{review_id}")
def single_review(
    review_id: int,
    request: Request,
    db: Session = Depends(get_db)
):

    user_id = request.session.get("user_id")

    if user_id is None:

        return JSONResponse(
            status_code=401,
            content={
                "success": False,
                "message": "Please login first."
            }
        )

    review = get_review(

        db=db,

        review_id=review_id,

        patient_id=user_id
    )

    if review is None:

        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "message": "Review not found."
            }
        )

    return {

        "success": True,

        "review": {

            "id":
                review.id,

            "treatment_id":
                review.treatment_id,

            "doctor_id":
                review.doctor_id,

            "outcome":
                review.outcome,

            "current_condition":
                review.current_condition,

            "experience":
                review.experience,

            "follow_up_preference":
                review.follow_up_preference,

            "change_reason":
                review.change_reason,

            "rating":
                review.rating,

            "comment":
                review.comment,

            "created_at":
                str(review.created_at)

        }

    }