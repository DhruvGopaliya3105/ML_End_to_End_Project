from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from src.database.connection import get_db
from src.config import TEMPLATES_DIR

from src.services.follow_up_service import (
    get_patient_follow_ups,
    complete_follow_up
)


router = APIRouter()

templates = Jinja2Templates(
    directory=str(TEMPLATES_DIR)
)


@router.get("/follow-up-care")
def follow_up_care(
    request: Request,
    db: Session = Depends(get_db)
):

    user_id = request.session.get("user_id")

    if user_id is None:
        return RedirectResponse(
            url="/login",
            status_code=303
        )

    follow_ups = get_patient_follow_ups(
        db=db,
        patient_id=user_id
    )

    pending_follow_ups = []
    completed_follow_ups = []

    for follow_up in follow_ups:

        if follow_up.status == "COMPLETED":
            completed_follow_ups.append(follow_up)

        else:
            pending_follow_ups.append(follow_up)

    return templates.TemplateResponse(
        request,
        "follow_up.html",
        {
            "user": request.session,
            "follow_ups": follow_ups,
            "pending_follow_ups": pending_follow_ups,
            "completed_follow_ups": completed_follow_ups
        }
    )


@router.post("/follow-up/{follow_up_id}/complete")
def complete_follow_up_route(
    follow_up_id: int,
    request: Request,
    db: Session = Depends(get_db)
):

    user_id = request.session.get("user_id")

    if user_id is None:
        return RedirectResponse(
            url="/login",
            status_code=303
        )

    complete_follow_up(
        db=db,
        follow_up_id=follow_up_id,
        patient_id=user_id
    )

    return RedirectResponse(
        url="/follow-up-care",
        status_code=303
    )