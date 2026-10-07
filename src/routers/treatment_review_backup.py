from fastapi import (
    APIRouter,
    Depends,
    Request,
    Form
)

from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from sqlalchemy.orm import Session

from src.database.connection import get_db
from src.config import TEMPLATES_DIR

from src.models.doctor import Doctor
from src.models.treatment_review import TreatmentReview

from datetime import datetime


router = APIRouter(
    prefix="/treatment-review",
    tags=["Treatment Review"]
)

templates = Jinja2Templates(
    directory=str(TEMPLATES_DIR)
)


# ============================================================
# DOCTOR FEEDBACK PAGE
# ============================================================

@router.get("")
def treatment_review_page(
    request: Request,
    db: Session = Depends(get_db)
):

    user_id = request.session.get("user_id")

    if user_id is None:

        return RedirectResponse(
            url="/login",
            status_code=303
        )

    doctors = (
        db.query(Doctor)
        .filter(
            Doctor.is_active == True
        )
        .order_by(
            Doctor.name.asc()
        )
        .all()
    )

    reviews = (
        db.query(TreatmentReview)
        .filter(
            TreatmentReview.patient_id == user_id
        )
        .order_by(
            TreatmentReview.created_at.desc()
        )
        .all()
    )

    return templates.TemplateResponse(
        request,
        "treatment_review.html",
        {
            "user": request.session,
            "doctors": doctors,
            "reviews": reviews
        }
    )


# ============================================================
# SUBMIT FEEDBACK
# ============================================================

@router.post("/submit")
def submit_treatment_review(

    request: Request,

    doctor_id: int = Form(...),

    rating: int = Form(...),

    outcome: str = Form(...),

    current_condition: str = Form(""),

    experience: str = Form(""),

    follow_up_preference: str = Form(""),

    change_reason: str = Form(""),

    comment: str = Form(""),

    db: Session = Depends(get_db)

):

    user_id = request.session.get("user_id")

    if user_id is None:

        return RedirectResponse(
            url="/login",
            status_code=303
        )

    # --------------------------------------------------------
    # VALIDATE RATING
    # --------------------------------------------------------

    if rating < 1 or rating > 5:

        return RedirectResponse(
            url="/treatment-review",
            status_code=303
        )

    # --------------------------------------------------------
    # CHECK DOCTOR
    # --------------------------------------------------------

    doctor = (
        db.query(Doctor)
        .filter(
            Doctor.id == doctor_id,
            Doctor.is_active == True
        )
        .first()
    )

    if doctor is None:

        return RedirectResponse(
            url="/treatment-review",
            status_code=303
        )

    # --------------------------------------------------------
    # CREATE REVIEW
    # --------------------------------------------------------

    review = TreatmentReview(

        patient_id=user_id,

        doctor_id=doctor_id,

        outcome=outcome,

        current_condition=current_condition,

        experience=experience,

        follow_up_preference=follow_up_preference,

        change_reason=change_reason,

        rating=rating,

        comment=comment,

        created_at=datetime.utcnow(),

        updated_at=datetime.utcnow()
    )

    db.add(review)

    db.commit()

    db.refresh(review)

    return RedirectResponse(
        url="/treatment-review",
        status_code=303
    )


# ============================================================
# FEEDBACK HISTORY
# ============================================================

@router.get("/history")
def review_history(
    request: Request,
    db: Session = Depends(get_db)
):

    user_id = request.session.get("user_id")

    if user_id is None:

        return RedirectResponse(
            url="/login",
            status_code=303
        )

    reviews = (
        db.query(TreatmentReview)
        .filter(
            TreatmentReview.patient_id == user_id
        )
        .order_by(
            TreatmentReview.created_at.desc()
        )
        .all()
    )

    return templates.TemplateResponse(
        request,
        "treatment_review.html",
        {
            "user": request.session,
            "doctors": [],
            "reviews": reviews
        }
    )